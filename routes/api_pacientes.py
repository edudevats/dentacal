from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required
from models import db, Paciente, Cita
from datetime import datetime

bp_pacientes = Blueprint('pacientes', __name__)


@bp_pacientes.before_request
@login_required
def require_login():
    pass


@bp_pacientes.route('/pacientes')
def view_pacientes():
    pacientes = Paciente.query.order_by(Paciente.nombre).all()
    return render_template('pacientes.html', pacientes=pacientes)


@bp_pacientes.route('/pacientes/<int:paciente_id>')
def view_paciente(paciente_id):
    paciente = Paciente.query.get_or_404(paciente_id)
    citas = Cita.query.filter_by(paciente_id=paciente_id).order_by(Cita.fecha_inicio.desc()).all()
    return render_template('paciente_detalle.html', paciente=paciente, citas=citas)


# ── API ───────────────────────────────────────────────────────────────────────

@bp_pacientes.route('/api/pacientes', methods=['GET'])
def api_listar_pacientes():
    q = request.args.get('q', '').strip()
    query = Paciente.query
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(Paciente.nombre.ilike(like), Paciente.telefono.ilike(like))
        )
    pacientes = query.order_by(Paciente.nombre).all()
    return jsonify([p.to_dict() for p in pacientes])


@bp_pacientes.route('/api/pacientes', methods=['POST'])
def api_crear_paciente():
    data = request.json
    if not data.get('nombre') or not data.get('telefono'):
        return jsonify({'error': 'Nombre y teléfono son requeridos'}), 400

    if Paciente.query.filter_by(telefono=data['telefono']).first():
        return jsonify({'error': 'Ya existe un paciente con ese teléfono'}), 409

    fecha_nac = None
    if data.get('fecha_nacimiento'):
        try:
            fecha_nac = datetime.strptime(data['fecha_nacimiento'], '%Y-%m-%d').date()
        except ValueError:
            pass

    paciente = Paciente(
        nombre=data['nombre'],
        telefono=data['telefono'],
        email=data.get('email', ''),
        fecha_nacimiento=fecha_nac,
        nombre_escuela=data.get('nombre_escuela', ''),
        notas=data.get('notas', ''),
        estado_crm=data.get('estado_crm', 'nuevo'),
    )
    db.session.add(paciente)
    db.session.commit()
    return jsonify(paciente.to_dict()), 201


@bp_pacientes.route('/api/pacientes/<int:paciente_id>', methods=['GET'])
def api_obtener_paciente(paciente_id):
    p = Paciente.query.get_or_404(paciente_id)
    data = p.to_dict()
    data['citas'] = [c.to_dict() for c in p.citas]
    return jsonify(data)


@bp_pacientes.route('/api/pacientes/telefono/<telefono>', methods=['GET'])
def api_buscar_por_telefono(telefono):
    p = Paciente.query.filter_by(telefono=telefono).first()
    if not p:
        return jsonify({'error': 'No encontrado'}), 404
    data = p.to_dict()
    data['citas'] = [c.to_dict() for c in p.citas]
    return jsonify(data)


@bp_pacientes.route('/api/pacientes/<int:paciente_id>', methods=['PUT'])
def api_actualizar_paciente(paciente_id):
    p = Paciente.query.get_or_404(paciente_id)
    data = request.json

    for campo in ('nombre', 'email', 'nombre_escuela', 'notas', 'estado_crm'):
        if campo in data:
            setattr(p, campo, data[campo])

    if 'fecha_nacimiento' in data and data['fecha_nacimiento']:
        try:
            p.fecha_nacimiento = datetime.strptime(data['fecha_nacimiento'], '%Y-%m-%d').date()
        except ValueError:
            pass

    db.session.commit()
    return jsonify(p.to_dict())


@bp_pacientes.route('/api/pacientes/<int:paciente_id>', methods=['DELETE'])
def api_eliminar_paciente(paciente_id):
    p = Paciente.query.get_or_404(paciente_id)
    db.session.delete(p)
    db.session.commit()
    return jsonify({'ok': True})
