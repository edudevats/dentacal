from flask import Blueprint, jsonify, request
from flask_login import login_required
from sqlalchemy import func
from extensions import db
from models import (Paciente, EstatusCRM, EstatusCita, SeguimientoCRM, TipoSeguimiento,
                    ConversacionWhatsapp, Cita)
from datetime import datetime, timedelta

crm_bp = Blueprint('crm', __name__, url_prefix='/api/crm')


@crm_bp.route('', methods=['GET'])
@login_required
def listar():
    q = Paciente.query.filter_by(eliminado=False)

    estatus = request.args.get('estatus')
    if estatus:
        try:
            q = q.filter_by(estatus_crm=EstatusCRM[estatus])
        except KeyError:
            pass

    pacientes = q.order_by(Paciente.estatus_crm, Paciente.nombre).all()

    # Última interacción bot por paciente (una sola query)
    ultima_bot_rows = db.session.query(
        ConversacionWhatsapp.paciente_id,
        func.max(ConversacionWhatsapp.timestamp).label('ultima_bot')
    ).filter(ConversacionWhatsapp.paciente_id.isnot(None))\
     .group_by(ConversacionWhatsapp.paciente_id).all()
    ultima_bot_map = {r.paciente_id: r.ultima_bot for r in ultima_bot_rows}

    resultado = []
    for p in pacientes:
        d = p.to_dict()
        # Siguiente seguimiento pendiente
        siguiente = SeguimientoCRM.query.filter_by(
            paciente_id=p.id, completado=False
        ).order_by(SeguimientoCRM.fecha_programada).first()
        d['siguiente_seguimiento'] = {
            'tipo': siguiente.tipo.value,
            'fecha': siguiente.fecha_programada.isoformat() if siguiente.fecha_programada else None,
        } if siguiente else None
        # Última interacción con el bot
        ub = ultima_bot_map.get(p.id)
        d['ultima_interaccion_bot'] = ub.isoformat() if ub else None
        resultado.append(d)
    return jsonify(resultado)


@crm_bp.route('/<int:paciente_id>', methods=['GET'])
@login_required
def detalle_crm(paciente_id):
    p = Paciente.query.filter_by(id=paciente_id, eliminado=False).first_or_404()
    data = p.to_dict()

    data['seguimientos'] = [
        {
            'id': s.id,
            'tipo': s.tipo.value,
            'fecha_programada': s.fecha_programada.isoformat() if s.fecha_programada else None,
            'completado': s.completado,
            'notas': s.notas or '',
        }
        for s in p.seguimientos
    ]

    # Historial de citas
    citas = Cita.query.filter_by(paciente_id=paciente_id)\
        .order_by(Cita.fecha_inicio.desc()).limit(10).all()
    data['citas'] = [c.to_dict() for c in citas]

    # Historial de asistencias (citas completadas o no_asistencia)
    asistencias_query = Cita.query.filter(
        Cita.paciente_id == paciente_id,
        Cita.status.in_([EstatusCita.completada, EstatusCita.no_asistencia]),
    ).order_by(Cita.fecha_inicio.desc()).all()

    data['historial_asistencias'] = [
        {
            'id': c.id,
            'fecha': c.fecha_inicio.isoformat(),
            'tipo_cita': c.tipo_cita.nombre if c.tipo_cita else 'Cita',
            'dentista': c.dentista.nombre if c.dentista else '',
            'status': c.status.value,
            'confirmacion_fecha': c.confirmacion_fecha.isoformat() if c.confirmacion_fecha else None,
        }
        for c in asistencias_query
    ]

    total_asist = len(asistencias_query)
    asistio = sum(1 for c in asistencias_query if c.status == EstatusCita.completada)
    no_asistio = total_asist - asistio
    data['estadisticas_asistencia'] = {
        'total': total_asist,
        'asistencias': asistio,
        'inasistencias': no_asistio,
        'tasa_asistencia': round((asistio / total_asist * 100) if total_asist > 0 else 0, 1),
    }

    return jsonify(data)


@crm_bp.route('/<int:paciente_id>/estatus', methods=['PUT'])
@login_required
def cambiar_estatus(paciente_id):
    p = Paciente.query.filter_by(id=paciente_id, eliminado=False).first_or_404()
    data = request.get_json(force=True)
    nuevo_estatus = data.get('estatus')

    if p.es_problematico and nuevo_estatus != 'baja':
        return jsonify(error='Este paciente esta marcado como problematico. Debe desmarcarlo primero antes de cambiar su estatus.'), 400

    try:
        p.estatus_crm = EstatusCRM[nuevo_estatus]
    except KeyError:
        return jsonify(error='Estatus invalido. Valores: alta, activo, prospecto, baja'), 400

    db.session.commit()
    return jsonify(ok=True, estatus=p.estatus_crm.value)


@crm_bp.route('/<int:paciente_id>/seguimiento', methods=['POST'])
@login_required
def crear_seguimiento(paciente_id):
    p = Paciente.query.filter_by(id=paciente_id, eliminado=False).first_or_404()
    data = request.get_json(force=True)

    tipo_str = data.get('tipo', 'whatsapp_1')
    try:
        tipo = TipoSeguimiento[tipo_str]
    except KeyError:
        return jsonify(error='Tipo invalido'), 400

    fecha_programada = None
    if data.get('fecha_programada'):
        try:
            fecha_programada = datetime.fromisoformat(data['fecha_programada'])
        except ValueError:
            pass

    seg = SeguimientoCRM(
        paciente_id=paciente_id,
        tipo=tipo,
        fecha_programada=fecha_programada,
        notas=data.get('notas', ''),
    )
    db.session.add(seg)
    db.session.commit()
    return jsonify(id=seg.id), 201


@crm_bp.route('/seguimiento/<int:seg_id>/completar', methods=['POST'])
@login_required
def completar_seguimiento(seg_id):
    seg = SeguimientoCRM.query.get_or_404(seg_id)
    seg.completado = True
    seg.fecha_enviado = datetime.utcnow()
    data = request.get_json(force=True) or {}
    if data.get('notas'):
        seg.notas = data['notas']
    db.session.commit()
    return jsonify(ok=True)


@crm_bp.route('/<int:paciente_id>/enviar-whatsapp', methods=['POST'])
@login_required
def enviar_whatsapp(paciente_id):
    p = Paciente.query.filter_by(id=paciente_id, eliminado=False).first_or_404()
    data = request.get_json(force=True)
    mensaje = data.get('mensaje', '').strip()
    numero = p.numero_contacto_wa

    if not mensaje:
        return jsonify(error='El mensaje es requerido'), 400
    if not numero:
        return jsonify(error='El paciente no tiene numero de WhatsApp'), 400

    try:
        from services.whatsapp_service import enviar_mensaje
        sid = enviar_mensaje(numero, mensaje)
        # Guardar en historial
        _guardar_conversacion(numero, p.id, mensaje, es_bot=True)
        return jsonify(ok=True, sid=sid)
    except Exception as e:
        return jsonify(error=str(e)), 500


@crm_bp.route('/<int:paciente_id>/conversacion', methods=['GET'])
@login_required
def conversacion(paciente_id):
    p = Paciente.query.filter_by(id=paciente_id, eliminado=False).first_or_404()
    numero = p.numero_contacto_wa

    mensajes = ConversacionWhatsapp.query.filter(
        db.or_(
            ConversacionWhatsapp.paciente_id == paciente_id,
            ConversacionWhatsapp.numero_telefono == numero,
        )
    ).order_by(ConversacionWhatsapp.timestamp).all()

    return jsonify([{
        'id': m.id,
        'mensaje': m.mensaje,
        'es_bot': m.es_bot,
        'timestamp': m.timestamp.isoformat(),
    } for m in mensajes])


def _guardar_conversacion(numero, paciente_id, mensaje, es_bot=False):
    conv = ConversacionWhatsapp(
        numero_telefono=numero,
        paciente_id=paciente_id,
        mensaje=mensaje,
        es_bot=es_bot,
    )
    db.session.add(conv)
    db.session.commit()
