from datetime import datetime, time

from flask import jsonify, request
from sqlalchemy import or_
from sqlalchemy.orm import contains_eager

from edr.api import edr_api_bp
from edr.models import GastoConcepto, MetodoPago
from edr.schemas import parse_mes
from models import Cita, Dentista, Paciente, TipoCita


def _literal_like_pattern(value):
    escaped = value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


@edr_api_bp.get('/catalogos')
def catalogos():
    return jsonify({
        'dentistas': [
            dentista.to_dict()
            for dentista in Dentista.query.filter_by(activo=True)
            .order_by(Dentista.nombre)
        ],
        'tipos_cita': [
            tipo.to_dict()
            for tipo in TipoCita.query.filter_by(activo=True)
            .order_by(TipoCita.nombre)
        ],
        'metodos_pago': [
            {'id': metodo.id, 'nombre': metodo.nombre}
            for metodo in MetodoPago.query.filter_by(activo=True)
            .order_by(MetodoPago.nombre)
        ],
        'gastos_conceptos': [
            {
                'id': concepto.id,
                'nombre': concepto.nombre,
                'tipo_default': concepto.tipo_default,
            }
            for concepto in GastoConcepto.query.filter_by(activo=True)
            .order_by(GastoConcepto.nombre)
        ],
    })


@edr_api_bp.get('/pacientes')
def buscar_pacientes():
    query = (request.args.get('q') or '').strip()
    if len(query) < 2:
        return jsonify([])
    rows = (
        Paciente.query
        .filter(
            Paciente.eliminado.is_(False),
            Paciente.nombre.ilike(_literal_like_pattern(query), escape='\\'),
        )
        .order_by(Paciente.nombre)
        .limit(20)
        .all()
    )
    return jsonify([
        {'id': paciente.id, 'nombre': paciente.nombre_completo}
        for paciente in rows
    ])


def _serialize_cita(cita):
    tipo = cita.tipo_cita
    return {
        'id': cita.id,
        'fecha': cita.fecha_inicio.date().isoformat(),
        'fecha_inicio': cita.fecha_inicio.isoformat(),
        'paciente_id': cita.paciente_id,
        'paciente_nombre': cita.paciente.nombre_completo,
        'dentista_id': cita.dentista_id,
        'dentista_nombre': cita.dentista.nombre,
        'tipo_cita_id': cita.tipo_cita_id,
        'nombre_tratamiento': tipo.nombre if tipo else '',
        'monto': float(tipo.precio) if tipo and tipo.precio is not None else 0.0,
    }


@edr_api_bp.get('/citas')
def buscar_citas():
    query = (request.args.get('q') or '').strip()
    _mes, start, end = parse_mes(request.args.get('mes'))
    start_at = datetime.combine(start, time.min)
    end_at = datetime.combine(end, time.min)
    rows = (
        Cita.query
        .join(Paciente, Cita.paciente_id == Paciente.id)
        .join(Dentista, Cita.dentista_id == Dentista.id)
        .outerjoin(TipoCita, Cita.tipo_cita_id == TipoCita.id)
        .options(
            contains_eager(Cita.paciente),
            contains_eager(Cita.dentista),
            contains_eager(Cita.tipo_cita),
        )
        .filter(Cita.fecha_inicio >= start_at, Cita.fecha_inicio < end_at)
    )
    if query:
        pattern = _literal_like_pattern(query)
        rows = rows.filter(or_(
            Paciente.nombre.ilike(pattern, escape='\\'),
            TipoCita.nombre.ilike(pattern, escape='\\'),
        ))
    rows = rows.order_by(Cita.fecha_inicio.desc(), Cita.id.desc()).limit(30).all()
    return jsonify([_serialize_cita(cita) for cita in rows])
