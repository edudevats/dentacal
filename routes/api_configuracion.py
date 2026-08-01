from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from extensions import db
from models import TipoCita, PlantillaMensaje, ConfiguracionConsultorio, OrigenPaciente
import logging

logger = logging.getLogger(__name__)

configuracion_bp = Blueprint('configuracion', __name__, url_prefix='/api/configuracion')


def _parse_hora(valor):
    """Convierte 'HH:MM' a datetime.time; ValueError si es invalido."""
    from datetime import time
    partes = str(valor).split(':')
    if len(partes) != 2:
        raise ValueError('formato de hora invalido')
    h, m = int(partes[0]), int(partes[1])
    return time(h, m)  # time() ya valida rangos (0-23 / 0-59)


def _reprogramar_resumen_doctores(hora, minuto):
    """Reprograma el job del resumen en caliente. No-op si el scheduler no corre."""
    try:
        from extensions import scheduler
        if scheduler.running and scheduler.get_job('resumen_doctores'):
            scheduler.reschedule_job('resumen_doctores', trigger='cron', hour=hora, minute=minuto)
            logger.info(f'Job resumen_doctores reprogramado a {hora:02d}:{minuto:02d}')
    except Exception as e:
        logger.warning(f'No se pudo reprogramar resumen_doctores: {e}')


@configuracion_bp.route('', methods=['GET'])
@login_required
def obtener():
    config = ConfiguracionConsultorio.query.first()
    if not config:
        return jsonify({}), 200
    return jsonify({
        'id': config.id,
        'nombre_consultorio': config.nombre_consultorio,
        'direccion': config.direccion,
        'telefono': config.telefono or '',
        'horario_apertura': config.horario_apertura.strftime('%H:%M') if config.horario_apertura else '09:00',
        'horario_cierre': config.horario_cierre.strftime('%H:%M') if config.horario_cierre else '18:00',
        'precio_primera_consulta': float(config.precio_primera_consulta) if config.precio_primera_consulta else 550,
        'porcentaje_anticipo': config.porcentaje_anticipo,
        'clabe': config.clabe,
        'tarjeta': config.tarjeta,
        'titular_cuenta': config.titular_cuenta,
        'google_reviews_link': config.google_reviews_link,
        'hora_resumen_doctores': config.hora_resumen_doctores.strftime('%H:%M') if config.hora_resumen_doctores else '21:00',
    })


@configuracion_bp.route('', methods=['PUT'])
@login_required
def actualizar():
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    config = ConfiguracionConsultorio.query.first()
    if not config:
        config = ConfiguracionConsultorio()
        db.session.add(config)

    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400
    fields = ['nombre_consultorio', 'direccion', 'telefono', 'clabe',
              'tarjeta', 'titular_cuenta', 'google_reviews_link',
              'porcentaje_anticipo']
    for f in fields:
        if f in data:
            setattr(config, f, data[f])

    try:
        if 'horario_apertura' in data:
            config.horario_apertura = _parse_hora(data['horario_apertura'])
        if 'horario_cierre' in data:
            config.horario_cierre = _parse_hora(data['horario_cierre'])
        if 'precio_primera_consulta' in data:
            config.precio_primera_consulta = float(data['precio_primera_consulta'])
        if 'hora_resumen_doctores' in data:
            config.hora_resumen_doctores = _parse_hora(data['hora_resumen_doctores'])
            _reprogramar_resumen_doctores(config.hora_resumen_doctores.hour, config.hora_resumen_doctores.minute)
    except (ValueError, TypeError):
        return jsonify(error='Hora invalida'), 400

    db.session.commit()
    return jsonify(ok=True)


# --- Tipos de cita ---

@configuracion_bp.route('/tipos-cita', methods=['GET'])
@login_required
def listar_tipos():
    tipos = TipoCita.query.filter_by(activo=True).all()
    return jsonify([t.to_dict() for t in tipos])


@configuracion_bp.route('/tipos-cita', methods=['POST'])
@login_required
def crear_tipo():
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400
    if not data.get('nombre'):
        return jsonify(error='nombre requerido'), 400

    t = TipoCita(
        nombre=data['nombre'],
        duracion_minutos=data.get('duracion_minutos', 60),
        precio=data.get('precio', 0),
        descripcion=data.get('descripcion', ''),
        color=data.get('color', '#3788d8'),
        requiere_anticipo=bool(data.get('requiere_anticipo', False)),
    )
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201


@configuracion_bp.route('/tipos-cita/<int:tipo_id>', methods=['PUT'])
@login_required
def actualizar_tipo(tipo_id):
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    t = TipoCita.query.get_or_404(tipo_id)
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400
    for field in ['nombre', 'duracion_minutos', 'precio', 'descripcion', 'color', 'requiere_anticipo']:
        if field in data:
            setattr(t, field, data[field])
    db.session.commit()
    return jsonify(t.to_dict())


# --- Plantillas ---

@configuracion_bp.route('/plantillas', methods=['GET'])
@login_required
def listar_plantillas():
    plantillas = PlantillaMensaje.query.filter_by(activo=True).all()
    return jsonify([p.to_dict() for p in plantillas])


@configuracion_bp.route('/plantillas/<int:plantilla_id>', methods=['PUT'])
@login_required
def actualizar_plantilla(plantilla_id):
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    p = PlantillaMensaje.query.get_or_404(plantilla_id)
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400
    if 'contenido' in data:
        p.contenido = data['contenido']
    if 'nombre' in data:
        p.nombre = data['nombre']
    db.session.commit()
    return jsonify(p.to_dict())


# --- Origenes de paciente ---

@configuracion_bp.route('/origenes', methods=['GET'])
@login_required
def listar_origenes():
    origenes = OrigenPaciente.query.filter_by(activo=True).order_by(OrigenPaciente.nombre).all()
    return jsonify([o.to_dict() for o in origenes])


@configuracion_bp.route('/origenes', methods=['POST'])
@login_required
def crear_origen():
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        return jsonify(error='nombre requerido'), 400
    existente = OrigenPaciente.query.filter_by(nombre=nombre).first()
    if existente:
        if not existente.activo:
            existente.activo = True
            db.session.commit()
            return jsonify(existente.to_dict()), 200
        return jsonify(error='Ya existe una categoria con ese nombre'), 409
    o = OrigenPaciente(nombre=nombre)
    db.session.add(o)
    db.session.commit()
    return jsonify(o.to_dict()), 201


@configuracion_bp.route('/origenes/<int:origen_id>', methods=['PUT'])
@login_required
def actualizar_origen(origen_id):
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    o = OrigenPaciente.query.get_or_404(origen_id)
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400
    if 'nombre' in data:
        nombre = data['nombre'].strip()
        if nombre:
            o.nombre = nombre
    if 'activo' in data:
        o.activo = bool(data['activo'])
    db.session.commit()
    return jsonify(o.to_dict())


@configuracion_bp.route('/origenes/<int:origen_id>', methods=['DELETE'])
@login_required
def eliminar_origen(origen_id):
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    o = OrigenPaciente.query.get_or_404(origen_id)
    o.activo = False
    db.session.commit()
    return jsonify(ok=True)
