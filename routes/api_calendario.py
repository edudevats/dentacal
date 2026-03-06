from flask import Blueprint, jsonify, request
from flask_login import login_required
from models import Cita, Consultorio, EstatusCita
from datetime import datetime

calendario_bp = Blueprint('calendario', __name__, url_prefix='/api/calendario')


@calendario_bp.route('/eventos', methods=['GET'])
@login_required
def eventos():
    """Retorna eventos en formato FullCalendar con resourceId."""
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    dentista_id = request.args.get('dentista_id', type=int)
    consultorio_id = request.args.get('consultorio_id', type=int)

    if not start_str or not end_str:
        return jsonify(error='start y end son requeridos'), 400

    try:
        # FullCalendar envia fechas en formato ISO (puede tener timezone)
        start = _parse_dt(start_str)
        end = _parse_dt(end_str)
    except ValueError:
        return jsonify(error='Formato de fecha invalido'), 400

    q = Cita.query.filter(
        Cita.fecha_inicio < end,
        Cita.fecha_fin > start,
        Cita.status != EstatusCita.cancelada,
        Cita.paciente.has(eliminado=False),
    )

    if dentista_id:
        q = q.filter_by(dentista_id=dentista_id)
    if consultorio_id:
        q = q.filter_by(consultorio_id=consultorio_id)

    citas = q.all()
    return jsonify([c.to_calendar_event() for c in citas])


@calendario_bp.route('/recursos', methods=['GET'])
@login_required
def recursos():
    """Retorna los 3 consultorios como resources para FullCalendar."""
    consultorios = Consultorio.query.filter_by(activo=True).order_by(Consultorio.id).all()
    return jsonify([c.to_dict() for c in consultorios])


def _parse_dt(s):
    """Parsea datetime ISO, removiendo timezone info para comparar con DB (UTC naive)."""
    # Remover timezone suffix si existe
    if s.endswith('Z'):
        s = s[:-1]
    elif '+' in s[10:]:
        s = s[:s.rfind('+')]
    elif s.count('-') > 2:
        # ISO con offset negativo ej 2026-03-10T00:00:00-06:00
        s = s[:19]
    return datetime.fromisoformat(s[:19])
