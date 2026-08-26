"""
Respuesta del bot fuera del request de Twilio.

Twilio corta la conexion del webhook a los ~15 s. El agentic loop de Gemini
tarda mas que eso cuando encadena varias llamadas, y el TwiML terminaba
escribiendose sobre un socket ya cerrado: en el log de PythonAnywhere aparecia
"OSError: write error" y el paciente no recibia nada.

Ahora el webhook contesta 200 de inmediato y la respuesta sale por la REST API
de Twilio desde un hilo aparte. El paciente acaba de escribir, asi que la
ventana de 24 h esta abierta y el texto libre es valido: no hace falta
plantilla aprobada (no aplica el error 63016).
"""
import logging
import threading

from extensions import db
from models import ConversacionWhatsapp

log = logging.getLogger(__name__)

MENSAJE_ERROR = (
    'Lo siento, en este momento tengo un inconveniente técnico. '
    'Por favor llama al consultorio directamente o inténtalo en unos minutos.'
)

# Un candado por numero de telefono. Si el paciente manda dos mensajes
# seguidos, el segundo hilo espera al primero: sin esto ambos leerian el mismo
# historial de ConversacionWhatsapp y contestarian lo mismo, o al reves.
_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def _lock_de(numero):
    with _LOCKS_GUARD:
        lock = _LOCKS.get(numero)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[numero] = lock
        return lock


def guardar_mensaje(numero, paciente_id, mensaje, es_bot=False):
    """Registra una linea de la conversacion. Nunca propaga la excepcion."""
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


def calcular_respuesta(numero, paciente_id, body):
    """
    Corre el bot IA y devuelve el texto a mandar. Si el bot truena devuelve el
    mensaje de disculpa: el paciente siempre recibe algo.

    Requiere un app context activo.
    """
    from models import Paciente
    from services.ai_service import procesar_mensaje_bot

    try:
        paciente = Paciente.query.get(paciente_id) if paciente_id else None
        return procesar_mensaje_bot(body, numero, paciente)
    except Exception as e:
        log.error(f'Error en bot IA para {numero}: {e}')
        return MENSAJE_ERROR


def responder(app, numero, paciente_id, body):
    """
    Calcula la respuesta y la manda por la REST API de Twilio. Bloquea.

    Se registra en ConversacionWhatsapp (que es la bitacora del chat del bot)
    pero no en MensajeEnviado: esa tabla es para los envios que dispara la app
    -- recordatorios, resumenes, campanas -- y el monitor del bot lee la otra.
    """
    from models import TipoRecordatorio
    from services.whatsapp_service import enviar_mensaje

    with app.app_context():
        with _lock_de(numero):
            respuesta = calcular_respuesta(numero, paciente_id, body)
            guardar_mensaje(numero, paciente_id, respuesta, es_bot=True)

            try:
                sid = enviar_mensaje(
                    numero, respuesta,
                    tipo=TipoRecordatorio.otro,
                    paciente_id=paciente_id,
                    registrar=False,
                )
                log.info(f'Respuesta del bot enviada a {numero}: SID={sid}')
                return sid
            except Exception as e:
                log.error(
                    f'No se pudo enviar la respuesta del bot a {numero}: {e}')
                return None


def responder_en_hilo(app, numero, paciente_id, body):
    """Arranca responder() en segundo plano y regresa de inmediato."""
    hilo = threading.Thread(
        target=responder,
        args=(app, numero, paciente_id, body),
        name=f'bot-respuesta-{numero}',
        daemon=True,
    )
    hilo.start()
    return hilo
