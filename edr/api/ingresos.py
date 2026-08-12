from datetime import datetime
from decimal import Decimal

from flask import jsonify, request
from flask_login import current_user
from sqlalchemy.orm import joinedload

from edr.api import edr_api_bp
from edr.audit import record_audit
from edr.models import Ingreso, MetodoPago, PagoComisionIngreso, PagoDoctor
from edr.schemas import (
    ValidationError,
    parse_mes,
    serialize_ingreso,
    validate_ingreso_payload,
)
from extensions import db
from models import Cita, Dentista, Paciente, TipoCita


def _not_found():
    return jsonify(error='No encontrado'), 404


def _relation_error(field):
    return f'No existe un registro activo para {field}.'


def _validate_relations(data):
    errors = {}
    lookups = (
        ('paciente_id', Paciente, Paciente.eliminado.is_(False)),
        ('dentista_id', Dentista, Dentista.activo.is_(True)),
        ('tipo_cita_id', TipoCita, TipoCita.activo.is_(True)),
        ('metodo_pago_id', MetodoPago, MetodoPago.activo.is_(True)),
    )
    for field, model, active_filter in lookups:
        value = data.get(field)
        if value is not None and model.query.filter(
            model.id == value, active_filter
        ).first() is None:
            errors[field] = _relation_error(field)

    cita = None
    if data.get('cita_id') is not None:
        cita = Cita.query.get(data['cita_id'])
        if cita is None:
            errors['cita_id'] = 'La cita indicada no existe.'
        else:
            expected = {
                'paciente_id': cita.paciente_id,
                'dentista_id': cita.dentista_id,
                'tipo_cita_id': cita.tipo_cita_id,
            }
            for field, value in expected.items():
                if data.get(field) != value:
                    errors[field] = 'No corresponde a la cita indicada.'
    if errors:
        raise ValidationError(errors)
    return cita


def _validate_commissions(data):
    monto = data.get('monto')
    bancaria = data.get('comision_bancaria', Decimal('0.00'))
    doctor = data.get('comision_doctor', Decimal('0.00'))
    if monto is not None and bancaria + doctor > monto:
        raise ValidationError({
            'comision_doctor': 'La suma de comisiones no puede superar el monto.'
        })


def _current_data(ingreso):
    return {
        'fecha': ingreso.fecha,
        'cita_id': ingreso.cita_id,
        'paciente_id': ingreso.paciente_id,
        'dentista_id': ingreso.dentista_id,
        'tipo_cita_id': ingreso.tipo_cita_id,
        'metodo_pago_id': ingreso.metodo_pago_id,
        'paciente_nombre': ingreso.paciente_nombre,
        'nombre_tratamiento': ingreso.nombre_tratamiento,
        'monto': ingreso.monto,
        'comision_bancaria': ingreso.comision_bancaria,
        'comision_doctor': ingreso.comision_doctor,
        'descuento_pct': ingreso.descuento_pct,
        'factura': ingreso.factura,
        'tipo_servicio': ingreso.tipo_servicio,
        'comentarios': ingreso.comentarios,
    }


def _effective_changes(ingreso, changes):
    return {
        field: value
        for field, value in changes.items()
        if getattr(ingreso, field) != value
    }


@edr_api_bp.get('/ingresos')
def listar_ingresos():
    _mes, start, end = parse_mes(request.args.get('mes'))
    query = Ingreso.query.options(
        joinedload(Ingreso.dentista),
        joinedload(Ingreso.tipo_cita),
        joinedload(Ingreso.metodo_pago),
    ).filter(Ingreso.fecha >= start, Ingreso.fecha < end)
    if request.args.get('incluir_anulados') != '1':
        query = query.filter(Ingreso.anulado.is_(False))
    rows = query.order_by(Ingreso.fecha.desc(), Ingreso.id.desc()).all()
    return jsonify([serialize_ingreso(ingreso) for ingreso in rows])


@edr_api_bp.get('/ingresos/<int:ingreso_id>')
def obtener_ingreso(ingreso_id):
    ingreso = db.session.get(Ingreso, ingreso_id)
    if ingreso is None:
        return _not_found()
    return jsonify(serialize_ingreso(ingreso))


@edr_api_bp.post('/ingresos')
def crear_ingreso():
    data = validate_ingreso_payload(request.get_json(silent=True), partial=False)
    _validate_relations(data)
    _validate_commissions(data)
    ingreso = Ingreso(**data, created_by_id=current_user.id)
    db.session.add(ingreso)
    db.session.flush()
    after = serialize_ingreso(ingreso)
    db.session.add(record_audit('crear', 'ingresos', ingreso.id, {}, after))
    db.session.commit()
    return jsonify(serialize_ingreso(ingreso)), 201


@edr_api_bp.put('/ingresos/<int:ingreso_id>')
def actualizar_ingreso(ingreso_id):
    ingreso = db.session.get(Ingreso, ingreso_id)
    if ingreso is None:
        return _not_found()
    if ingreso.anulado:
        return jsonify(
            error='ingreso_anulado',
            mensaje='Un ingreso anulado no puede modificarse.',
        ), 409
    changes = validate_ingreso_payload(
        request.get_json(silent=True), partial=True
    )
    changes = _effective_changes(ingreso, changes)
    if not changes:
        raise ValidationError({
            'payload': 'Envía al menos un campo reconocido con un cambio.'
        })
    candidate = _current_data(ingreso)
    candidate.update(changes)
    _validate_relations(candidate)
    _validate_commissions(candidate)
    before = serialize_ingreso(ingreso)
    for field, value in changes.items():
        setattr(ingreso, field, value)
    ingreso.updated_by_id = current_user.id
    db.session.flush()
    after = serialize_ingreso(ingreso)
    db.session.add(record_audit(
        'actualizar', 'ingresos', ingreso.id, before, after
    ))
    db.session.commit()
    return jsonify(serialize_ingreso(ingreso))


@edr_api_bp.delete('/ingresos/<int:ingreso_id>')
def anular_ingreso(ingreso_id):
    ingreso = db.session.get(Ingreso, ingreso_id)
    if ingreso is None:
        return _not_found()
    if ingreso.anulado:
        return jsonify(serialize_ingreso(ingreso))
    active_payment = (
        PagoComisionIngreso.query
        .join(PagoDoctor, PagoComisionIngreso.pago_id == PagoDoctor.id)
        .filter(
            PagoComisionIngreso.ingreso_id == ingreso.id,
            PagoDoctor.anulado.is_(False),
        )
        .first()
    )
    if active_payment is not None:
        return jsonify(
            error='conflicto_comision_activa',
            mensaje='El ingreso tiene una comisión activa y no puede anularse.',
        ), 409
    before = serialize_ingreso(ingreso)
    ingreso.anulado = True
    ingreso.anulado_at = datetime.utcnow()
    ingreso.anulado_por_id = current_user.id
    ingreso.updated_by_id = current_user.id
    db.session.flush()
    after = serialize_ingreso(ingreso)
    db.session.add(record_audit(
        'anular', 'ingresos', ingreso.id, before, after
    ))
    db.session.commit()
    return jsonify(serialize_ingreso(ingreso))
