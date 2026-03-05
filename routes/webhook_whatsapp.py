from flask import Blueprint, request, current_app
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from models import db, ConversacionWhatsapp, Paciente
from services.ai_receptionist import procesar_mensaje_bot
import json
from datetime import datetime

bp_webhook = Blueprint('webhook', __name__)


def _validar_firma_twilio():
    """Valida que la petición provenga de Twilio."""
    auth_token = current_app.config.get('TWILIO_AUTH_TOKEN', '')
    if not auth_token:
        # Sin token configurado, solo aceptar en desarrollo
        if not current_app.debug:
            return False
        return True

    validator = RequestValidator(auth_token)
    signature = request.headers.get('X-Twilio-Signature', '')
    url = request.url
    post_data = request.form.to_dict()

    return validator.validate(url, post_data, signature)


@bp_webhook.route('/webhook/whatsapp', methods=['POST'])
def webhook_whatsapp():
    """Recibe mensajes de Twilio y los procesa con el bot IA."""
    # Validar firma Twilio
    if not _validar_firma_twilio():
        current_app.logger.warning('[WA] Firma Twilio inválida — petición rechazada')
        return 'Forbidden', 403

    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')  # "whatsapp:+52xxxxxxxxxx"

    if not incoming_msg or not from_number:
        return str(MessagingResponse())

    # Limpiar número (quitar prefijo whatsapp:)
    telefono = from_number.replace('whatsapp:', '')

    current_app.logger.info(f"[WA] De {telefono}: {incoming_msg}")

    try:
        # Obtener/crear conversación
        conv = ConversacionWhatsapp.query.filter_by(telefono=telefono).first()
        if not conv:
            # Buscar si el paciente existe
            paciente = Paciente.query.filter_by(telefono=telefono).first()
            conv = ConversacionWhatsapp(
                telefono=telefono,
                paciente_id=paciente.id if paciente else None,
                estado_flujo='info',
                historial_mensajes=json.dumps([]),
            )
            db.session.add(conv)
            db.session.flush()

        # Agregar mensaje al historial
        historial = json.loads(conv.historial_mensajes or '[]')
        historial.append({'role': 'user', 'content': incoming_msg})
        # Limitar historial a últimos 20 mensajes
        if len(historial) > 20:
            historial = historial[-20:]

        # Procesar con IA
        respuesta_bot, nuevo_estado = procesar_mensaje_bot(
            telefono=telefono,
            mensaje=incoming_msg,
            historial=historial,
            estado_flujo=conv.estado_flujo,
            paciente_id=conv.paciente_id,
        )

        # Guardar respuesta en historial
        historial.append({'role': 'assistant', 'content': respuesta_bot})
        conv.historial_mensajes = json.dumps(historial)
        conv.estado_flujo = nuevo_estado
        conv.ultima_actividad = datetime.utcnow()

        # Vincular paciente si se identificó
        if not conv.paciente_id:
            p = Paciente.query.filter_by(telefono=telefono).first()
            if p:
                conv.paciente_id = p.id

        db.session.commit()

        # Enviar respuesta Twilio
        resp = MessagingResponse()
        resp.message(respuesta_bot)
        return str(resp)

    except Exception as e:
        current_app.logger.error(f"[WA] Error procesando mensaje: {e}", exc_info=True)
        resp = MessagingResponse()
        resp.message(
            'Disculpe, tuvimos un problema técnico. '
            'Por favor contáctenos directamente al consultorio. 🦷'
        )
        return str(resp)


@bp_webhook.route('/webhook/whatsapp/status', methods=['POST'])
def webhook_status():
    """Callback de status de mensajes Twilio (entregado, leído, etc.)."""
    msg_status = request.values.get('MessageStatus', '')
    msg_sid = request.values.get('MessageSid', '')
    current_app.logger.info(f"[WA Status] {msg_sid}: {msg_status}")
    return '', 204
