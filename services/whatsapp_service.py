"""
Integracion con Twilio para enviar mensajes de WhatsApp.
"""
import logging
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


def _enviar_por_twilio(numero_destino, mensaje, status_callback=None):
    """
    Transporte puro: habla con Twilio y devuelve el SID. No escribe bitacora.
    Lanza excepcion si el envio falla.
    """
    account_sid = current_app.config.get('TWILIO_ACCOUNT_SID', '')
    auth_token = current_app.config.get('TWILIO_AUTH_TOKEN', '')
    from_number = current_app.config.get('TWILIO_WHATSAPP_NUMBER', '')

    if not all([account_sid, auth_token, from_number]):
        raise ValueError('Credenciales de Twilio no configuradas')

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

    kwargs = {'from_': from_number, 'body': mensaje, 'to': to}
    if status_callback:
        kwargs['status_callback'] = status_callback

    msg = client.messages.create(**kwargs)
    logger.info(f'WA enviado a {numero_destino}: SID={msg.sid}')
    return msg.sid


def _crear_registro(numero_destino, mensaje, tipo, paciente_id, cita_id,
                    dentista_id, campana_destinatario_id):
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
                   campana_destinatario_id=None, registrar=True):
    """
    Envia un mensaje de WhatsApp via Twilio y lo registra en la bitacora.

    numero_destino: numero en formato +521XXXXXXXXXX (sin prefijo whatsapp:)
    status_callback: URL absoluta opcional. None usa la del config; False la deshabilita.
    tipo: valor de TipoRecordatorio. Si no se pasa, se registra como 'otro'.
    registrar: False omite la bitacora — lo usa el job de reenvio, que actualiza
        la fila que ya existe en vez de crear una nueva.

    Retorna el SID del mensaje. Propaga la excepcion si el envio falla.
    """
    _asegurar_frontera_transaccional()

    registro = None
    if registrar:
        registro = _crear_registro(numero_destino, mensaje, tipo, paciente_id,
                                   cita_id, dentista_id, campana_destinatario_id)

    try:
        sid = _enviar_por_twilio(numero_destino, mensaje, status_callback)
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
    if plantilla:
        mensaje = plantilla.contenido.format(
            nombre_paciente=paciente.nombre_completo,
            hora=hora,
        )
    else:
        mensaje = (
            f'Hola buenas tardes\n'
            f'Como esta? Le escribo para confirmar la cita de {paciente.nombre_completo} '
            f'manana a las {hora}.\n'
            f'Gracias :)'
        )

    try:
        enviar_mensaje(numero, mensaje, tipo=TipoRecordatorio.confirmacion_24h,
                       paciente_id=paciente.id, cita_id=cita.id)
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

    if plantilla:
        mensaje = plantilla.contenido.format(
            nombre_paciente=paciente.nombre_completo,
            hora=hora,
            dentista=dentista,
        )
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
                       paciente_id=paciente.id, cita_id=cita.id)
        return True
    except Exception as e:
        logger.error(f'Error enviando confirmacion mismo dia cita {cita.id}: {e}')
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

    if plantilla:
        mensaje = plantilla.contenido.format(
            nombre_paciente=paciente.nombre_completo,
            google_reviews_link=reviews_link,
        )
    else:
        mensaje = (
            f'Hola Sra/Sr buenas tardes :) Como esta? '
            f'Le comparto la foto (DIPLOMA Y PIN) de {paciente.nombre_completo}, '
            f'nos encantaria conocer su experiencia con nosotros le mandare un link '
            f'{reviews_link} y solo debe dar clic, muchas gracias :)'
        )

    try:
        enviar_mensaje(numero, mensaje, tipo=TipoRecordatorio.postconsulta,
                       paciente_id=paciente.id, cita_id=cita.id)
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
    if plantilla:
        mensaje = plantilla.contenido.format(
            nombre_paciente=paciente.nombre_completo,
            fecha=fecha_cita,
        )
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
                       paciente_id=paciente.id, cita_id=cita.id)
        return True
    except Exception as e:
        logger.error(f'Error enviando reagendar no-asistencia cita {cita.id}: {e}')
        return False


def enviar_recordatorio_proxima_visita(paciente):
    """Envia recordatorio mensual para agendar proxima visita."""
    from models import TipoRecordatorio

    numero = paciente.numero_contacto_wa

    if not numero:
        return False

    from models import PlantillaMensaje
    plantilla = PlantillaMensaje.query.filter_by(tipo='proxima_visita', activo=True).first()

    tutor = paciente.nombre_tutor or 'Estimado/a'
    if plantilla:
        mensaje = plantilla.contenido.format(
            nombre_tutor=tutor,
            nombre_paciente=paciente.nombre_completo,
        )
    else:
        mensaje = (
            f'Hola {tutor}! Le recordamos que ya es momento de programar '
            f'la proxima cita de {paciente.nombre_completo} en La Casa del Sr. Perez.\n'
            f'Escribanos para buscarle un horario disponible :)'
        )

    try:
        enviar_mensaje(numero, mensaje, tipo=TipoRecordatorio.proxima_visita,
                       paciente_id=paciente.id)
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

    lineas = [f'Hola {dentista.nombre}! Tus citas de manana {fecha_str}:\n']
    for c in citas:
        hora = c.fecha_inicio.strftime('%H:%M')
        status = 'CONFIRMADA' if c.status.value == 'confirmada' else 'Pendiente'
        lineas.append(f'- {hora}: {c.paciente.nombre_completo} ({c.tipo_cita.nombre if c.tipo_cita else "Cita"}) [{status}]')

    lineas.append('\nBuen dia! La Casa del Sr. Perez')
    mensaje = '\n'.join(lineas)

    try:
        enviar_mensaje(numero, mensaje, tipo=TipoRecordatorio.resumen_doctor,
                       dentista_id=dentista.id)
        return True
    except Exception as e:
        logger.error(f'Error enviando resumen a Dr. {dentista.nombre}: {e}')
        return False
