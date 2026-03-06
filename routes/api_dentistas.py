from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from extensions import db
from models import Dentista, HorarioDentista, BloqueoDentista
from datetime import time, datetime

dentistas_bp = Blueprint('dentistas', __name__, url_prefix='/api/dentistas')


@dentistas_bp.route('', methods=['GET'])
@login_required
def listar():
    solo_activos = request.args.get('activos', 'true').lower() == 'true'
    q = Dentista.query
    if solo_activos:
        q = q.filter_by(activo=True)
    dentistas = q.order_by(Dentista.nombre).all()
    return jsonify([d.to_dict() for d in dentistas])


@dentistas_bp.route('/<int:dentista_id>', methods=['GET'])
@login_required
def detalle(dentista_id):
    d = Dentista.query.get_or_404(dentista_id)
    data = d.to_dict()
    data['horarios'] = [
        {'dia_semana': h.dia_semana,
         'hora_inicio': h.hora_inicio.strftime('%H:%M'),
         'hora_fin': h.hora_fin.strftime('%H:%M'),
         'activo': h.activo}
        for h in d.horarios
    ]
    return jsonify(data)


@dentistas_bp.route('', methods=['POST'])
@login_required
def crear():
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    data = request.get_json(force=True)
    if not data.get('nombre'):
        return jsonify(error='El nombre es requerido'), 400

    d = Dentista(
        nombre=data['nombre'],
        especialidad=data.get('especialidad', ''),
        color=data.get('color', '#3788d8'),
        telefono=data.get('telefono', ''),
        email=data.get('email', ''),
    )
    db.session.add(d)
    db.session.flush()

    # Horario por defecto L-V 9-18
    for dia in range(5):
        db.session.add(HorarioDentista(
            dentista_id=d.id, dia_semana=dia,
            hora_inicio=time(9, 0), hora_fin=time(18, 0)
        ))

    db.session.commit()
    return jsonify(d.to_dict()), 201


@dentistas_bp.route('/<int:dentista_id>', methods=['PUT'])
@login_required
def actualizar(dentista_id):
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    d = Dentista.query.get_or_404(dentista_id)
    data = request.get_json(force=True)

    if 'nombre' in data:
        d.nombre = data['nombre']
    if 'especialidad' in data:
        d.especialidad = data['especialidad']
    if 'color' in data:
        d.color = data['color']
    if 'telefono' in data:
        d.telefono = data['telefono']
    if 'email' in data:
        d.email = data['email']
    if 'activo' in data:
        d.activo = bool(data['activo'])

    # Actualizar horarios si vienen
    if 'horarios' in data:
        for h_data in data['horarios']:
            dia = h_data.get('dia_semana')
            horario = HorarioDentista.query.filter_by(
                dentista_id=d.id, dia_semana=dia).first()
            if not horario:
                horario = HorarioDentista(dentista_id=d.id, dia_semana=dia)
                db.session.add(horario)
            horario.hora_inicio = _parse_time(h_data.get('hora_inicio', '09:00'))
            horario.hora_fin = _parse_time(h_data.get('hora_fin', '18:00'))
            horario.activo = h_data.get('activo', True)

    db.session.commit()
    return jsonify(d.to_dict())


@dentistas_bp.route('/<int:dentista_id>', methods=['DELETE'])
@login_required
def eliminar(dentista_id):
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    d = Dentista.query.get_or_404(dentista_id)
    d.activo = False  # soft delete
    db.session.commit()
    return jsonify(ok=True)


@dentistas_bp.route('/<int:dentista_id>/bloqueos', methods=['POST'])
@login_required
def crear_bloqueo(dentista_id):
    Dentista.query.get_or_404(dentista_id)
    data = request.get_json(force=True)
    try:
        inicio = datetime.fromisoformat(data['fecha_inicio'])
        fin = datetime.fromisoformat(data['fecha_fin'])
    except (KeyError, ValueError):
        return jsonify(error='Fechas invalidas'), 400

    bloqueo = BloqueoDentista(
        dentista_id=dentista_id,
        fecha_inicio=inicio,
        fecha_fin=fin,
        motivo=data.get('motivo', ''),
    )
    db.session.add(bloqueo)
    db.session.commit()
    return jsonify(id=bloqueo.id), 201


def _parse_time(s):
    h, m = s.split(':')
    return time(int(h), int(m))
