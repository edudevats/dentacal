"""
Envios manuales a doctores desde Configuracion -> Doctores.

El job de las 21:00 (`_job_resumen_doctores`) manda solo el resumen del dia
siguiente y solo si hay citas. Aqui viven las tres versiones a demanda que
dispara recepcion: horario de la semana, citas de un dia y citas de la semana.

Cada una arma el texto y lo manda con su propia plantilla, para que el dia que
se registren en Twilio se les pueda pegar el ContentSid desde la pantalla de
Plantillas. Sin ContentSid salen como texto libre: WhatsApp solo las entrega
si el doctor escribio en las ultimas 24 h (error 63016).
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DIAS = ('Lunes', 'Martes', 'Miercoles', 'Jueves', 'Viernes', 'Sabado', 'Domingo')

# Cuantos dias cubren "la semana" del horario y del resumen semanal, contando
# desde el dia que recepcion aprieta el boton.
DIAS_SEMANA = 7

# Meta no acepta saltos de linea dentro del valor de una variable de plantilla:
# Twilio rechaza el envio con el error 21656 antes de siquiera intentarlo. Por
# eso las citas de un mismo dia van en un solo renglon separadas por esto, y
# cada dia viaja en su propia variable ({{3}} a {{9}}) para que los saltos de
# linea los ponga el CUERPO de la plantilla, que si los admite.
SEPARADOR_CITAS = ' · '
SIN_CITAS = 'sin citas'


class EnvioDoctorError(Exception):
    """No hay nada que mandar, o no hay a donde mandarlo. Es culpa del dato,
    no del transporte: la ruta lo traduce a un 400 con el motivo."""


def _fecha(valor):
    """Normaliza date/datetime/None a un date en hora local del consultorio."""
    from services.tiempo import ahora_local

    if valor is None:
        return ahora_local().date()
    return valor.date() if isinstance(valor, datetime) else valor


def _citas_entre(dentista, desde, hasta):
    """Citas vivas del dentista entre dos fechas (ambas inclusive)."""
    from models import Cita, EstatusCita

    inicio = datetime(desde.year, desde.month, desde.day, 0, 0, 0)
    fin = datetime(hasta.year, hasta.month, hasta.day, 23, 59, 59)
    return (Cita.query
            .filter(Cita.dentista_id == dentista.id,
                    Cita.fecha_inicio >= inicio,
                    Cita.fecha_inicio <= fin,
                    Cita.status.in_([EstatusCita.pendiente, EstatusCita.confirmada]))
            .order_by(Cita.fecha_inicio)
            .all())


def _linea_cita(cita):
    hora = cita.fecha_inicio.strftime('%H:%M')
    estatus = 'CONFIRMADA' if cita.status.value == 'confirmada' else 'Pendiente'
    tipo = cita.tipo_cita.nombre if cita.tipo_cita else 'Cita'
    return f'{hora} {cita.paciente.nombre_completo} ({tipo}) [{estatus}]'


def citas_en_un_renglon(citas):
    """Las citas de un dia, en una sola linea. Ver SEPARADOR_CITAS."""
    return SEPARADOR_CITAS.join(_linea_cita(c) for c in citas)


def _por_dia(desde, valor_de_cada_dia):
    """
    Arma las siete variables de dia ({{3}} a {{9}}) para las plantillas
    semanales. `valor_de_cada_dia` recibe la fecha y devuelve lo que va despues
    de los dos puntos; ninguna puede quedar vacia porque Meta rechaza las
    variables en blanco.
    """
    valores = {}
    for i in range(DIAS_SEMANA):
        dia = desde + timedelta(days=i)
        valores[f'dia_{i + 1}'] = f'{_etiqueta_dia(dia)}: {valor_de_cada_dia(dia)}'
    return valores


def _etiqueta_dia(fecha):
    return f'{DIAS[fecha.weekday()]} {fecha.strftime("%d/%m")}'


def _rango_str(desde, hasta):
    return f'{desde.strftime("%d/%m/%Y")} al {hasta.strftime("%d/%m/%Y")}'


def _en_vacaciones(dentista, fecha):
    """True si un BloqueoDentista cubre cualquier parte de ese dia."""
    from models import BloqueoDentista

    inicio = datetime(fecha.year, fecha.month, fecha.day, 0, 0, 0)
    fin = datetime(fecha.year, fecha.month, fecha.day, 23, 59, 59)
    return BloqueoDentista.query.filter(
        BloqueoDentista.dentista_id == dentista.id,
        BloqueoDentista.fecha_inicio <= fin,
        BloqueoDentista.fecha_fin >= inicio,
    ).first() is not None


def _enviar(dentista, tipo_plantilla, valores, fallback):
    """Manda el mensaje al doctor con su plantilla, o con el texto de respaldo
    si la plantilla no existe. Devuelve el texto que quedo en la bitacora."""
    from models import PlantillaMensaje, TipoRecordatorio
    from services.paises import formatear_numero_e164
    from services.whatsapp_service import enviar_mensaje, kwargs_plantilla

    numero = formatear_numero_e164(dentista.telefono, getattr(dentista, 'pais', 'MX'))
    if not numero:
        raise EnvioDoctorError(
            f'{dentista.nombre} no tiene numero de WhatsApp cargado.')

    plantilla = PlantillaMensaje.query.filter_by(
        tipo=tipo_plantilla, activo=True).first()
    try:
        mensaje = plantilla.contenido.format(**valores) if plantilla else fallback
    except KeyError as falta:
        # Pasa si la fila de plantillas_mensaje quedo con un placeholder que el
        # envio ya no manda: casi siempre, migraciones sin correr.
        raise EnvioDoctorError(
            f'La plantilla "{tipo_plantilla}" usa {falta}, que este envio ya no '
            'manda. Falta correr las migraciones (flask db upgrade).')

    enviar_mensaje(numero, mensaje, tipo=TipoRecordatorio.resumen_doctor,
                   dentista_id=dentista.id,
                   **kwargs_plantilla(plantilla, valores))
    return mensaje


def _armar_horario_semanal(dentista, desde=None):
    """Arma el horario de los proximos 7 dias sin mandarlo.

    Usa `horario_efectivo`, asi que respeta los turnos rotativos: si el doctor
    comparte un sabado con otra doctora, solo aparece el sabado que le toca.
    """
    from services.scheduler_service import horario_efectivo

    desde = _fecha(desde)
    hasta = desde + timedelta(days=DIAS_SEMANA - 1)
    trabaja_algun_dia = False

    def _estado_del_dia(dia):
        nonlocal trabaja_algun_dia
        rango = horario_efectivo(dentista.id, dia)
        if not rango:
            return 'descanso'
        if _en_vacaciones(dentista, dia):
            return 'vacaciones'
        trabaja_algun_dia = True
        inicio, fin = rango
        return f'{inicio.strftime("%H:%M")} a {fin.strftime("%H:%M")}'

    dias = _por_dia(desde, _estado_del_dia)

    if not trabaja_algun_dia:
        raise EnvioDoctorError(
            f'{dentista.nombre} no tiene dias de atencion en esa semana.')

    rango_str = _rango_str(desde, hasta)
    valores = {
        'nombre_doctor': dentista.nombre,
        'rango': rango_str,
        **dias,
    }
    listado = '\n'.join(f'- {dias[f"dia_{i}"]}' for i in range(1, DIAS_SEMANA + 1))
    fallback = (f'Hola {dentista.nombre}! Este es tu horario del {rango_str}:\n'
                f'{listado}\n'
                f'Si algo no coincide avisanos. La Casa del Sr. Perez')
    return 'horario_doctor', valores, fallback


def enviar_horario_semanal(dentista, desde=None):
    """Manda al doctor los dias y horas que atiende en los proximos 7 dias."""
    return _enviar(dentista, *_armar_horario_semanal(dentista, desde))


def _armar_resumen_dia(dentista, fecha=None):
    """Arma las citas de un dia (por defecto hoy) sin mandarlas."""
    fecha = _fecha(fecha)
    citas = _citas_entre(dentista, fecha, fecha)
    if not citas:
        raise EnvioDoctorError(
            f'{dentista.nombre} no tiene citas el {fecha.strftime("%d/%m/%Y")}.')

    fecha_str = fecha.strftime('%d/%m/%Y')
    listado = citas_en_un_renglon(citas)
    valores = {
        'nombre_doctor': dentista.nombre,
        'fecha': fecha_str,
        'listado': listado,
    }
    fallback = (f'Hola {dentista.nombre}! Estas son tus citas del {fecha_str}:\n'
                f'{listado}\n'
                f'La Casa del Sr. Perez')
    return 'resumen_doctor_dia', valores, fallback


def enviar_resumen_dia(dentista, fecha=None):
    """Manda al doctor sus citas de un dia (por defecto hoy)."""
    return _enviar(dentista, *_armar_resumen_dia(dentista, fecha))


def _armar_resumen_semanal(dentista, desde=None):
    """Arma las citas de los proximos 7 dias, agrupadas por dia, sin mandarlas."""
    desde = _fecha(desde)
    hasta = desde + timedelta(days=DIAS_SEMANA - 1)
    citas = _citas_entre(dentista, desde, hasta)
    if not citas:
        raise EnvioDoctorError(
            f'{dentista.nombre} no tiene citas del {_rango_str(desde, hasta)}.')

    por_fecha = {}
    for cita in citas:
        por_fecha.setdefault(cita.fecha_inicio.date(), []).append(cita)

    dias = _por_dia(
        desde,
        lambda dia: citas_en_un_renglon(por_fecha[dia]) if dia in por_fecha
        else SIN_CITAS)

    rango_str = _rango_str(desde, hasta)
    valores = {
        'nombre_doctor': dentista.nombre,
        'rango': rango_str,
        **dias,
    }
    listado = '\n'.join(f'- {dias[f"dia_{i}"]}' for i in range(1, DIAS_SEMANA + 1))
    fallback = (f'Hola {dentista.nombre}! Estas son tus citas de la semana '
                f'del {rango_str}:\n'
                f'{listado}\n'
                f'La Casa del Sr. Perez')
    return 'resumen_semanal_doctor', valores, fallback


def enviar_resumen_semanal(dentista, desde=None):
    """Manda al doctor sus citas de los proximos 7 dias, agrupadas por dia."""
    return _enviar(dentista, *_armar_resumen_semanal(dentista, desde))


# Como armar cada envio sin mandarlo. Lo usa `manage.py revisar_envio_doctor`
# para ver que le llegaria a Twilio sin gastar un mensaje.
ARMADORES = {
    'horario': _armar_horario_semanal,
    'dia': _armar_resumen_dia,
    'semana': _armar_resumen_semanal,
}

# Lo que la ruta acepta en el campo `tipo`, y con que se responde.
ENVIOS = {
    'horario': (enviar_horario_semanal, 'Horario de la semana'),
    'dia': (enviar_resumen_dia, 'Resumen de citas del dia'),
    'semana': (enviar_resumen_semanal, 'Resumen de citas de la semana'),
}
