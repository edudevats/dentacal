"""
Integracion con Twilio para enviar mensajes de WhatsApp.
"""
import logging
from flask import current_app

logger = logging.getLogger(__name__)


def enviar_mensaje(numero_destino, mensaje):
    """
    Envia un mensaje de WhatsApp via Twilio.
    numero_destino: numero en formato +521XXXXXXXXXX (sin prefijo whatsapp:)
    Retorna el SID del mensaje.
    """
    account_sid = current_app.config.get('TWILIO_ACCOUNT_SID', '')
    auth_token = current_app.config.get('TWILIO_AUTH_TOKEN', '')
    from_number = current_app.config.get('TWILIO_WHATSAPP_NUMBER', '')

    if not all([account_sid, auth_token, from_number]):
        raise ValueError('Credenciales de Twilio no configuradas')

    if account_sid.startswith('test') or account_sid == 'test_sid':
        logger.info(f'[TEST] WA a {numero_destino}: {mensaje[:80]}...')
        return 'TEST_SID'

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)

        # Normalizar numero
        if not numero_destino.startswith('whatsapp:'):
            to = f'whatsapp:{numero_destino}'
        else:
            to = numero_destino

        msg = client.messages.create(
            from_=from_number,
            body=mensaje,
            to=to,
        )
        logger.info(f'WA enviado a {numero_destino}: SID={msg.sid}')
        return msg.sid
    except Exception as e:
        logger.error(f'Error enviando WA a {numero_destino}: {e}')
        raise


def enviar_recordatorio_cita(cita):
    """
    Envia recordatorio de confirmacion 24h antes de la cita.
    """
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
        enviar_mensaje(numero, mensaje)
        return True
    except Exception as e:
        logger.error(f'Error enviando recordatorio cita {cita.id}: {e}')
        return False


def enviar_postconsulta(cita):
    """
    Envia mensaje de postconsulta 2 dias despues (protocolo postconsulta).
    Incluye link de resenas de Google.
    """
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
        enviar_mensaje(numero, mensaje)
        return True
    except Exception as e:
        logger.error(f'Error enviando postconsulta cita {cita.id}: {e}')
        return False


def enviar_resumen_diario_doctor(dentista, citas, fecha_str):
    """
    Envia resumen diario al doctor con pacientes confirmados.
    """
    if not dentista.telefono:
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
        enviar_mensaje(dentista.telefono, mensaje)
        return True
    except Exception as e:
        logger.error(f'Error enviando resumen a Dr. {dentista.nombre}: {e}')
        return False
