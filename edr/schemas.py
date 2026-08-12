import re
from datetime import date
from decimal import Decimal, InvalidOperation


class ValidationError(ValueError):
    def __init__(self, fields):
        super().__init__('validation_error')
        self.fields = fields


def _iso(value):
    return value.isoformat() if value is not None else None


def _json_number(value):
    return float(value) if value is not None else 0.0


def serialize_ingreso(ingreso):
    """Convierte un ingreso ORM a tipos seguros para JSON y auditoría."""
    return {
        'id': ingreso.id,
        'fecha': _iso(ingreso.fecha),
        'cita_id': ingreso.cita_id,
        'paciente_id': ingreso.paciente_id,
        'dentista_id': ingreso.dentista_id,
        'tipo_cita_id': ingreso.tipo_cita_id,
        'metodo_pago_id': ingreso.metodo_pago_id,
        'paciente_nombre': ingreso.paciente_nombre,
        'nombre_tratamiento': ingreso.nombre_tratamiento,
        'monto': _json_number(ingreso.monto),
        'comision_bancaria': _json_number(ingreso.comision_bancaria),
        'comision_doctor': _json_number(ingreso.comision_doctor),
        'descuento_pct': _json_number(ingreso.descuento_pct),
        'factura': bool(ingreso.factura),
        'tipo_servicio': ingreso.tipo_servicio,
        'comentarios': ingreso.comentarios,
        'anulado': bool(ingreso.anulado),
        'anulado_at': _iso(ingreso.anulado_at),
        'anulado_por_id': ingreso.anulado_por_id,
        'created_by_id': ingreso.created_by_id,
        'updated_by_id': ingreso.updated_by_id,
        'created_at': _iso(ingreso.created_at),
        'updated_at': _iso(ingreso.updated_at),
        'dentista_nombre': ingreso.dentista.nombre if ingreso.dentista else None,
        'tipo_cita_nombre': ingreso.tipo_cita.nombre if ingreso.tipo_cita else None,
        'metodo_pago_nombre': (
            ingreso.metodo_pago.nombre if ingreso.metodo_pago else None
        ),
    }


def serialize_gasto(gasto):
    """Convierte un gasto ORM a tipos seguros para JSON y auditorÃ­a."""
    return {
        'id': gasto.id,
        'fecha': _iso(gasto.fecha),
        'concepto_id': gasto.concepto_id,
        'concepto_nombre': gasto.concepto_nombre,
        'tipo': gasto.tipo,
        'monto': _json_number(gasto.monto),
        'comentarios': gasto.comentarios,
        'anulado': bool(gasto.anulado),
        'anulado_at': _iso(gasto.anulado_at),
        'anulado_por_id': gasto.anulado_por_id,
        'created_by_id': gasto.created_by_id,
        'updated_by_id': gasto.updated_by_id,
        'created_at': _iso(gasto.created_at),
        'updated_at': _iso(gasto.updated_at),
    }


def serialize_pago(pago):
    """Convierte un pago a tipos seguros para JSON y auditoría."""
    return {
        'id': pago.id,
        'fecha': _iso(pago.fecha),
        'dentista_id': pago.dentista_id,
        'dentista_nombre': pago.dentista.nombre if pago.dentista else None,
        'concepto': pago.concepto,
        'tipo': pago.tipo,
        'monto': _json_number(pago.monto),
        'descuento_saldo': _json_number(pago.descuento_saldo),
        'anulado': bool(pago.anulado),
        'anulado_at': _iso(pago.anulado_at),
        'anulado_por_id': pago.anulado_por_id,
        'created_by_id': pago.created_by_id,
        'updated_by_id': pago.updated_by_id,
        'created_at': _iso(pago.created_at),
        'updated_at': _iso(pago.updated_at),
    }


def parse_mes(mes, today=None):
    today = today or date.today()
    if mes is None or mes == '':
        mes = f'{today.year:04d}-{today.month:02d}'
    if not re.fullmatch(r'\d{4}-\d{2}', str(mes)):
        raise ValidationError({'mes': 'Usa el formato YYYY-MM con un mes válido.'})
    year, month = map(int, str(mes).split('-'))
    if (
        year < 1
        or year > 9999
        or month < 1
        or month > 12
        or (year == 9999 and month == 12)
    ):
        raise ValidationError({'mes': 'Usa el formato YYYY-MM con un mes válido.'})
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return str(mes), start, end


def parse_money(value, field, *, positive=False, default=None):
    if value is None and default is not None:
        value = default
    if isinstance(value, bool):
        raise ValidationError({field: 'Debe ser un importe válido.'})
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError({field: 'Debe ser un importe válido.'})
    if not parsed.is_finite() or parsed.as_tuple().exponent < -2:
        raise ValidationError({field: 'Usa como máximo dos decimales.'})
    if positive and parsed <= 0:
        raise ValidationError({field: 'Debe ser mayor que cero.'})
    if not positive and parsed < 0:
        raise ValidationError({field: 'No puede ser negativo.'})
    return parsed.quantize(Decimal('0.01'))


def _text(payload, field, errors, *, required=False, max_length=200):
    if field not in payload:
        if required:
            errors[field] = 'Este campo es requerido.'
        return None
    value = str(payload.get(field) or '').strip()
    if required and not value:
        errors[field] = 'Este campo es requerido.'
    elif len(value) > max_length:
        errors[field] = f'Usa como máximo {max_length} caracteres.'
    return value


def _date(payload, field, errors, *, required=False):
    if field not in payload:
        if required:
            errors[field] = 'Este campo es requerido.'
        return None
    try:
        value = str(payload[field])
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        errors[field] = 'Usa una fecha válida en formato YYYY-MM-DD.'
        return None


def _optional_id(payload, field, errors):
    if field not in payload or payload[field] is None:
        return None
    if type(payload[field]) is not int:
        errors[field] = 'Debe ser un identificador entero.'
        return None
    value = payload[field]
    if value <= 0:
        errors[field] = 'Debe ser un identificador entero positivo.'
    return value


def _money_field(payload, field, errors, *, required=False, positive=False, default=None):
    if field not in payload:
        if required:
            errors[field] = 'Este campo es requerido.'
        return default
    try:
        return parse_money(payload[field], field, positive=positive, default=default)
    except ValidationError as error:
        errors.update(error.fields)
        return default


def validate_ingreso_payload(payload, partial=False):
    if not isinstance(payload, dict):
        raise ValidationError({'payload': 'Envía un objeto JSON válido.'})
    errors, data = {}, {}
    required = not partial
    for field in ('fecha',):
        value = _date(payload, field, errors, required=required)
        if value is not None:
            data[field] = value
    for field in ('paciente_nombre', 'nombre_tratamiento'):
        value = _text(payload, field, errors, required=required)
        if value is not None:
            data[field] = value
    for field in (
        'cita_id',
        'paciente_id',
        'dentista_id',
        'tipo_cita_id',
        'metodo_pago_id',
    ):
        value = _optional_id(payload, field, errors)
        if field in payload or (field == 'metodo_pago_id' and required):
            if field == 'metodo_pago_id' and value is None and field not in errors:
                errors[field] = 'Este campo es requerido.'
            data[field] = value
    for field, positive, default in (
        ('monto', True, None),
        ('comision_bancaria', False, Decimal('0.00')),
        ('comision_doctor', False, Decimal('0.00')),
        ('descuento_pct', False, Decimal('0.00')),
    ):
        value = _money_field(
            payload,
            field,
            errors,
            required=required and field == 'monto',
            positive=positive,
            default=default,
        )
        if field in payload or (required and default is not None):
            data[field] = value
    if data.get('descuento_pct', Decimal('0')) > Decimal('100'):
        errors['descuento_pct'] = 'Debe estar entre 0 y 100.'
    if data.get('monto') is not None:
        commissions = data.get('comision_bancaria', Decimal('0')) + data.get(
            'comision_doctor', Decimal('0')
        )
        if commissions > data['monto']:
            errors['comision_doctor'] = (
                'La suma de comisiones no puede superar el monto.'
            )
    if 'tipo_servicio' in payload or required:
        tipo = payload.get('tipo_servicio', 'clinico')
        if tipo not in ('clinico', 'estetico'):
            errors['tipo_servicio'] = 'Usa clinico o estetico.'
        else:
            data['tipo_servicio'] = tipo
    if 'factura' in payload or required:
        factura = payload.get('factura', False)
        if not isinstance(factura, bool):
            errors['factura'] = 'Debe ser un booleano JSON.'
        else:
            data['factura'] = factura
    if 'comentarios' in payload:
        data['comentarios'] = _text(payload, 'comentarios', errors, max_length=5000)
    if errors:
        raise ValidationError(errors)
    return data


def validate_gasto_payload(payload, partial=False):
    if not isinstance(payload, dict):
        raise ValidationError({'payload': 'EnvÃ­a un objeto JSON vÃ¡lido.'})
    if not payload and partial:
        raise ValidationError({
            'payload': 'EnvÃ­a al menos un campo reconocido con un cambio.'
        })
    allowed = {
        'fecha', 'concepto_id', 'concepto_nombre', 'tipo', 'monto',
        'comentarios',
    }
    if set(payload) - allowed:
        raise ValidationError({
            'payload': 'EnvÃ­a Ãºnicamente campos reconocidos.'
        })
    errors, data = {}, {}
    required = not partial
    if not payload:
        errors['payload'] = 'EnvÃ­a al menos un campo reconocido con un cambio.'
    fecha = _date(payload, 'fecha', errors, required=required)
    if fecha is not None:
        data['fecha'] = fecha
    if 'concepto_nombre' not in payload:
        if required:
            errors['concepto_nombre'] = 'Este campo es requerido.'
    elif not isinstance(payload['concepto_nombre'], str):
        errors['concepto_nombre'] = 'Debe ser texto.'
    else:
        concepto = payload['concepto_nombre'].strip()
        if not concepto:
            errors['concepto_nombre'] = 'Este campo es requerido.'
        elif len(concepto) > 200:
            errors['concepto_nombre'] = 'Usa como mÃ¡ximo 200 caracteres.'
        else:
            data['concepto_nombre'] = concepto
    if 'concepto_id' in payload:
        data['concepto_id'] = _optional_id(payload, 'concepto_id', errors)
    if 'tipo' in payload or required:
        tipo = payload.get('tipo', 'fijo')
        if tipo not in ('fijo', 'variable'):
            errors['tipo'] = 'Usa fijo o variable.'
        else:
            data['tipo'] = tipo
    monto = _money_field(payload, 'monto', errors, required=required, positive=True)
    if monto is not None:
        data['monto'] = monto
    if 'comentarios' in payload:
        if payload['comentarios'] is None:
            data['comentarios'] = None
        elif not isinstance(payload['comentarios'], str):
            errors['comentarios'] = 'Debe ser texto.'
        else:
            data['comentarios'] = _text(
                payload, 'comentarios', errors, max_length=5000
            )
    if errors:
        raise ValidationError(errors)
    return data


def validate_pago_payload(payload, partial=False):
    if not isinstance(payload, dict):
        raise ValidationError({'payload': 'Envía un objeto JSON válido.'})
    allowed = {
        'fecha', 'dentista_id', 'concepto', 'tipo', 'monto',
        'descuento_saldo',
    }
    if set(payload) - allowed:
        raise ValidationError({
            'payload': 'Envía únicamente campos reconocidos.'
        })
    if not payload and partial:
        raise ValidationError({
            'payload': 'Envía al menos un campo reconocido con un cambio.'
        })
    errors, data = {}, {}
    required = not partial
    if not payload:
        errors['payload'] = 'Envía los datos del pago.'
    fecha = _date(payload, 'fecha', errors, required=required)
    if fecha is not None:
        data['fecha'] = fecha
    if 'concepto' not in payload:
        if required:
            errors['concepto'] = 'Este campo es requerido.'
    elif not isinstance(payload['concepto'], str):
        errors['concepto'] = 'Debe ser texto.'
    else:
        concepto = payload['concepto'].strip()
        if not concepto:
            errors['concepto'] = 'Este campo es requerido.'
        elif len(concepto) > 200:
            errors['concepto'] = 'Usa como máximo 200 caracteres.'
        else:
            data['concepto'] = concepto
    dentista_id = _optional_id(payload, 'dentista_id', errors)
    if 'dentista_id' in payload or required:
        if dentista_id is None and 'dentista_id' not in errors:
            errors['dentista_id'] = 'Este campo es requerido.'
        data['dentista_id'] = dentista_id
    if 'tipo' in payload or required:
        tipo = payload.get('tipo')
        if tipo not in ('salario', 'otro'):
            errors['tipo'] = 'Usa salario u otro.'
        else:
            data['tipo'] = tipo
    monto = _money_field(payload, 'monto', errors, required=required, positive=True)
    if monto is not None:
        data['monto'] = monto
    descuento = _money_field(
        payload, 'descuento_saldo', errors, default=Decimal('0.00')
    )
    if 'descuento_saldo' in payload or required:
        data['descuento_saldo'] = descuento
    if errors:
        raise ValidationError(errors)
    return data


def validate_comision_pago_payload(payload):
    if not isinstance(payload, dict):
        raise ValidationError({'payload': 'Envía un objeto JSON válido.'})
    allowed = {'dentista_id', 'fecha', 'ingreso_ids'}
    if set(payload) - allowed:
        raise ValidationError({
            'payload': 'Envía únicamente campos reconocidos.'
        })
    if not payload:
        raise ValidationError({
            'payload': 'Envía los datos de la liquidación.'
        })

    errors, data = {}, {}
    fecha = _date(payload, 'fecha', errors, required=True)
    if fecha is not None:
        data['fecha'] = fecha
    dentista_id = _optional_id(payload, 'dentista_id', errors)
    if dentista_id is None and 'dentista_id' not in errors:
        errors['dentista_id'] = 'Este campo es requerido.'
    elif dentista_id is not None:
        data['dentista_id'] = dentista_id

    raw_ids = payload.get('ingreso_ids')
    ids = []
    if not isinstance(raw_ids, list) or not raw_ids:
        errors['ingreso_ids'] = 'Selecciona ingresos únicos.'
    else:
        for value in raw_ids:
            if type(value) is not int or value <= 0:
                errors['ingreso_ids'] = 'Selecciona ingresos válidos.'
                break
            ids.append(value)
        if 'ingreso_ids' not in errors and len(ids) != len(set(ids)):
            errors['ingreso_ids'] = 'Selecciona ingresos únicos.'
    if 'ingreso_ids' not in errors:
        data['ingreso_ids'] = ids
    if errors:
        raise ValidationError(errors)
    return data
