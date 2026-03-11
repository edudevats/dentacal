from flask import Blueprint, jsonify, request
from flask_login import login_required
from sqlalchemy import func
from extensions import db
from models import ConversacionWhatsapp, Paciente

bot_bp = Blueprint('bot', __name__, url_prefix='/api/bot')


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

    # Mapa de pacientes por variantes del número
    pacientes_map = {}
    for p in Paciente.query.filter(
        Paciente.eliminado == False,
        Paciente.whatsapp.isnot(None)
    ).all():
        wa = p.whatsapp
        wa_limpio = wa.replace('+', '').replace(' ', '')
        for variante in {wa, wa_limpio, f'+{wa_limpio}'}:
            if variante:
                pacientes_map[variante] = p

    resultado = []
    for r in sorted(stats, key=lambda x: x.ultima_interaccion or '', reverse=True):
        paciente = pacientes_map.get(r.numero_telefono)
        if not paciente:
            n_limpio = r.numero_telefono.replace('+', '').replace(' ', '')
            paciente = pacientes_map.get(n_limpio) or pacientes_map.get(f'+{n_limpio}')

        ultimo = ultimo_por_numero.get(r.numero_telefono)
        resultado.append({
            'numero_telefono': r.numero_telefono,
            'ultima_interaccion': r.ultima_interaccion.isoformat() if r.ultima_interaccion else None,
            'total_mensajes': r.total_mensajes,
            'ultimo_mensaje': (ultimo.mensaje or '')[:100] if ultimo else '',
            'ultimo_es_bot': ultimo.es_bot if ultimo else False,
            'paciente_id': paciente.id if paciente else None,
            'paciente_nombre': paciente.nombre_completo if paciente else None,
            'paciente_estatus_crm': paciente.estatus_crm.value if paciente and paciente.estatus_crm else None,
        })

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
