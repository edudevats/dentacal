from decimal import Decimal, ROUND_HALF_UP

ZERO = Decimal('0')
MONEY = Decimal('0.01')
RATIO = Decimal('0.0001')


def _d(value):
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def _money(value):
    return _d(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def costo_tratamiento(
    costo_materiales, comision_bancaria, comision_especialista, costo_consultorio
):
    return _money(
        _d(costo_materiales)
        + _d(comision_bancaria)
        + _d(comision_especialista)
        + _d(costo_consultorio)
    )


def ganancia_tratamiento(
    precio, costo_materiales, comision_bancaria, comision_especialista, costo_consultorio
):
    return _money(
        _d(precio)
        - costo_tratamiento(
            costo_materiales,
            comision_bancaria,
            comision_especialista,
            costo_consultorio,
        )
    )


def estado_resultados(
    *,
    ventas,
    comisiones_bancarias,
    comisiones_doctores,
    gastos_variables,
    gastos_fijos,
    pagos_doctores_adicionales,
):
    ventas = _d(ventas)
    gastos_variables_totales = (
        _d(comisiones_bancarias)
        + _d(comisiones_doctores)
        + _d(gastos_variables)
        + _d(pagos_doctores_adicionales)
    )
    utilidad_bruta = ventas - gastos_variables_totales
    pct_bruta = utilidad_bruta / ventas if ventas > ZERO else ZERO
    utilidad_neta = utilidad_bruta - _d(gastos_fijos)
    pct_neta = utilidad_neta / ventas if ventas > ZERO else ZERO
    equilibrio = _d(gastos_fijos) / pct_bruta if pct_bruta > ZERO else ZERO
    return {
        'ventas': _money(ventas),
        'comisiones_bancarias': _money(comisiones_bancarias),
        'comisiones_doctores': _money(comisiones_doctores),
        'gastos_variables': _money(gastos_variables),
        'gastos_fijos': _money(gastos_fijos),
        'pagos_doctores_adicionales': _money(pagos_doctores_adicionales),
        'gastos_variables_totales': _money(gastos_variables_totales),
        'utilidad_bruta': _money(utilidad_bruta),
        'pct_utilidad_bruta': pct_bruta.quantize(RATIO, rounding=ROUND_HALF_UP),
        'utilidad_neta': _money(utilidad_neta),
        'pct_utilidad': pct_neta.quantize(RATIO, rounding=ROUND_HALF_UP),
        'punto_equilibrio': _money(equilibrio),
    }
