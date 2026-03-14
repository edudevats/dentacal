import logging
from datetime import datetime
from flask import Blueprint, request, Response
from extensions import db, csrf
from models import ConversacionWhatsapp, Paciente

log = logging.getLogger(__name__)

webhook_bp = Blueprint('webhook', __name__, url_prefix='/webhook')

MENSAJE_ADJUNTO = (
    'Lo sentimos, no podemos recibir imágenes, videos ni archivos por este medio 🙏\n'
    'Por favor escríbenos en texto y con gusto te atendemos 😊'
)


@webhook_bp.route('/whatsapp', methods=['POST'])
@csrf.exempt
def whatsapp_incoming():
    """Recibe mensajes entrantes de Twilio WhatsApp."""
    _validar_firma_twilio()

    from_number = request.form.get('From', '').strip()
    numero = from_number.replace('whatsapp:', '').strip()

    if not numero:
        return Response('', status=200)

    body      = request.form.get('Body', '').strip()
    num_media = int(request.form.get('NumMedia', 0) or 0)

    paciente = _buscar_o_registrar_paciente(numero)
    pid = paciente.id if paciente else None

    # ── Filtro: rechazar cualquier mensaje con archivos adjuntos ────────────
    if num_media > 0:
        log.info(f'Adjunto rechazado de {numero} (NumMedia={num_media})')
        # Guardamos una nota de texto (sin URL ni datos del archivo)
        _guardar_mensaje(numero, pid, '[Archivo adjunto — no guardado]', es_bot=False)
        _guardar_mensaje(numero, pid, MENSAJE_ADJUNTO, es_bot=True)
        return _twiml_response(MENSAJE_ADJUNTO)

    # ── Mensaje sin texto (raro, pero posible) ──────────────────────────────
    if not body:
        return Response('', status=200)

    # ── Mensaje de texto normal → procesar con bot IA ──────────────────────
    _guardar_mensaje(numero, pid, body, es_bot=False)

    try:
        from services.ai_service import procesar_mensaje_bot
        respuesta = procesar_mensaje_bot(body, numero, paciente)
    except Exception as e:
        log.error(f'Error en bot IA: {e}')
        respuesta = (
            'Lo siento, en este momento tengo un inconveniente técnico. '
            'Por favor llama al consultorio directamente o inténtalo en unos minutos.'
        )

    _guardar_mensaje(numero, pid, respuesta, es_bot=True)
    return _twiml_response(respuesta)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _twiml_response(texto):
    """Devuelve respuesta TwiML (o texto plano si Twilio no está instalado)."""
    try:
        from twilio.twiml.messaging_response import MessagingResponse
        resp = MessagingResponse()
        resp.message(texto)
        return Response(str(resp), mimetype='text/xml')
    except ImportError:
        return Response(texto, mimetype='text/plain')


def _validar_firma_twilio():
    """Valida la firma X-Twilio-Signature en producción."""
    from flask import current_app
    if current_app.config.get('TESTING'):
        return

    auth_token = current_app.config.get('TWILIO_AUTH_TOKEN', '')
    if not auth_token:
        return  # Sin token configurado, omitir validación (solo dev)

    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(auth_token)
        if not validator.validate(request.url, request.form.to_dict(),
                                  request.headers.get('X-Twilio-Signature', '')):
            from flask import abort
            abort(403)
    except ImportError:
        pass


def _variantes_numero_mx(numero):
    """Genera todas las variantes posibles de un numero mexicano.
    Twilio envia +521XXXXXXXXXX pero en la BD puede estar como
    +52XXXXXXXXXX, 52XXXXXXXXXX, XXXXXXXXXX, +521XXXXXXXXXX, etc.
    """
    limpio = numero.replace('+', '').replace(' ', '').replace('-', '')
    # Extraer los 10 digitos base del numero mexicano
    if limpio.startswith('521') and len(limpio) == 13:
        base10 = limpio[3:]  # quitar 521
    elif limpio.startswith('52') and len(limpio) == 12:
        base10 = limpio[2:]  # quitar 52
    elif len(limpio) == 10:
        base10 = limpio
    else:
        # Numero no mexicano o formato desconocido, retornar variantes basicas
        return list(set([numero, f'+{limpio}', limpio]))

    return list(set([
        base10,                # 5512345678
        f'52{base10}',         # 5252345678  (12 digitos)
        f'+52{base10}',        # +5252345678
        f'521{base10}',        # 52152345678 (13 digitos)
        f'+521{base10}',       # +52152345678
        numero,                # valor original tal cual
    ]))


def _buscar_o_registrar_paciente(numero):
    """Busca el paciente por whatsapp. Si hay multiples (grupo familiar),
    retorna el mas recientemente activo."""
    variantes = _variantes_numero_mx(numero)
    pacientes = Paciente.query.filter(
        Paciente.whatsapp.in_(variantes),
        Paciente.eliminado == False
    ).all()

    if not pacientes:
        return None
    if len(pacientes) == 1:
        return pacientes[0]

    # Multiples pacientes comparten numero: elegir el mas recientemente activo
    from sqlalchemy import func as sqlfunc
    ultimo_msg = db.session.query(
        ConversacionWhatsapp.paciente_id,
        sqlfunc.max(ConversacionWhatsapp.timestamp).label('ultima')
    ).filter(
        ConversacionWhatsapp.paciente_id.in_([p.id for p in pacientes])
    ).group_by(ConversacionWhatsapp.paciente_id).all()

    if ultimo_msg:
        mas_reciente_id = max(ultimo_msg, key=lambda x: x.ultima).paciente_id
        for p in pacientes:
            if p.id == mas_reciente_id:
                return p

    # Fallback: paciente mas reciente
    return max(pacientes, key=lambda p: p.created_at or datetime.min)


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
        log.error(f'Error guardando conversacion: {e}')
        db.session.rollback()
