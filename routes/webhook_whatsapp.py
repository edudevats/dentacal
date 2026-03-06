from flask import Blueprint, request, Response
from extensions import db, csrf
from models import ConversacionWhatsapp, Paciente

webhook_bp = Blueprint('webhook', __name__, url_prefix='/webhook')


@webhook_bp.route('/whatsapp', methods=['POST'])
@csrf.exempt
def whatsapp_incoming():
    """Recibe mensajes entrantes de Twilio WhatsApp."""
    # Validar firma de Twilio en produccion
    _validar_firma_twilio()

    body = request.form.get('Body', '').strip()
    from_number = request.form.get('From', '').strip()  # formato: whatsapp:+521...
    # Normalizar numero
    numero = from_number.replace('whatsapp:', '').strip()

    if not body or not numero:
        return Response('', status=200)

    # Guardar mensaje del paciente
    paciente = _buscar_o_registrar_paciente(numero)
    _guardar_mensaje(numero, paciente.id if paciente else None, body, es_bot=False)

    # Procesar con IA
    try:
        from services.ai_service import procesar_mensaje_bot
        respuesta = procesar_mensaje_bot(body, numero, paciente)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'Error en bot IA: {e}')
        respuesta = ('Lo siento, en este momento tengo un inconveniente tecnico. '
                     'Por favor llama al consultorio directamente o intentalo en unos minutos.')

    # Guardar respuesta del bot
    _guardar_mensaje(numero, paciente.id if paciente else None, respuesta, es_bot=True)

    # Responder via TwiML
    try:
        from twilio.twiml.messaging_response import MessagingResponse
        resp = MessagingResponse()
        resp.message(respuesta)
        return Response(str(resp), mimetype='text/xml')
    except ImportError:
        # Si Twilio no esta instalado (tests), devolver texto plano
        return Response(respuesta, mimetype='text/plain')


def _validar_firma_twilio():
    """Valida la firma X-Twilio-Signature en produccion."""
    from flask import current_app
    if current_app.config.get('TESTING'):
        return

    auth_token = current_app.config.get('TWILIO_AUTH_TOKEN', '')
    if not auth_token:
        return  # Sin token configurado, omitir validacion (solo dev)

    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(auth_token)
        url = request.url
        params = request.form.to_dict()
        signature = request.headers.get('X-Twilio-Signature', '')

        if not validator.validate(url, params, signature):
            from flask import abort
            abort(403)
    except ImportError:
        pass


def _buscar_o_registrar_paciente(numero):
    """Busca el paciente por whatsapp o retorna None si no existe."""
    numero_limpio = numero.replace('+', '').replace(' ', '')
    paciente = Paciente.query.filter(
        db.or_(
            Paciente.whatsapp == numero,
            Paciente.whatsapp == f'+{numero_limpio}',
            Paciente.whatsapp == numero_limpio,
        ),
        Paciente.eliminado == False
    ).first()
    return paciente


def _guardar_mensaje(numero, paciente_id, mensaje, es_bot=False):
    try:
        conv = ConversacionWhatsapp(
            numero_telefono=numero,
            paciente_id=paciente_id,
            mensaje=mensaje,
            es_bot=es_bot,
        )
        db.session.add(conv)
        db.session.commit()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f'Error guardando conversacion: {e}')
        db.session.rollback()
