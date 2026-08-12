from decimal import Decimal

from flask import jsonify, request
from sqlalchemy import func

from edr.accounting_engine import estado_resultados
from edr.api import edr_api_bp
from edr.models import GastoOperativo, Ingreso, PagoDoctor
from edr.schemas import parse_mes
from extensions import db


def _sum_month(model, column, start, end, *filters):
    value = (
        db.session.query(func.coalesce(func.sum(column), 0))
        .filter(
            model.fecha >= start,
            model.fecha < end,
            model.anulado.is_(False),
            *filters,
        )
        .scalar()
    )
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def _count_month(model, start, end):
    return (
        db.session.query(func.count(model.id))
        .filter(
            model.fecha >= start,
            model.fecha < end,
            model.anulado.is_(False),
        )
        .scalar()
    )


def _decimal_json(values):
    return {
        key: float(value) if isinstance(value, Decimal) else value
        for key, value in values.items()
    }


@edr_api_bp.get('/resumen')
def resumen_mensual():
    mes, start, end = parse_mes(request.args.get('mes'))
    pnl = estado_resultados(
        ventas=_sum_month(Ingreso, Ingreso.monto, start, end),
        comisiones_bancarias=_sum_month(
            Ingreso, Ingreso.comision_bancaria, start, end
        ),
        comisiones_doctores=_sum_month(
            Ingreso, Ingreso.comision_doctor, start, end
        ),
        gastos_variables=_sum_month(
            GastoOperativo,
            GastoOperativo.monto,
            start,
            end,
            GastoOperativo.tipo == 'variable',
        ),
        gastos_fijos=_sum_month(
            GastoOperativo,
            GastoOperativo.monto,
            start,
            end,
            GastoOperativo.tipo == 'fijo',
        ),
        pagos_doctores_adicionales=_sum_month(
            PagoDoctor,
            PagoDoctor.monto,
            start,
            end,
            PagoDoctor.tipo.in_(('salario', 'otro')),
        ),
    )
    return jsonify({
        'mes': mes,
        'pnl': _decimal_json(pnl),
        'conteos': {
            'ingresos': _count_month(Ingreso, start, end),
            'gastos': _count_month(GastoOperativo, start, end),
            'pagos_doctores': _count_month(PagoDoctor, start, end),
        },
    })
