from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from extensions import db
from models import TipoCita, PlantillaMensaje, ConfiguracionConsultorio, OrigenPaciente

configuracion_bp = Blueprint('configuracion', __name__, url_prefix='/api/configuracion')


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

    data = request.get_json(force=True)
    fields = ['nombre_consultorio', 'direccion', 'telefono', 'clabe',
              'tarjeta', 'titular_cuenta', 'google_reviews_link',
              'porcentaje_anticipo']
    for f in fields:
        if f in data:
            setattr(config, f, data[f])

    from datetime import time
    if 'horario_apertura' in data:
        h, m = data['horario_apertura'].split(':')
        config.horario_apertura = time(int(h), int(m))
    if 'horario_cierre' in data:
        h, m = data['horario_cierre'].split(':')
        config.horario_cierre = time(int(h), int(m))
    if 'precio_primera_consulta' in data:
        config.precio_primera_consulta = float(data['precio_primera_consulta'])

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
    data = request.get_json(force=True)
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
    data = request.get_json(force=True)
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
    data = request.get_json(force=True)
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
    data = request.get_json(force=True)
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
    data = request.get_json(force=True)
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
