from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required
from models import db, TipoCita, PlantillaMensaje
from extensions import cache

bp_config = Blueprint('configuracion', __name__)


@bp_config.before_request
@login_required
def require_login():
    pass


@bp_config.route('/configuracion')
def view_configuracion():
    tipos = TipoCita.query.all()
    plantillas = PlantillaMensaje.query.all()
    return render_template('configuracion.html', tipos=tipos, plantillas=plantillas)


@bp_config.route('/tipos-cita')
def view_tipos_cita():
    """Página dedicada de gestión de tipos de cita."""
    tipos = TipoCita.query.order_by(TipoCita.nombre).all()
    return render_template('tipos_cita.html', tipos=tipos)


# ── Tipos de cita API ─────────────────────────────────────────────────────────

@bp_config.route('/api/tipos-cita', methods=['GET'])
@cache.cached(timeout=1800, key_prefix='tipos_cita')  # 30 min
def api_listar_tipos():
    return jsonify([t.to_dict() for t in TipoCita.query.order_by(TipoCita.nombre).all()])


@bp_config.route('/api/tipos-cita', methods=['POST'])
def api_crear_tipo():
    data = request.json or {}
    nombre = data.get('nombre', '').strip()
    if not nombre:
        return jsonify(error='El nombre es requerido'), 400
    if TipoCita.query.filter_by(nombre=nombre).first():
        return jsonify(error='Ya existe un tipo con ese nombre'), 409
    t = TipoCita(
        nombre=nombre,
        duracion_mins=int(data.get('duracion_mins', 30)),
        costo=float(data.get('costo', 0)),
        activo=True,
    )
    db.session.add(t)
    db.session.commit()
    cache.delete('tipos_cita')
    return jsonify(t.to_dict()), 201


@bp_config.route('/api/tipos-cita/<int:tipo_id>', methods=['PUT'])
def api_actualizar_tipo(tipo_id):
    t = TipoCita.query.get_or_404(tipo_id)
    data = request.json or {}
    if 'nombre' in data:
        nombre = data['nombre'].strip()
        if not nombre:
            return jsonify(error='El nombre es requerido'), 400
        duplicado = TipoCita.query.filter(
            TipoCita.nombre == nombre, TipoCita.id != tipo_id
        ).first()
        if duplicado:
            return jsonify(error='Ya existe un tipo con ese nombre'), 409
        t.nombre = nombre
    if 'duracion_mins' in data:
        t.duracion_mins = int(data['duracion_mins'])
    if 'costo' in data:
        t.costo = float(data['costo'])
    if 'activo' in data:
        t.activo = bool(data['activo'])
    db.session.commit()
    cache.delete('tipos_cita')
    return jsonify(t.to_dict())


@bp_config.route('/api/tipos-cita/<int:tipo_id>', methods=['DELETE'])
def api_eliminar_tipo(tipo_id):
    t = TipoCita.query.get_or_404(tipo_id)
    from models import Cita
    tiene_citas = Cita.query.filter_by(tipo_cita_id=tipo_id).first()
    if tiene_citas:
        # Desactivar en vez de eliminar si tiene citas asociadas
        t.activo = False
        db.session.commit()
        cache.delete('tipos_cita')
        return jsonify(ok=True, accion='desactivado',
                       mensaje='Tiene citas asociadas, se desactivó en lugar de eliminar')
    db.session.delete(t)
    db.session.commit()
    cache.delete('tipos_cita')
    return jsonify(ok=True, accion='eliminado')


# ── Plantillas de mensajes ────────────────────────────────────────────────────

@bp_config.route('/api/plantillas', methods=['GET'])
def api_listar_plantillas():
    return jsonify([p.to_dict() for p in PlantillaMensaje.query.all()])


@bp_config.route('/api/plantillas/<int:plantilla_id>', methods=['PUT'])
def api_actualizar_plantilla(plantilla_id):
    p = PlantillaMensaje.query.get_or_404(plantilla_id)
    data = request.json
    if 'contenido' in data:
        p.contenido = data['contenido']
    if 'activo' in data:
        p.activo = data['activo']
    db.session.commit()
    return jsonify(p.to_dict())
