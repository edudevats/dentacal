import time
import logging
from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, text
from extensions import db, permiso_requerido
from models import ConversacionWhatsapp, Paciente, LogBot

log = logging.getLogger(__name__)

bot_bp = Blueprint('bot', __name__, url_prefix='/api/bot')


@bot_bp.before_request
@login_required
@permiso_requerido('bot')
def _check_permiso():
    pass


@bot_bp.route('/conversaciones', methods=['GET'])
@login_required
def listar_conversaciones():
    """Lista todas las conversaciones agrupadas por número, ordenadas por última interacción."""
    # Stats por número: última interacción y total de mensajes
    stats = db.session.query(
        ConversacionWhatsapp.numero_telefono,
        func.max(ConversacionWhatsapp.timestamp).label('ultima_interaccion'),
        func.count(ConversacionWhatsapp.id).label('total_mensajes'),
    ).group_by(ConversacionWhatsapp.numero_telefono).all()

    # Último mensaje de cada número (subquery por eficiencia)
    max_ts_sq = db.session.query(
        ConversacionWhatsapp.numero_telefono,
        func.max(ConversacionWhatsapp.timestamp).label('max_ts')
    ).group_by(ConversacionWhatsapp.numero_telefono).subquery()

    ultimos = db.session.query(ConversacionWhatsapp).join(
        max_ts_sq,
        db.and_(
            ConversacionWhatsapp.numero_telefono == max_ts_sq.c.numero_telefono,
            ConversacionWhatsapp.timestamp == max_ts_sq.c.max_ts
        )
    ).all()

    ultimo_por_numero = {m.numero_telefono: m for m in ultimos}

    # Mapa de pacientes por variantes del número (soporta multiples por numero)
    from routes.webhook_whatsapp import _variantes_numero_mx
    pacientes_map = {}  # numero -> list[Paciente]
    for p in Paciente.query.filter(
        Paciente.eliminado == False,
        Paciente.whatsapp.isnot(None)
    ).all():
        for variante in _variantes_numero_mx(p.whatsapp):
            pacientes_map.setdefault(variante, []).append(p)

    resultado = []
    for r in sorted(stats, key=lambda x: x.ultima_interaccion or '', reverse=True):
        # Buscar paciente usando todas las variantes del número de la conversación
        pacientes = pacientes_map.get(r.numero_telefono, [])
        if not pacientes:
            for v in _variantes_numero_mx(r.numero_telefono):
                pacientes = pacientes_map.get(v, [])
                if pacientes:
                    break

        paciente = pacientes[0] if pacientes else None
        ultimo = ultimo_por_numero.get(r.numero_telefono)
        item = {
            'numero_telefono': r.numero_telefono,
            'ultima_interaccion': r.ultima_interaccion.isoformat() if r.ultima_interaccion else None,
            'total_mensajes': r.total_mensajes,
            'ultimo_mensaje': (ultimo.mensaje or '')[:100] if ultimo else '',
            'ultimo_es_bot': ultimo.es_bot if ultimo else False,
            'paciente_id': paciente.id if paciente else None,
            'paciente_nombre': paciente.nombre_completo if paciente else None,
            'paciente_estatus_crm': paciente.estatus_crm.value if paciente and paciente.estatus_crm else None,
        }
        if len(pacientes) > 1:
            grupo = paciente.grupo_familiar if paciente else None
            item['grupo_familiar'] = grupo.nombre if grupo else None
            item['familia'] = [
                {'id': p.id, 'nombre': p.nombre_completo}
                for p in pacientes
            ]
        resultado.append(item)

    return jsonify(resultado)


@bot_bp.route('/hilo/<path:numero>', methods=['GET'])
@login_required
def hilo_conversacion(numero):
    """Devuelve el hilo completo de mensajes de un número."""
    mensajes = ConversacionWhatsapp.query.filter(
        ConversacionWhatsapp.numero_telefono == numero
    ).order_by(ConversacionWhatsapp.timestamp).all()

    return jsonify([{
        'id': m.id,
        'mensaje': m.mensaje,
        'es_bot': m.es_bot,
        'timestamp': m.timestamp.isoformat(),
        'paciente_id': m.paciente_id,
    } for m in mensajes])


# ── Status de APIs externas (solo admin) ────────────────────────────────────

def _mask(value, show=4):
    """Oculta una clave dejando visible solo los ultimos N caracteres."""
    if not value:
        return ''
    if len(value) <= show:
        return '*' * len(value)
    return '*' * (len(value) - show) + value[-show:]


def _check_gemini():
    """Verifica conexion con Gemini haciendo una peticion minima."""
    api_key = current_app.config.get('GEMINI_API_KEY', '')
    model = current_app.config.get('AI_MODEL', 'gemini-3.1-flash-lite-preview')

    if not api_key:
        return {'ok': False, 'estado': 'no_configurado',
                'detalle': 'GEMINI_API_KEY vacio en .env', 'modelo': model}
    if api_key.startswith('test'):
        return {'ok': False, 'estado': 'modo_test',
                'detalle': 'GEMINI_API_KEY en modo test', 'modelo': model}

    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        return {'ok': False, 'estado': 'sdk_faltante',
                'detalle': f'google-genai no instalado: {e}', 'modelo': model}

    try:
        t0 = time.time()
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=model,
            contents=[types.Content(role='user', parts=[types.Part(text='ping')])],
            config=types.GenerateContentConfig(
                max_output_tokens=5,
                temperature=0,
            ),
        )
        latencia_ms = int((time.time() - t0) * 1000)
        texto = ''
        try:
            if resp and resp.candidates:
                parts = resp.candidates[0].content.parts or []
                for p in parts:
                    if getattr(p, 'text', None):
                        texto = p.text[:40]
                        break
        except Exception:
            pass

        return {
            'ok': True,
            'estado': 'ok',
            'detalle': f'Respuesta recibida ({latencia_ms} ms)',
            'modelo': model,
            'latencia_ms': latencia_ms,
            'api_key_preview': _mask(api_key),
            'muestra_respuesta': texto,
        }
    except Exception as e:
        msg = str(e)[:200]
        log.warning(f'Gemini health check fallo: {e}')
        return {
            'ok': False,
            'estado': 'error',
            'detalle': msg,
            'modelo': model,
            'api_key_preview': _mask(api_key),
        }


def _check_twilio():
    """Verifica credenciales de Twilio obteniendo info de la cuenta."""
    sid = current_app.config.get('TWILIO_ACCOUNT_SID', '')
    token = current_app.config.get('TWILIO_AUTH_TOKEN', '')
    wa_number = current_app.config.get('TWILIO_WHATSAPP_NUMBER', '')

    if not sid or not token:
        return {'ok': False, 'estado': 'no_configurado',
                'detalle': 'TWILIO_ACCOUNT_SID o TWILIO_AUTH_TOKEN vacios',
                'numero_wa': wa_number}
    if sid.startswith('test'):
        return {'ok': False, 'estado': 'modo_test',
                'detalle': 'Credenciales Twilio en modo test',
                'numero_wa': wa_number}

    try:
        from twilio.rest import Client
    except ImportError as e:
        return {'ok': False, 'estado': 'sdk_faltante',
                'detalle': f'twilio no instalado: {e}',
                'numero_wa': wa_number}

    try:
        t0 = time.time()
        client = Client(sid, token)
        account = client.api.v2010.accounts(sid).fetch()
        latencia_ms = int((time.time() - t0) * 1000)
        return {
            'ok': account.status == 'active',
            'estado': account.status,
            'detalle': f'Cuenta "{account.friendly_name}" ({account.status})',
            'numero_wa': wa_number,
            'latencia_ms': latencia_ms,
            'sid_preview': _mask(sid),
        }
    except Exception as e:
        msg = str(e)[:200]
        log.warning(f'Twilio health check fallo: {e}')
        return {
            'ok': False,
            'estado': 'error',
            'detalle': msg,
            'numero_wa': wa_number,
            'sid_preview': _mask(sid),
        }


def _check_db():
    """Verifica que la BD responda."""
    try:
        t0 = time.time()
        db.session.execute(text('SELECT 1'))
        latencia_ms = int((time.time() - t0) * 1000)
        return {'ok': True, 'estado': 'ok',
                'detalle': f'Respuesta ({latencia_ms} ms)',
                'latencia_ms': latencia_ms}
    except Exception as e:
        return {'ok': False, 'estado': 'error', 'detalle': str(e)[:200]}


def _check_status_callback():
    """Verifica que PUBLIC_BASE_URL este configurado para el Status Callback."""
    base = current_app.config.get('PUBLIC_BASE_URL', '').strip()
    if not base:
        return {
            'ok': False,
            'estado': 'no_configurado',
            'detalle': 'PUBLIC_BASE_URL vacio — sin tracking de entrega de mensajes',
            'url': None,
        }
    url = f'{base.rstrip("/")}/webhook/whatsapp-status'
    return {'ok': True, 'estado': 'configurado',
            'detalle': 'Twilio enviara actualizaciones de entrega a esta URL',
            'url': url}


@bot_bp.route('/status-apis', methods=['GET'])
@login_required
def status_apis():
    """
    Estado de las APIs externas del bot (Gemini + Twilio + DB + Status Callback).
    Solo admin. Hace peticiones reales para verificar conectividad.
    """
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403

    gemini = _check_gemini()
    twilio = _check_twilio()
    base_db = _check_db()
    status_cb = _check_status_callback()

    # Global: ok solo si Gemini+Twilio+DB estan OK. Status callback es advertencia.
    global_ok = gemini['ok'] and twilio['ok'] and base_db['ok']

    return jsonify({
        'ok': global_ok,
        'timestamp': time.time(),
        'servicios': {
            'gemini': gemini,
            'twilio': twilio,
            'database': base_db,
            'status_callback': status_cb,
        }
    })


@bot_bp.route('/logs', methods=['GET'])
@login_required
def logs_bot():
    """Lista los logs del bot con paginación y filtros."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    nivel = request.args.get('nivel')  # error, warning, info

    q = LogBot.query.order_by(LogBot.created_at.desc())
    if nivel:
        q = q.filter(LogBot.nivel == nivel)

    total = q.count()
    logs = q.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'logs': [l.to_dict() for l in logs],
        'total': total,
        'page': page,
        'pages': (total + per_page - 1) // per_page,
    })


@bot_bp.route('/logs/<int:log_id>', methods=['DELETE'])
@login_required
def eliminar_log(log_id):
    """Elimina un log específico."""
    log_entry = LogBot.query.get_or_404(log_id)
    db.session.delete(log_entry)
    db.session.commit()
    return jsonify(ok=True)


@bot_bp.route('/logs/clear', methods=['DELETE'])
@login_required
def limpiar_logs():
    """Elimina todos los logs."""
    LogBot.query.delete()
    db.session.commit()
    return jsonify(ok=True)
