"""
Integracion con Twilio para enviar mensajes de WhatsApp.
"""
import logging
import re

from flask import current_app

logger = logging.getLogger(__name__)


def _build_status_callback_url():
    """Construye la URL absoluta del Status Callback de Twilio.
    Si PUBLIC_BASE_URL no esta configurada, retorna None y Twilio no enviara
    callbacks (envio normal sin tracking)."""
    base = current_app.config.get('PUBLIC_BASE_URL', '').strip().rstrip('/')
    if not base:
        return None
    return f'{base}/webhook/whatsapp-status'


# Espaciado de los reintentos, en minutos: 15 min, 1 h, 4 h.
BACKOFF_MINUTOS = [15, 60, 240]
MAX_REINTENTOS = len(BACKOFF_MINUTOS)


def _asegurar_frontera_transaccional():
    """Rechaza trabajo del caller que una sesion de ledger no puede aislar."""
    from sqlalchemy import inspect
    from extensions import db, LEDGER_FLUSHED_UNCOMMITTED

    caller = db.session()
    if caller.info.get(LEDGER_FLUSHED_UNCOMMITTED):
        raise RuntimeError(
            'Frontera de transaccion insegura: el caller tiene un flush '
            'sin commit o rollback outer')
    if caller.new or caller.deleted:
        raise RuntimeError(
            'Frontera de transaccion insegura: el caller tiene objetos '
            'nuevos o eliminados pendientes')

    # Una mutacion escalar sin flush es segura: la sesion independiente nunca
    # autoflushea al caller. Un cambio de PK no lo es porque los IDs entregados
    # al ledger pueden no existir todavia en la base.
    for objeto in caller.dirty:
        estado = inspect(objeto)
        if not caller.is_modified(objeto, include_collections=True):
            continue
        if any(estado.attrs[columna.key].history.has_changes()
               for columna in estado.mapper.primary_key):
            raise RuntimeError(
                'Frontera de transaccion insegura: hay una llave primaria '
                'modificada sin commit')


# Orden de las variables de cada plantilla aprobada de WhatsApp, tal como se
# registro en Twilio. Vive aqui y no solo en la base porque recepcion no tiene
# por que saberlo: un orden mal escrito no falla, manda el nombre donde va la
# hora. El campo de la pantalla de Configuracion es un override para servicio.
ORDEN_VARIABLES_POR_TIPO = {
    'recordatorio_24h': 'nombre_paciente,hora',
    'confirmacion_mismo_dia': 'nombre_paciente,hora,dentista',
    'recordatorio_cita_hoy': 'hora,nombre_paciente,nombre_doctor',
    'postconsulta': 'nombre_paciente,google_reviews_link',
    'proxima_visita': 'nombre_tutor,nombre_paciente',
    'no_asistencia_reagendar': 'nombre_paciente,fecha',
    'cumpleanos': 'nombre_tutor,nombre_paciente',
    'resumen_doctor': 'nombre_doctor,fecha,listado',
    'cita_reagendada': 'nombre_paciente,fecha,hora,doctor',
    # Envios manuales a doctores (services/doctor_envios.py). Los dos semanales
    # mandan un dia por variable porque Meta no admite saltos de linea dentro
    # del valor de una variable: los renglones los pone el cuerpo de la
    # plantilla. Ver SEPARADOR_CITAS en services/doctor_envios.py.
    'horario_doctor': ('nombre_doctor,rango,'
                       'dia_1,dia_2,dia_3,dia_4,dia_5,dia_6,dia_7'),
    'resumen_doctor_dia': 'nombre_doctor,fecha,listado',
    'resumen_semanal_doctor': ('nombre_doctor,rango,'
                               'dia_1,dia_2,dia_3,dia_4,dia_5,dia_6,dia_7'),
}


# Lo que WhatsApp no acepta dentro del valor de una variable de plantilla:
# saltos de linea, tabuladores y cuatro o mas espacios seguidos. Twilio lo
# rechaza con el error 21656 ("The Content Variables parameter is invalid")
# antes de intentar la entrega.
_SALTOS_DE_LINEA = re.compile(r'[ \t]*\n[ \t\n]*')
_ESPACIOS_DE_MAS = re.compile(r'\t+|    +')


def limpiar_valor_de_variable(valor):
    """
    Aplana un valor para que WhatsApp lo acepte como variable de plantilla.

    Es una red de seguridad, no el lugar donde se le da formato al mensaje: si
    llega aqui algo con saltos de linea es que quien lo armo no contemplo la
    regla, y sale un aviso en el log. El texto legible de la bitacora no pasa
    por aqui, asi que no se degrada.
    """
    limpio = _ESPACIOS_DE_MAS.sub(' ', _SALTOS_DE_LINEA.sub(' · ', valor)).strip()
    if limpio != valor:
        logger.warning(
            'Variable de plantilla aplanada para WhatsApp (traia saltos de '
            f'linea o espacios de mas): {valor[:80]!r}')
    return limpio


def orden_variables(plantilla):
    """
    Orden de variables efectivo: el que tenga cargado la plantilla, o el que
    conoce la app para ese tipo. Cadena vacia si no aplica.
    """
    explicito = (getattr(plantilla, 'content_variables_orden', None) or '').strip()
    if explicito:
        return explicito
    return ORDEN_VARIABLES_POR_TIPO.get(getattr(plantilla, 'tipo', None), '')


def _variables_posicionales(plantilla, valores):
    """
    Traduce los placeholders con nombre de la plantilla a las variables
    numeradas que espera Twilio ({{1}}, {{2}}...). Devuelve el JSON listo o
    None si la plantilla no lleva variables.
    """
    import json

    orden = orden_variables(plantilla)
    if not orden:
        return None

    nombres = [n.strip() for n in orden.split(',') if n.strip()]
    if not nombres:
        return None

    return json.dumps({
        str(posicion): limpiar_valor_de_variable(str(valores.get(nombre, '')))
        for posicion, nombre in enumerate(nombres, start=1)
    })


def kwargs_plantilla(plantilla, valores):
    """
    Argumentos de envio por plantilla aprobada, o vacio si la plantilla no
    tiene ContentSid cargado — en ese caso el mensaje sale como texto libre,
    que es lo correcto dentro de la ventana de 24 h.
    """
    if plantilla is None or not getattr(plantilla, 'content_sid', None):
        return {}
    return {
        'content_sid': plantilla.content_sid,
        'content_variables': _variables_posicionales(plantilla, valores),
    }


def _normalizado(numero):
    """Canoniza el destino y deja rastro en el log cuando hubo que corregirlo."""
    from services.paises import normalizar_whatsapp
    arreglado = normalizar_whatsapp(numero)
    if arreglado != numero:
        logger.info(f'Numero corregido antes de enviar: {numero} -> {arreglado}')
    return arreglado


def _enviar_por_twilio(numero_destino, mensaje, status_callback=None,
                       content_sid=None, content_variables=None):
    """
    Transporte puro: habla con Twilio y devuelve el SID. No escribe bitacora.
    Lanza excepcion si el envio falla.

    Con ``content_sid`` el mensaje viaja como plantilla aprobada de WhatsApp;
    sin el, como texto libre.
    """
    account_sid = current_app.config.get('TWILIO_ACCOUNT_SID', '')
    auth_token = current_app.config.get('TWILIO_AUTH_TOKEN', '')
    from_number = current_app.config.get('TWILIO_WHATSAPP_NUMBER', '')

    if not all([account_sid, auth_token, from_number]):
        raise ValueError('Credenciales de Twilio no configuradas')

    # Ultima red: ningun numero sale a Twilio sin codigo de pais. En el log de
    # produccion se vio "WA enviado a 5549527650" -- pelon, sin +52.
    numero_destino = _normalizado(numero_destino)

    if account_sid.startswith('test') or account_sid == 'test_sid':
        logger.info(f'[TEST] WA a {numero_destino}: {mensaje[:80]}...')
        return 'TEST_SID'

    from twilio.rest import Client
    client = Client(account_sid, auth_token)

    if not numero_destino.startswith('whatsapp:'):
        to = f'whatsapp:{numero_destino}'
    else:
        to = numero_destino

    if status_callback is None:
        status_callback = _build_status_callback_url()

    kwargs = {'from_': from_number, 'to': to}
    if content_sid:
        # Twilio rechaza body y content_sid juntos: el texto lo aporta la
        # plantilla aprobada.
        kwargs['content_sid'] = content_sid
        if content_variables:
            kwargs['content_variables'] = content_variables
    else:
        kwargs['body'] = mensaje
    if status_callback:
        kwargs['status_callback'] = status_callback

    msg = client.messages.create(**kwargs)
    via = f' (plantilla {content_sid})' if content_sid else ''
    logger.info(f'WA enviado a {numero_destino}: SID={msg.sid}{via}')
    return msg.sid


def _crear_registro(numero_destino, mensaje, tipo, paciente_id, cita_id,
                    dentista_id, campana_destinatario_id,
                    content_sid=None, content_variables=None):
    """Crea la fila pendiente sin confirmar la sesion Flask del llamador."""
    from extensions import db
    from models import MensajeEnviado, TipoRecordatorio, EstatusRecordatorio
    from services.tiempo import ahora_local
    from sqlalchemy.orm import Session

    registro = MensajeEnviado(
        tipo=tipo or TipoRecordatorio.otro,
        numero_destino=numero_destino,
        mensaje=mensaje,
        paciente_id=paciente_id,
        cita_id=cita_id,
        dentista_id=dentista_id,
        campana_destinatario_id=campana_destinatario_id,
        estatus=EstatusRecordatorio.pendiente,
        intentos=0,
        content_sid=content_sid,
        content_variables=content_variables,
        fecha_creacion=ahora_local(),
    )
    with Session(bind=db.engine, expire_on_commit=False) as ledger_session:
        ledger_session.add(registro)
        ledger_session.commit()
    return registro


def _marcar_enviado(registro, sid):
    from extensions import db
    from models import EstatusRecordatorio, MensajeEnviado
    from services.tiempo import ahora_local
    from sqlalchemy.orm import Session

    fecha_envio = ahora_local()
    with Session(bind=db.engine) as ledger_session:
        persistido = ledger_session.get(MensajeEnviado, registro.id)
        persistido.estatus = EstatusRecordatorio.enviado
        persistido.message_sid = sid
        persistido.fecha_envio = fecha_envio
        persistido.intentos = (persistido.intentos or 0) + 1
        persistido.proximo_intento = None
        persistido.error = None
        ledger_session.commit()
    return fecha_envio


def _persistir_sid_aceptado(registro, sid):
    """
    Persiste una aceptacion de Twilio con una recuperacion acotada.

    Un SID ya emitido nunca vuelve a convertirse en un fallo de transporte: si
    el almacenamiento local sigue caido, la fila pendiente no tiene fecha de
    reintento y el job no puede duplicar el envio.
    """
    for intento in range(2):
        try:
            return _marcar_enviado(registro, sid)
        except Exception as error:
            logger.error(
                'SID aceptado por Twilio, pero fallo la persistencia local '
                f'(intento {intento + 1}/2, mensaje {registro.id}): {error}')
    return None


def _programar_reintento(registro, error):
    """
    Marca la fila como fallida y agenda el siguiente intento segun BACKOFF_MINUTOS.
    Si ya se agotaron los reintentos, la deja en fallido_definitivo.
    """
    from datetime import timedelta
    from extensions import db
    from models import EstatusRecordatorio, MensajeEnviado
    from services.tiempo import ahora_local
    from sqlalchemy.orm import Session

    with Session(bind=db.engine) as ledger_session:
        persistido = ledger_session.get(MensajeEnviado, registro.id)
        persistido.intentos = (persistido.intentos or 0) + 1
        persistido.error = str(error)[:500]

        if persistido.intentos > MAX_REINTENTOS:
            persistido.estatus = EstatusRecordatorio.fallido_definitivo
            persistido.proximo_intento = None
        else:
            persistido.estatus = EstatusRecordatorio.fallido
            espera = BACKOFF_MINUTOS[persistido.intentos - 1]
            persistido.proximo_intento = ahora_local() + timedelta(minutes=espera)

        ledger_session.commit()


def enviar_mensaje(numero_destino, mensaje, status_callback=None, tipo=None,
                   paciente_id=None, cita_id=None, dentista_id=None,
                   campana_destinatario_id=None, registrar=True,
                   content_sid=None, content_variables=None):
    """
    Envia un mensaje de WhatsApp via Twilio y lo registra en la bitacora.

    numero_destino: numero en formato +521XXXXXXXXXX (sin prefijo whatsapp:)
    status_callback: URL absoluta opcional. None usa la del config; False la deshabilita.
    tipo: valor de TipoRecordatorio. Si no se pasa, se registra como 'otro'.
    registrar: False omite la bitacora — lo usa el job de reenvio, que actualiza
        la fila que ya existe en vez de crear una nueva.
    content_sid: ContentSid de una plantilla aprobada de WhatsApp. Sin el, el
        mensaje sale como texto libre y solo se entrega dentro de la ventana
        de 24 h. ``mensaje`` se sigue guardando en la bitacora en ambos casos.

    Retorna el SID del mensaje. Propaga la excepcion si el envio falla.
    """
    _asegurar_frontera_transaccional()

    # Antes de _crear_registro: la bitacora tiene que guardar el mismo numero
    # que recibe Twilio, porque el job de reenvio reintenta desde esa fila.
    numero_destino = _normalizado(numero_destino)

    registro = None
    if registrar:
        registro = _crear_registro(numero_destino, mensaje, tipo, paciente_id,
                                   cita_id, dentista_id, campana_destinatario_id,
                                   content_sid, content_variables)

    try:
        sid = _enviar_por_twilio(numero_destino, mensaje, status_callback,
                                 content_sid, content_variables)
    except Exception as e:
        logger.error(f'Error enviando WA a {numero_destino}: {e}')
        if registro is not None:
            _programar_reintento(registro, e)
        raise

    if registro is not None:
        _persistir_sid_aceptado(registro, sid)
    return sid


def enviar_recordatorio_cita(cita):
    """
    Envia recordatorio de confirmacion 24h antes de la cita.
    """
    from models import TipoRecordatorio

    paciente = cita.paciente
    numero = paciente.numero_contacto_wa

    if not numero:
        logger.warning(f'Cita {cita.id}: paciente sin numero de WhatsApp')
        return False

    from models import PlantillaMensaje
    plantilla = PlantillaMensaje.query.filter_by(tipo='recordatorio_24h', activo=True).first()

    hora = cita.fecha_inicio.strftime('%I:%M %p')
    valores = {'nombre_paciente': paciente.nombre_completo, 'hora': hora}
    if plantilla:
        mensaje = plantilla.contenido.format(**valores)
    else:
        mensaje = (
            f'Hola buenas tardes\n'
            f'Como esta? Le escribo para confirmar la cita de {paciente.nombre_completo} '
            f'manana a las {hora}.\n'
            f'Gracias :)'
        )

    try:
        enviar_mensaje(numero, mensaje, tipo=TipoRecordatorio.confirmacion_24h,
                       paciente_id=paciente.id, cita_id=cita.id,
                       **kwargs_plantilla(plantilla, valores))
        return True
    except Exception as e:
        logger.error(f'Error enviando recordatorio cita {cita.id}: {e}')
        return False


def enviar_confirmacion_mismo_dia(cita):
    """
    Envia confirmacion temprana para citas de hoy que fueron reservadas
    con menos de 24h de anticipacion y no recibieron el recordatorio normal.
    """
    from models import TipoRecordatorio

    paciente = cita.paciente
    numero = paciente.numero_contacto_wa

    if not numero:
        logger.warning(f'Cita {cita.id}: paciente sin numero de WhatsApp')
        return False

    from models import PlantillaMensaje
    plantilla = PlantillaMensaje.query.filter_by(tipo='confirmacion_mismo_dia', activo=True).first()

    hora = cita.fecha_inicio.strftime('%I:%M %p')
    dentista = cita.dentista.nombre if cita.dentista else 'su doctor'

    valores = {
        'nombre_paciente': paciente.nombre_completo,
        'hora': hora,
        'dentista': dentista,
    }
    if plantilla:
        mensaje = plantilla.contenido.format(**valores)
    else:
        mensaje = (
            f'Buenos dias! \U0001f60a\n'
            f'Le recordamos que {paciente.nombre_completo} tiene cita '
            f'el dia de HOY a las {hora} con {dentista}.\n'
            f'Les esperamos en La Casa del Sr. Perez \U0001f9b7\u2728\n'
            f'Si necesita reagendar, por favor respondanos lo antes posible.'
        )

    try:
        enviar_mensaje(numero, mensaje, tipo=TipoRecordatorio.confirmacion_mismo_dia,
                       paciente_id=paciente.id, cita_id=cita.id,
                       **kwargs_plantilla(plantilla, valores))
        return True
    except Exception as e:
        logger.error(f'Error enviando confirmacion mismo dia cita {cita.id}: {e}')
        return False


def enviar_recordatorio_cita_hoy(cita):
    """Envia un recordatorio informativo para una cita ya confirmada de hoy."""
    from models import PlantillaMensaje, TipoRecordatorio

    paciente = cita.paciente
    numero = paciente.numero_contacto_wa
    if not numero:
        logger.warning(f'Cita {cita.id}: paciente sin numero de WhatsApp')
        return False

    hora = cita.fecha_inicio.strftime('%I:%M %p')
    nombre_doctor = cita.dentista.nombre if cita.dentista else 'su doctor'
    plantilla = PlantillaMensaje.query.filter_by(
        tipo='recordatorio_cita_hoy', activo=True).first()
    valores = {
        'nombre_paciente': paciente.nombre_completo,
        'hora': hora,
        'nombre_doctor': nombre_doctor,
    }
    if plantilla:
        mensaje = plantilla.contenido.format(**valores)
    else:
        mensaje = (
            f'No olvides tu cita hoy a las {hora} para '
            f'{paciente.nombre_completo} con {nombre_doctor}.'
        )

    try:
        enviar_mensaje(
            numero,
            mensaje,
            tipo=TipoRecordatorio.recordatorio_cita_hoy,
            paciente_id=paciente.id,
            cita_id=cita.id,
            dentista_id=cita.dentista_id,
            **kwargs_plantilla(plantilla, valores),
        )
        return True
    except Exception as e:
        logger.error(f'Error enviando recordatorio de hoy cita {cita.id}: {e}')
        return False


def enviar_postconsulta(cita):
    """
    Envia mensaje de postconsulta 2 dias despues (protocolo postconsulta).
    Incluye link de resenas de Google.
    """
    from models import TipoRecordatorio

    paciente = cita.paciente
    numero = paciente.numero_contacto_wa

    if not numero:
        return False

    from flask import current_app
    reviews_link = current_app.config.get('GOOGLE_REVIEWS_LINK', 'https://n9.cl/ufkug')

    from models import PlantillaMensaje
    plantilla = PlantillaMensaje.query.filter_by(tipo='postconsulta', activo=True).first()

    valores = {
        'nombre_paciente': paciente.nombre_completo,
        'google_reviews_link': reviews_link,
    }
    if plantilla:
        mensaje = plantilla.contenido.format(**valores)
    else:
        mensaje = (
            f'Hola Sra/Sr buenas tardes :) Como esta? '
            f'Le comparto la foto (DIPLOMA Y PIN) de {paciente.nombre_completo}, '
            f'nos encantaria conocer su experiencia con nosotros le mandare un link '
            f'{reviews_link} y solo debe dar clic, muchas gracias :)'
        )

    try:
        enviar_mensaje(numero, mensaje, tipo=TipoRecordatorio.postconsulta,
                       paciente_id=paciente.id, cita_id=cita.id,
                       **kwargs_plantilla(plantilla, valores))
        return True
    except Exception as e:
        logger.error(f'Error enviando postconsulta cita {cita.id}: {e}')
        return False


def enviar_reagendar_no_asistencia(cita):
    """Envia mensaje ofreciendo reagendar cuando el paciente no asistio."""
    from models import TipoRecordatorio

    paciente = cita.paciente
    numero = paciente.numero_contacto_wa

    if not numero:
        logger.warning(f'Cita {cita.id}: paciente sin numero de WhatsApp para reagendar')
        return False

    from models import PlantillaMensaje
    plantilla = PlantillaMensaje.query.filter_by(tipo='no_asistencia_reagendar', activo=True).first()

    fecha_cita = cita.fecha_inicio.strftime('%d/%m/%Y')
    valores = {'nombre_paciente': paciente.nombre_completo, 'fecha': fecha_cita}
    if plantilla:
        mensaje = plantilla.contenido.format(**valores)
    else:
        mensaje = (
            f'Estimado/a, le escribimos de La Casa del Sr. Perez.\n'
            f'Lamentamos que {paciente.nombre_completo} no haya podido asistir a su cita '
            f'programada el {fecha_cita}.\n'
            f'Nos encantaria poder atenderle en otra fecha. '
            f'Responda a este mensaje y con gusto le ayudamos a reagendar su cita.'
        )

    try:
        enviar_mensaje(numero, mensaje, tipo=TipoRecordatorio.no_asistencia,
                       paciente_id=paciente.id, cita_id=cita.id,
                       **kwargs_plantilla(plantilla, valores))
        return True
    except Exception as e:
        logger.error(f'Error enviando reagendar no-asistencia cita {cita.id}: {e}')
        return False


def enviar_cita_reagendada(cita):
    """Avisa al paciente que su cita cambio de fecha/hora. True si se envio."""
    from models import PlantillaMensaje, TipoRecordatorio

    paciente = cita.paciente
    numero = paciente.numero_contacto_wa if paciente else None
    if not numero:
        logger.warning(f'Cita {cita.id}: paciente sin numero para aviso de reagendado')
        return False

    plantilla = PlantillaMensaje.query.filter_by(
        tipo='cita_reagendada', activo=True).first()

    fecha = cita.fecha_inicio.strftime('%d/%m/%Y')
    hora = cita.fecha_inicio.strftime('%H:%M')
    doctor = cita.dentista.nombre if cita.dentista else ''

    valores = {
        'nombre_paciente': paciente.nombre_completo,
        'fecha': fecha, 'hora': hora, 'doctor': doctor,
    }
    if plantilla:
        mensaje = plantilla.contenido.format(**valores)
    else:
        mensaje = (
            f'Hola {paciente.nombre_completo}, le escribimos de La Casa del Sr. Perez.\n\n'
            f'Su cita fue reagendada para el {fecha} a las {hora} con {doctor}.\n\n'
            f'Si la nueva fecha no le funciona, responda a este mensaje y la ajustamos.'
        )

    enviar_mensaje(numero, mensaje, tipo=TipoRecordatorio.otro,
                   paciente_id=paciente.id, cita_id=cita.id,
                   **kwargs_plantilla(plantilla, valores))
    return True


def enviar_recordatorio_proxima_visita(paciente):
    """Envia recordatorio mensual para agendar proxima visita."""
    from models import TipoRecordatorio

    numero = paciente.numero_contacto_wa

    if not numero:
        return False

    from models import PlantillaMensaje
    plantilla = PlantillaMensaje.query.filter_by(tipo='proxima_visita', activo=True).first()

    tutor = paciente.nombre_tutor or 'Estimado/a'
    valores = {'nombre_tutor': tutor, 'nombre_paciente': paciente.nombre_completo}
    if plantilla:
        mensaje = plantilla.contenido.format(**valores)
    else:
        mensaje = (
            f'Hola {tutor}! Le recordamos que ya es momento de programar '
            f'la proxima cita de {paciente.nombre_completo} en La Casa del Sr. Perez.\n'
            f'Escribanos para buscarle un horario disponible :)'
        )

    try:
        enviar_mensaje(numero, mensaje, tipo=TipoRecordatorio.proxima_visita,
                       paciente_id=paciente.id,
                       **kwargs_plantilla(plantilla, valores))
        return True
    except Exception as e:
        logger.error(f'Error enviando recordatorio proxima visita a {paciente.nombre_completo}: {e}')
        return False


def enviar_resumen_diario_doctor(dentista, citas, fecha_str):
    """
    Envia resumen diario al doctor con pacientes confirmados.
    """
    from models import TipoRecordatorio
    from services.paises import formatear_numero_e164

    numero = formatear_numero_e164(dentista.telefono, getattr(dentista, 'pais', 'MX'))
    if not numero:
        return False

    if not citas:
        return False

    from services.doctor_envios import citas_en_un_renglon
    listado = citas_en_un_renglon(citas)

    from models import PlantillaMensaje
    plantilla = PlantillaMensaje.query.filter_by(
        tipo='resumen_doctor', activo=True).first()

    # El listado va como una sola variable y en un solo renglon: una plantilla
    # de WhatsApp no puede tener un numero variable de lineas, y Meta ademas no
    # admite saltos de linea dentro del valor de una variable.
    valores = {
        'nombre_doctor': dentista.nombre,
        'fecha': fecha_str,
        'listado': listado,
    }
    if plantilla:
        mensaje = plantilla.contenido.format(**valores)
    else:
        mensaje = '\n'.join([
            f'Hola {dentista.nombre}! Tus citas de manana {fecha_str}:\n',
            listado,
            '\nBuen dia! La Casa del Sr. Perez',
        ])

    try:
        enviar_mensaje(numero, mensaje, tipo=TipoRecordatorio.resumen_doctor,
                       dentista_id=dentista.id,
                       **kwargs_plantilla(plantilla, valores))
        return True
    except Exception as e:
        logger.error(f'Error enviando resumen a Dr. {dentista.nombre}: {e}')
        return False
