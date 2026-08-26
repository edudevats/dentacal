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

# Prefijo de las respuestas que Twilio rechazo. Se guardan en el hilo para que
# recepcion vea que el paciente NO fue contestado, y se filtran del historial
# que lee Gemini: el bot no dijo eso, no debe creer que lo dijo.
MARCA_NO_ENVIADO = '[NO SE ENVIO'

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
    """
    Registra una linea de la conversacion. Nunca propaga la excepcion.

    Reintenta una vez tras el rollback: si una tool tumbo la conexion a MySQL,
    la sesion queda envenenada y el primer commit falla aunque la BD ya este
    de vuelta. Sin el reintento se perdia la respuesta del bot del historial.
    """
    for intento in (1, 2):
        try:
            conv = ConversacionWhatsapp(
                numero_telefono=numero,
                paciente_id=paciente_id,
                mensaje=mensaje,
                es_bot=es_bot,
            )
            db.session.add(conv)
            db.session.commit()
            return True
        except Exception as e:
            log.error(f'Error guardando conversacion (intento {intento}): {e}')
            try:
                db.session.rollback()
            except Exception as e2:
                log.error(f'Rollback fallido guardando conversacion: {e2}')
                return False
    return False


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

    from services.twilio_errores import motivo_envio

    with app.app_context():
        with _lock_de(numero):
            respuesta = calcular_respuesta(numero, paciente_id, body)

            # Enviar ANTES de guardar. Al reves, un envio rechazado (tope de
            # cuota, numero invalido) dejaba la respuesta en el hilo como si
            # hubiera salido, y recepcion daba al paciente por atendido.
            try:
                sid = enviar_mensaje(
                    numero, respuesta,
                    tipo=TipoRecordatorio.otro,
                    paciente_id=paciente_id,
                    registrar=False,
                )
            except Exception as e:
                motivo = motivo_envio(e)
                log.error(
                    f'No se pudo enviar la respuesta del bot a {numero}: {e}')
                guardar_mensaje(
                    numero, paciente_id,
                    f'{MARCA_NO_ENVIADO}: {motivo}] {respuesta}',
                    es_bot=True)
                return None

            guardar_mensaje(numero, paciente_id, respuesta, es_bot=True)
            log.info(f'Respuesta del bot enviada a {numero}: SID={sid}')
            return sid


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
