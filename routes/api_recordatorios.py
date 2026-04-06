import re
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from extensions import db
from models import RecordatorioManual, Paciente, PlantillaMensaje
from datetime import datetime

recordatorios_bp = Blueprint('recordatorios', __name__, url_prefix='/api/recordatorios')

# Tipos que vienen con la app y no se pueden eliminar
_BUILT_IN_TIPOS = {'recordatorio_seguimiento', 'recordatorio_tratamiento', 'recordatorio_recuperacion'}

# Tipos automáticos del sistema que NO deben aparecer en la lista de recordatorios manuales
_AUTOMATED_TIPOS = {
    'recordatorio_24h', 'no_asistencia_reagendar', 'proxima_visita',
    'postconsulta', 'confirmacion', 'anticipo', 'info_consulta',
    'sonrisas_magicas', 'cumpleanos',
}


def _tipo_key(tipo_db):
    """Extrae la clave corta: 'recordatorio_seguimiento' → 'seguimiento'."""
    if tipo_db.startswith('recordatorio_'):
        return tipo_db[len('recordatorio_'):]
    return tipo_db


def _plantilla_to_dict(p):
    return {
        'id': p.id,
        'tipo_key': _tipo_key(p.tipo),
        'nombre': p.nombre,
        'contenido': p.contenido,
        'es_builtin': p.tipo in _BUILT_IN_TIPOS,
    }


@recordatorios_bp.route('', methods=['POST'])
@login_required
def crear():
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400

    paciente_id = data.get('paciente_id')
    if not paciente_id:
        return jsonify(error='paciente_id requerido'), 400

    paciente = Paciente.query.filter_by(id=paciente_id, eliminado=False).first()
    if not paciente:
        return jsonify(error='Paciente no encontrado'), 404

    mensaje = (data.get('mensaje') or '').strip()
    fecha_str = data.get('fecha_programada')
    if not mensaje:
        return jsonify(error='mensaje requerido'), 400
    if not fecha_str:
        return jsonify(error='fecha_programada requerida'), 400

    try:
        fecha_programada = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify(error='Formato de fecha inválido (YYYY-MM-DD)'), 400

    r = RecordatorioManual(
        paciente_id=paciente_id,
        cita_origen_id=data.get('cita_origen_id'),
        tipo=data.get('tipo', 'seguimiento'),
        mensaje=mensaje,
        fecha_programada=fecha_programada,
        creado_por=current_user.id,
    )
    db.session.add(r)
    db.session.commit()
    return jsonify(r.to_dict()), 201


@recordatorios_bp.route('/paciente/<int:paciente_id>', methods=['GET'])
@login_required
def listar_paciente(paciente_id):
    records = RecordatorioManual.query.filter_by(paciente_id=paciente_id)\
        .order_by(RecordatorioManual.fecha_programada.desc()).all()
    return jsonify([r.to_dict() for r in records])


@recordatorios_bp.route('/<int:recordatorio_id>', methods=['DELETE'])
@login_required
def cancelar(recordatorio_id):
    r = RecordatorioManual.query.get_or_404(recordatorio_id)
    if r.status == 'enviado':
        return jsonify(error='No se puede cancelar un recordatorio ya enviado'), 400
    r.status = 'cancelado'
    db.session.commit()
    return jsonify(ok=True)


@recordatorios_bp.route('/plantillas', methods=['GET'])
@login_required
def listar_plantillas():
    """Retorna lista de todos los tipos de recordatorio disponibles."""
    plantillas = (PlantillaMensaje.query
                  .filter(PlantillaMensaje.tipo.like('recordatorio_%'),
                          ~PlantillaMensaje.tipo.in_(_AUTOMATED_TIPOS),
                          PlantillaMensaje.activo == True)
                  .order_by(PlantillaMensaje.id)
                  .all())
    return jsonify([_plantilla_to_dict(p) for p in plantillas])


@recordatorios_bp.route('/plantillas', methods=['POST'])
@login_required
def crear_plantilla():
    """Crea un nuevo tipo de recordatorio personalizado."""
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400
    nombre = (data.get('nombre') or '').strip()
    contenido = (data.get('contenido') or '').strip()
    if not nombre:
        return jsonify(error='nombre requerido'), 400
    if not contenido:
        return jsonify(error='contenido requerido'), 400

    # Generar tipo slug: "Limpieza Preventiva" → "recordatorio_limpieza_preventiva"
    slug = re.sub(r'[^a-z0-9]+', '_', nombre.lower()).strip('_')
    tipo = f'recordatorio_{slug}'

    if PlantillaMensaje.query.filter_by(tipo=tipo).first():
        return jsonify(error='Ya existe un tipo con ese nombre'), 409

    p = PlantillaMensaje(nombre=nombre, tipo=tipo, contenido=contenido)
    db.session.add(p)
    db.session.commit()
    return jsonify(_plantilla_to_dict(p)), 201


@recordatorios_bp.route('/plantillas/<int:plantilla_id>', methods=['PUT'])
@login_required
def actualizar_plantilla(plantilla_id):
    """Edita el contenido (y opcionalmente nombre) de una plantilla de recordatorio."""
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    p = PlantillaMensaje.query.get_or_404(plantilla_id)
    if not p.tipo.startswith('recordatorio_'):
        return jsonify(error='No es una plantilla de recordatorio'), 400
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400
    if 'contenido' in data:
        p.contenido = data['contenido']
    if 'nombre' in data and p.tipo not in _BUILT_IN_TIPOS:
        p.nombre = data['nombre'].strip()
    db.session.commit()
    return jsonify(_plantilla_to_dict(p))


@recordatorios_bp.route('/plantillas/<int:plantilla_id>', methods=['DELETE'])
@login_required
def eliminar_plantilla(plantilla_id):
    """Elimina (desactiva) un tipo de recordatorio personalizado."""
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    p = PlantillaMensaje.query.get_or_404(plantilla_id)
    if p.tipo in _BUILT_IN_TIPOS:
        return jsonify(error='No se pueden eliminar los tipos predeterminados'), 400
    p.activo = False
    db.session.commit()
    return jsonify(ok=True)
