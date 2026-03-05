from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required
from models import Cita, Consultorio, Dentista, TipoCita
from datetime import datetime
from extensions import cache

bp_calendario = Blueprint('calendario', __name__)


@bp_calendario.before_request
@login_required
def require_login():
    pass


@bp_calendario.route('/calendario')
def view_calendario():
    dentistas = Dentista.query.filter_by(activo=True).order_by(Dentista.nombre).all()
    consultorios = Consultorio.query.filter_by(activo=True).all()
    tipos = TipoCita.query.filter_by(activo=True).order_by(TipoCita.nombre).all()
    dentistas_json = [d.to_dict() for d in dentistas]
    tipos_json = [t.to_dict() for t in tipos]
    return render_template('calendario.html',
                           dentistas=dentistas,
                           consultorios=consultorios,
                           tipos=tipos,
                           dentistas_json=dentistas_json,
                           tipos_json=tipos_json)


@bp_calendario.route('/api/calendario/eventos')
def api_eventos():
    """Devuelve eventos en formato FullCalendar con resources (consultorios)."""
    start = request.args.get('start')
    end = request.args.get('end')
    dentista_ids = request.args.getlist('dentista_id', type=int)

    q = Cita.query.filter(Cita.estado != 'cancelada')

    if start:
        try:
            q = q.filter(Cita.fecha_inicio >= datetime.fromisoformat(start.replace('Z', '')))
        except ValueError:
            pass
    if end:
        try:
            q = q.filter(Cita.fecha_fin <= datetime.fromisoformat(end.replace('Z', '')))
        except ValueError:
            pass
    if dentista_ids:
        q = q.filter(Cita.dentista_id.in_(dentista_ids))

    citas = q.all()
    eventos = []
    for c in citas:
        color = c.dentista.color if c.dentista else '#3788d8'
        estado_label = {
            'pendiente': '⏳',
            'confirmada': '✅',
            'no_asistio': '❌',
            'cancelada': '🚫',
        }.get(c.estado, '')

        eventos.append({
            'id': c.id,
            'resourceId': str(c.consultorio_id),
            'title': f"{estado_label} {c.paciente.nombre if c.paciente else 'Sin paciente'}",
            'start': c.fecha_inicio.isoformat(),
            'end': c.fecha_fin.isoformat(),
            'backgroundColor': color,
            'borderColor': color,
            'textColor': '#fff',
            'extendedProps': {
                'cita_id': c.id,
                'paciente_id': c.paciente_id,
                'paciente_nombre': c.paciente.nombre if c.paciente else '',
                'paciente_telefono': c.paciente.telefono if c.paciente else '',
                'dentista_nombre': c.dentista.nombre if c.dentista else '',
                'dentista_color': color,
                'consultorio': c.consultorio.nombre if c.consultorio else '',
                'tipo_cita': c.tipo_cita.nombre if c.tipo_cita else '',
                'estado': c.estado,
                'anticipo': c.anticipo_registrado,
                'notas': c.notas or '',
            },
        })
    return jsonify(eventos)


@bp_calendario.route('/api/calendario/resources')
@cache.cached(timeout=600, key_prefix='calendario_resources')  # 10 min
def api_resources():
    """Consultorios como resources para FullCalendar."""
    consultorios = Consultorio.query.filter_by(activo=True).all()
    return jsonify([
        {'id': str(c.id), 'title': c.nombre}
        for c in consultorios
    ])
