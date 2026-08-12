from datetime import datetime

from flask import jsonify, request
from flask_login import current_user

from edr.api import edr_api_bp
from edr.audit import record_audit
from edr.models import GastoConcepto, GastoOperativo
from edr.schemas import (
    ValidationError,
    parse_mes,
    serialize_gasto,
    validate_gasto_payload,
)
from extensions import db


def _not_found():
    return jsonify(error='No encontrado'), 404


def _current_data(gasto):
    data = {
        'fecha': gasto.fecha,
        'concepto_id': gasto.concepto_id,
        'concepto_nombre': gasto.concepto_nombre,
        'tipo': gasto.tipo,
        'monto': gasto.monto,
    }
    if gasto.comentarios is not None:
        data['comentarios'] = gasto.comentarios
    return data


def _effective_changes(gasto, data):
    return {
        field: value
        for field, value in data.items()
        if getattr(gasto, field) != value
    }


def _validate_concept(data):
    concepto_id = data.get('concepto_id')
    if concepto_id is None:
        return
    concepto = GastoConcepto.query.filter_by(
        id=concepto_id, activo=True
    ).first()
    if concepto is None:
        raise ValidationError({
            'concepto_id': 'El concepto no existe o estÃ¡ inactivo.'
        })


@edr_api_bp.get('/gastos')
def listar_gastos():
    _mes, start, end = parse_mes(request.args.get('mes'))
    query = GastoOperativo.query.filter(
        GastoOperativo.fecha >= start,
        GastoOperativo.fecha < end,
    )
    if request.args.get('incluir_anulados') != '1':
        query = query.filter(GastoOperativo.anulado.is_(False))
    rows = query.order_by(GastoOperativo.fecha, GastoOperativo.id).all()
    return jsonify([serialize_gasto(gasto) for gasto in rows])


@edr_api_bp.post('/gastos')
def crear_gasto():
    data = validate_gasto_payload(request.get_json(silent=True), partial=False)
    _validate_concept(data)
    gasto = GastoOperativo(**data, created_by_id=current_user.id)
    db.session.add(gasto)
    db.session.flush()
    after = serialize_gasto(gasto)
    db.session.add(record_audit(
        'crear', 'gastos_operativos', gasto.id, {}, after
    ))
    db.session.commit()
    return jsonify(after), 201


@edr_api_bp.put('/gastos/<int:gasto_id>')
def actualizar_gasto(gasto_id):
    gasto = db.session.get(GastoOperativo, gasto_id)
    if gasto is None:
        return _not_found()
    if gasto.anulado:
        return jsonify(
            error='gasto_anulado',
            mensaje='Un gasto anulado no puede modificarse.',
        ), 409

    changes = validate_gasto_payload(request.get_json(silent=True), partial=True)
    candidate = _current_data(gasto)
    candidate.update(changes)
    data = validate_gasto_payload(candidate, partial=False)
    _validate_concept(data)
    changes = _effective_changes(gasto, data)
    if not changes:
        raise ValidationError({
            'payload': 'EnvÃ­a al menos un campo reconocido con un cambio.'
        })

    before = serialize_gasto(gasto)
    for field, value in changes.items():
        setattr(gasto, field, value)
    gasto.updated_by_id = current_user.id
    db.session.flush()
    after = serialize_gasto(gasto)
    db.session.add(record_audit(
        'actualizar', 'gastos_operativos', gasto.id, before, after
    ))
    db.session.commit()
    return jsonify(after)


@edr_api_bp.delete('/gastos/<int:gasto_id>')
def anular_gasto(gasto_id):
    gasto = db.session.get(GastoOperativo, gasto_id)
    if gasto is None:
        return _not_found()
    if gasto.anulado:
        return jsonify(serialize_gasto(gasto))

    before = serialize_gasto(gasto)
    gasto.anulado = True
    gasto.anulado_at = datetime.utcnow()
    gasto.anulado_por_id = current_user.id
    gasto.updated_by_id = current_user.id
    db.session.flush()
    after = serialize_gasto(gasto)
    db.session.add(record_audit(
        'anular', 'gastos_operativos', gasto.id, before, after
    ))
    db.session.commit()
    return jsonify(after)
