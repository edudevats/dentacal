from datetime import datetime
from decimal import Decimal

from flask import jsonify, request
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from edr.api import edr_api_bp
from edr.audit import record_audit
from edr.models import Ingreso, PagoComisionIngreso, PagoDoctor
from edr.schemas import (
    ValidationError,
    parse_mes,
    serialize_pago,
    validate_comision_pago_payload,
    validate_pago_payload,
)
from extensions import db
from models import Dentista


def _not_found():
    return jsonify(error='No encontrado'), 404


def _payment_query():
    return PagoDoctor.query.options(joinedload(PagoDoctor.dentista))


# Lock order for every commission mutation is global and deterministic:
# Dentista.id -> PagoDoctor.id -> Ingreso.id -> PagoComisionIngreso.id.
# Lock queries intentionally contain no eager loader joins.
def _locked_dentist_query(dentista_id):
    return (
        Dentista.query.filter(Dentista.id == dentista_id)
        .order_by(Dentista.id)
        .with_for_update()
        .populate_existing()
    )


def _locked_active_dentist_query(dentista_id):
    return _locked_dentist_query(dentista_id).filter(Dentista.activo.is_(True))


def _locked_payment_rows_query(pago_ids):
    return (
        PagoDoctor.query.filter(PagoDoctor.id.in_(sorted(set(pago_ids))))
        .order_by(PagoDoctor.id)
        .with_for_update()
        .populate_existing()
    )


def _locked_payment_query(pago_id):
    return _locked_payment_rows_query([pago_id])


def _locked_income_query(ids):
    return (
        Ingreso.query.filter(Ingreso.id.in_(sorted(set(ids))))
        .order_by(Ingreso.id)
        .with_for_update()
        .populate_existing()
    )


def _locked_pivot_query(*, ingreso_ids=None, pago_ids=None):
    query = PagoComisionIngreso.query
    if ingreso_ids is not None:
        query = query.filter(
            PagoComisionIngreso.ingreso_id.in_(sorted(set(ingreso_ids)))
        )
    if pago_ids is not None:
        query = query.filter(
            PagoComisionIngreso.pago_id.in_(sorted(set(pago_ids)))
        )
    return (
        query.order_by(PagoComisionIngreso.id)
        .with_for_update()
        .populate_existing()
    )


def _parse_filter_id(value, field):
    if value in (None, ''):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError({field: 'Debe ser un identificador entero.'})
    if parsed <= 0 or str(value).strip() != str(parsed):
        raise ValidationError({field: 'Debe ser un identificador entero positivo.'})
    return parsed


def _validate_active_dentist(dentista_id):
    dentist = Dentista.query.filter_by(id=dentista_id, activo=True).first()
    if dentist is None:
        raise ValidationError({
            'dentista_id': 'El dentista no existe o está inactivo.'
        })
    return dentist


def _current_data(pago):
    return {
        'fecha': pago.fecha,
        'dentista_id': pago.dentista_id,
        'concepto': pago.concepto,
        'tipo': pago.tipo,
        'monto': pago.monto,
        'descuento_saldo': pago.descuento_saldo,
    }


def _effective_changes(pago, data):
    return {
        field: value
        for field, value in data.items()
        if getattr(pago, field) != value
    }


@edr_api_bp.get('/pagos-doctores')
def listar_pagos():
    _mes, start, end = parse_mes(request.args.get('mes'))
    dentista_id = _parse_filter_id(
        request.args.get('dentista_id'), 'dentista_id'
    )
    query = _payment_query().filter(
        PagoDoctor.fecha >= start,
        PagoDoctor.fecha < end,
    )
    if request.args.get('incluir_anulados') != '1':
        query = query.filter(PagoDoctor.anulado.is_(False))
    if dentista_id is not None:
        query = query.filter(PagoDoctor.dentista_id == dentista_id)
    rows = query.order_by(PagoDoctor.fecha.desc(), PagoDoctor.id.desc()).all()
    return jsonify([serialize_pago(pago) for pago in rows])


@edr_api_bp.get('/pagos-doctores/<int:pago_id>')
def obtener_pago(pago_id):
    pago = _payment_query().filter(PagoDoctor.id == pago_id).first()
    if pago is None:
        return _not_found()
    return jsonify(serialize_pago(pago))


@edr_api_bp.post('/pagos-doctores')
def crear_pago():
    data = validate_pago_payload(request.get_json(silent=True), partial=False)
    _validate_active_dentist(data['dentista_id'])
    pago = PagoDoctor(**data, created_by_id=current_user.id)
    db.session.add(pago)
    db.session.flush()
    after = serialize_pago(pago)
    db.session.add(record_audit(
        'crear', 'pagos_doctores', pago.id, {}, after
    ))
    db.session.commit()
    return jsonify(after), 201


@edr_api_bp.put('/pagos-doctores/<int:pago_id>')
def actualizar_pago(pago_id):
    pago = _locked_payment_query(pago_id).first()
    if pago is None:
        return _not_found()
    if pago.anulado:
        return jsonify(
            error='pago_anulado',
            mensaje='Un pago anulado no puede modificarse.',
        ), 409
    if pago.tipo == 'comision':
        return jsonify(
            error='pago_comision_inmutable',
            mensaje='Los pagos de comisión se derivan de sus ingresos.',
        ), 409

    changes = validate_pago_payload(
        request.get_json(silent=True), partial=True
    )
    candidate = _current_data(pago)
    candidate.update(changes)
    data = validate_pago_payload(candidate, partial=False)
    _validate_active_dentist(data['dentista_id'])
    changes = _effective_changes(pago, data)
    if not changes:
        raise ValidationError({
            'payload': 'Envía al menos un campo reconocido con un cambio.'
        })

    before = serialize_pago(pago)
    for field, value in changes.items():
        setattr(pago, field, value)
    pago.updated_by_id = current_user.id
    db.session.flush()
    after = serialize_pago(pago)
    db.session.add(record_audit(
        'actualizar', 'pagos_doctores', pago.id, before, after
    ))
    db.session.commit()
    return jsonify(after)


@edr_api_bp.delete('/pagos-doctores/<int:pago_id>')
def anular_pago(pago_id):
    payment_ref = db.session.query(PagoDoctor.dentista_id).filter(
        PagoDoctor.id == pago_id
    ).first()
    if payment_ref is None:
        return _not_found()
    _locked_dentist_query(payment_ref.dentista_id).first()
    pago = _locked_payment_query(pago_id).first()
    if pago is None:
        return _not_found()

    pivots = []
    if pago.tipo == 'comision':
        ingreso_ids = [
            row.ingreso_id
            for row in db.session.query(PagoComisionIngreso.ingreso_id)
            .filter(PagoComisionIngreso.pago_id == pago.id)
            .order_by(PagoComisionIngreso.ingreso_id)
            .all()
        ]
        if ingreso_ids:
            _locked_income_query(ingreso_ids).all()
        pivots = _locked_pivot_query(pago_ids=[pago.id]).all()

    if pago.anulado:
        if pivots:
            for pivot in pivots:
                db.session.delete(pivot)
            db.session.flush()
            db.session.commit()
        return jsonify(serialize_pago(pago))

    before = serialize_pago(pago)
    for pivot in pivots:
        db.session.delete(pivot)
    pago.anulado = True
    pago.anulado_at = datetime.utcnow()
    pago.anulado_por_id = current_user.id
    pago.updated_by_id = current_user.id
    db.session.flush()
    after = serialize_pago(pago)
    db.session.add(record_audit(
        'anular', 'pagos_doctores', pago.id, before, after
    ))
    db.session.commit()
    return jsonify(after)


@edr_api_bp.get('/comisiones/pendientes')
def listar_comisiones_pendientes():
    dentista_id = _parse_filter_id(
        request.args.get('dentista_id'), 'dentista_id'
    )
    liquidated = (
        select(PagoComisionIngreso.ingreso_id)
        .join(PagoDoctor, PagoComisionIngreso.pago_id == PagoDoctor.id)
        .where(PagoDoctor.anulado.is_(False))
    )
    query = (
        Ingreso.query.options(joinedload(Ingreso.dentista))
        .join(Dentista, Ingreso.dentista_id == Dentista.id)
        .filter(
            Ingreso.anulado.is_(False),
            Ingreso.comision_doctor > 0,
            Ingreso.dentista_id.isnot(None),
            Dentista.activo.is_(True),
            ~Ingreso.id.in_(liquidated),
        )
    )
    if dentista_id is not None:
        query = query.filter(Ingreso.dentista_id == dentista_id)
    ingresos = query.order_by(
        Dentista.nombre, Ingreso.dentista_id, Ingreso.fecha, Ingreso.id
    ).all()

    groups = {}
    total = Decimal('0.00')
    for ingreso in ingresos:
        group = groups.setdefault(ingreso.dentista_id, {
            'dentista_id': ingreso.dentista_id,
            'dentista_nombre': ingreso.dentista.nombre,
            'total_pendiente': Decimal('0.00'),
            'comisiones': [],
        })
        commission = ingreso.comision_doctor
        group['total_pendiente'] += commission
        total += commission
        group['comisiones'].append({
            'ingreso_id': ingreso.id,
            'fecha': ingreso.fecha.isoformat(),
            'paciente_nombre': ingreso.paciente_nombre,
            'nombre_tratamiento': ingreso.nombre_tratamiento,
            'monto': float(ingreso.monto),
            'comision_doctor': float(commission),
        })
    doctors = list(groups.values())
    for group in doctors:
        group['total_pendiente'] = float(group['total_pendiente'])
    return jsonify(
        total_pendiente=float(total),
        doctores=doctors,
    )


@edr_api_bp.post('/comisiones/pagar')
def pagar_comisiones():
    data = validate_comision_pago_payload(request.get_json(silent=True))
    dentista_id = data['dentista_id']
    ids = data['ingreso_ids']
    if _locked_active_dentist_query(dentista_id).first() is None:
        return jsonify(error='comision_no_disponible'), 409

    linked_payment_ids = [
        row.pago_id
        for row in db.session.query(PagoComisionIngreso.pago_id)
        .filter(PagoComisionIngreso.ingreso_id.in_(ids))
        .order_by(PagoComisionIngreso.pago_id)
        .all()
    ]
    linked_payments = (
        _locked_payment_rows_query(linked_payment_ids).all()
        if linked_payment_ids
        else []
    )
    ingresos = _locked_income_query(ids).all()
    pivots = _locked_pivot_query(ingreso_ids=ids).all()
    payments_by_id = {payment.id: payment for payment in linked_payments}
    active_or_incoherent_link = any(
        pivot.pago_id not in payments_by_id
        or not payments_by_id[pivot.pago_id].anulado
        for pivot in pivots
    )
    invalid = (
        len(ingresos) != len(ids)
        or any(
            ingreso.anulado
            or ingreso.dentista_id != dentista_id
            or ingreso.comision_doctor <= 0
            for ingreso in ingresos
        )
        or active_or_incoherent_link
    )
    if invalid:
        return jsonify(error='comision_no_disponible'), 409

    total = sum(
        (ingreso.comision_doctor for ingreso in ingresos),
        Decimal('0.00'),
    )
    pago = PagoDoctor(
        fecha=data['fecha'],
        dentista_id=dentista_id,
        concepto=f'Pago de {len(ingresos)} comisión(es)',
        tipo='comision',
        monto=total,
        descuento_saldo=Decimal('0.00'),
        created_by_id=current_user.id,
    )
    try:
        for pivot in pivots:
            db.session.delete(pivot)
        if pivots:
            # The unique ingreso_id guard requires residual DELETEs to reach
            # the database before replacement INSERTs are staged.
            db.session.flush()
        db.session.add(pago)
        db.session.flush()
        db.session.add_all([
            PagoComisionIngreso(
                pago_id=pago.id,
                ingreso_id=ingreso.id,
                monto=ingreso.comision_doctor,
            )
            for ingreso in ingresos
        ])
        db.session.flush()
        result = serialize_pago(pago)
        db.session.add(record_audit(
            'crear', 'pagos_doctores', pago.id, {}, result
        ))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error='comision_ya_liquidada'), 409
    return jsonify(result), 201
