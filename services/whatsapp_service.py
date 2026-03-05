"""Servicio de envío/recepción de WhatsApp via Twilio."""
import os
from flask import current_app


def _get_client():
    from twilio.rest import Client
    sid = current_app.config.get('TWILIO_ACCOUNT_SID', '')
    token = current_app.config.get('TWILIO_AUTH_TOKEN', '')
    if not sid or not token:
        raise RuntimeError('Credenciales Twilio no configuradas en .env')
    return Client(sid, token)


def enviar_mensaje(to: str, body: str) -> str:
    """Envía un mensaje de WhatsApp. `to` debe incluir prefijo whatsapp:."""
    client = _get_client()
    from_number = current_app.config['TWILIO_WHATSAPP_NUMBER']
    if not to.startswith('whatsapp:'):
        to = f'whatsapp:{to}'
    msg = client.messages.create(body=body, from_=from_number, to=to)
    current_app.logger.info(f"[WA] Enviado a {to}: SID={msg.sid}")
    return msg.sid


def notificar_recepcionista(texto: str) -> None:
    """Notifica a la recepcionista principal (número del consultorio)."""
    numero_recepcionista = os.environ.get('RECEPCIONISTA_WHATSAPP', '')
    if not numero_recepcionista:
        current_app.logger.warning('[WA] RECEPCIONISTA_WHATSAPP no configurado')
        return
    try:
        enviar_mensaje(numero_recepcionista, texto)
    except Exception as e:
        current_app.logger.error(f'[WA] No se pudo notificar recepcionista: {e}')
