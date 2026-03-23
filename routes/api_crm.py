import json
import threading

from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user
from sqlalchemy import func
from extensions import db, scheduler, permiso_requerido
from models import (Paciente, EstatusCRM, EstatusCita, SeguimientoCRM, TipoSeguimiento,
                    ConversacionWhatsapp, Cita, Campana, CampanaDestinatario, EstatusCampana)
from datetime import datetime, timedelta

crm_bp = Blueprint('crm', __name__, url_prefix='/api/crm')


@crm_bp.before_request
@login_required
@permiso_requerido('crm')
def _check_permiso():
    pass


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
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400
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
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400

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
    data = request.get_json(silent=True) or {}
    if data.get('notas'):
        seg.notas = data['notas']
    db.session.commit()
    return jsonify(ok=True)


@crm_bp.route('/<int:paciente_id>/enviar-whatsapp', methods=['POST'])
@login_required
def enviar_whatsapp(paciente_id):
    p = Paciente.query.filter_by(id=paciente_id, eliminado=False).first_or_404()
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400
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


# ---- Campanas de WhatsApp masivo ----

@crm_bp.route('/campanas', methods=['GET'])
@login_required
def listar_campanas():
    campanas = Campana.query.order_by(Campana.created_at.desc()).all()
    return jsonify([c.to_dict() for c in campanas])


@crm_bp.route('/campanas', methods=['POST'])
@login_required
def crear_campana_endpoint():
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON invalido'), 400

    nombre = (data.get('nombre') or '').strip()
    mensaje = (data.get('mensaje') or '').strip()
    if not nombre or not mensaje:
        return jsonify(error='Nombre y mensaje son requeridos'), 400

    filtros = data.get('filtros', {})
    fecha_programada = None
    if data.get('fecha_programada'):
        try:
            fecha_programada = datetime.fromisoformat(data['fecha_programada'])
        except ValueError:
            return jsonify(error='Fecha programada invalida'), 400

    from services.campana_service import crear_campana
    campana = crear_campana(nombre, mensaje, filtros, fecha_programada, current_user.id)
    return jsonify(campana.to_dict()), 201


@crm_bp.route('/campanas/<int:campana_id>', methods=['GET'])
@login_required
def detalle_campana(campana_id):
    campana = db.session.get(Campana, campana_id)
    if not campana:
        return jsonify(error='Campana no encontrada'), 404

    data = campana.to_dict()
    data['destinatarios'] = [
        {
            'id': d.id,
            'paciente_id': d.paciente_id,
            'paciente_nombre': d.paciente.nombre_completo if d.paciente else '',
            'numero_destino': d.numero_destino,
            'estatus': d.estatus.value if d.estatus else 'pendiente',
            'error_mensaje': d.error_mensaje,
            'fecha_envio': d.fecha_envio.isoformat() if d.fecha_envio else None,
        }
        for d in campana.destinatarios
    ]
    return jsonify(data)


@crm_bp.route('/campanas/preview', methods=['POST'])
@login_required
def preview_audiencia():
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON invalido'), 400

    filtros = data.get('filtros', {})

    from services.campana_service import obtener_audiencia
    pacientes = obtener_audiencia(filtros)

    muestra = [
        {'id': p.id, 'nombre': p.nombre_completo, 'whatsapp': p.numero_contacto_wa}
        for p in pacientes[:10]
    ]

    return jsonify(total=len(pacientes), muestra=muestra)


@crm_bp.route('/campanas/<int:campana_id>/enviar', methods=['POST'])
@login_required
def enviar_campana_endpoint(campana_id):
    campana = db.session.get(Campana, campana_id)
    if not campana:
        return jsonify(error='Campana no encontrada'), 404

    if campana.estatus != EstatusCampana.borrador:
        return jsonify(error='Solo se pueden enviar campanas en estado borrador'), 400

    from services.campana_service import preparar_destinatarios, enviar_campana, programar_campana

    total = preparar_destinatarios(campana)
    if total == 0:
        return jsonify(error='No hay destinatarios que cumplan los filtros'), 400

    if campana.fecha_programada and campana.fecha_programada > datetime.utcnow():
        programar_campana(campana.id, current_app._get_current_object(), scheduler)
        return jsonify(ok=True, total_destinatarios=total, programada=True)
    else:
        app = current_app._get_current_object()
        thread = threading.Thread(
            target=enviar_campana,
            args=(campana.id, app),
            daemon=True,
        )
        thread.start()
        return jsonify(ok=True, total_destinatarios=total, programada=False)


@crm_bp.route('/campanas/<int:campana_id>', methods=['DELETE'])
@login_required
def eliminar_campana(campana_id):
    campana = db.session.get(Campana, campana_id)
    if not campana:
        return jsonify(error='Campana no encontrada'), 404

    if campana.estatus in (EstatusCampana.enviando, EstatusCampana.completada):
        return jsonify(error='No se puede eliminar una campana en envio o completada'), 400

    if campana.estatus == EstatusCampana.programada:
        # Cancelar job del scheduler
        job_id = f'campana_{campana_id}'
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
        campana.estatus = EstatusCampana.cancelada
        db.session.commit()
        return jsonify(ok=True, cancelada=True)

    # Borrador: eliminar completamente
    db.session.delete(campana)
    db.session.commit()
    return jsonify(ok=True)
