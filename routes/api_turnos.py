from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from extensions import db, permiso_requerido
from models import TurnoRotativo, TurnoRotativoMiembro
from datetime import time, date

turnos_bp = Blueprint('turnos', __name__, url_prefix='/api/turnos')


@turnos_bp.before_request
@login_required
@permiso_requerido('calendario')
def _check_permiso():
    pass


def _parse_time(s):
    h, m = s.split(':')
    return time(int(h), int(m))


def _aplicar(turno, data):
    """Valida y aplica los campos de data al turno. Devuelve (ok, error|None)."""
    nombre = (data.get('nombre') or '').strip()
    if not nombre:
        return False, 'El nombre es requerido'
    try:
        dia_semana = int(data['dia_semana'])
    except (KeyError, ValueError, TypeError):
        return False, 'dia_semana invalido'
    if dia_semana < 0 or dia_semana > 6:
        return False, 'dia_semana debe ser 0-6'
    try:
        fecha_ancla = date.fromisoformat(data['fecha_ancla'])
    except (KeyError, ValueError, TypeError):
        return False, 'fecha_ancla invalida'
    if fecha_ancla.weekday() != dia_semana:
        return False, 'La fecha ancla debe caer en el mismo dia de la semana del turno'
    try:
        ids = [int(x) for x in (data.get('miembros') or [])]
    except (ValueError, TypeError):
        return False, 'miembros invalidos'
    if len(ids) < 2:
        return False, 'Un turno rotativo necesita al menos 2 doctores'
    if len(set(ids)) != len(ids):
        return False, 'No repitas doctores en el turno'

    # Ningun miembro debe estar en otro turno activo del mismo dia
    conflicto = (TurnoRotativo.query
                 .filter(TurnoRotativo.dia_semana == dia_semana,
                         TurnoRotativo.activo.is_(True),
                         TurnoRotativo.id != (turno.id or 0))
                 .join(TurnoRotativoMiembro)
                 .filter(TurnoRotativoMiembro.dentista_id.in_(ids))
                 .first())
    if conflicto:
        return False, f'Un doctor ya pertenece a otro turno de ese dia: {conflicto.nombre}'

    turno.nombre = nombre
    turno.dia_semana = dia_semana
    turno.hora_inicio = _parse_time(data.get('hora_inicio', '09:00'))
    turno.hora_fin = _parse_time(data.get('hora_fin', '14:00'))
    turno.fecha_ancla = fecha_ancla
    turno.activo = bool(data.get('activo', True))
    turno.miembros.clear()
    db.session.flush()
    for orden, did in enumerate(ids):
        turno.miembros.append(TurnoRotativoMiembro(dentista_id=did, orden=orden))
    return True, None


@turnos_bp.route('', methods=['GET'])
@login_required
def listar():
    turnos = TurnoRotativo.query.order_by(TurnoRotativo.nombre).all()
    return jsonify([t.to_dict() for t in turnos])


@turnos_bp.route('', methods=['POST'])
@login_required
def crear():
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON invalido'), 400
    turno = TurnoRotativo()
    ok, err = _aplicar(turno, data)
    if not ok:
        return jsonify(error=err), 400
    db.session.add(turno)
    db.session.commit()
    return jsonify(turno.to_dict()), 201


@turnos_bp.route('/<int:turno_id>', methods=['PUT'])
@login_required
def actualizar(turno_id):
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    turno = TurnoRotativo.query.get_or_404(turno_id)
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON invalido'), 400
    ok, err = _aplicar(turno, data)
    if not ok:
        return jsonify(error=err), 400
    db.session.commit()
    return jsonify(turno.to_dict())


@turnos_bp.route('/<int:turno_id>', methods=['DELETE'])
@login_required
def eliminar(turno_id):
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403
    turno = TurnoRotativo.query.get_or_404(turno_id)
    db.session.delete(turno)
    db.session.commit()
    return jsonify(ok=True)
