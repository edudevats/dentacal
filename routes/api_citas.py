from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from extensions import db, permiso_requerido
from models import (Cita, Paciente, Dentista, Consultorio, TipoCita,
                    EstatusCita, EstatusCRM)
from services.scheduler_service import verificar_disponibilidad, obtener_slots_disponibles
from datetime import datetime
import pytz

citas_bp = Blueprint('citas', __name__, url_prefix='/api/citas')


@citas_bp.before_request
@login_required
@permiso_requerido('calendario')
def _check_permiso():
    pass

TIMEZONE = pytz.timezone('America/Mexico_City')


@citas_bp.route('', methods=['GET'])
@login_required
def listar():
    fecha_str = request.args.get('fecha')
    dentista_id = request.args.get('dentista_id', type=int)
    consultorio_id = request.args.get('consultorio_id', type=int)

    q = Cita.query.filter(Cita.paciente.has(eliminado=False))

    if fecha_str:
        try:
            fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            inicio = datetime(fecha.year, fecha.month, fecha.day, 0, 0, 0)
            fin = datetime(fecha.year, fecha.month, fecha.day, 23, 59, 59)
            q = q.filter(Cita.fecha_inicio >= inicio, Cita.fecha_inicio <= fin)
        except ValueError:
            pass
    if dentista_id:
        q = q.filter_by(dentista_id=dentista_id)
    if consultorio_id:
        q = q.filter_by(consultorio_id=consultorio_id)

    citas = q.order_by(Cita.fecha_inicio).all()
    return jsonify([c.to_dict() for c in citas])


@citas_bp.route('/<int:cita_id>', methods=['GET'])
@login_required
def detalle(cita_id):
    cita = Cita.query.get_or_404(cita_id)
    return jsonify(cita.to_dict())


@citas_bp.route('', methods=['POST'])
@login_required
def crear():
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400

    # Validar campos requeridos
    required = ['paciente_id', 'dentista_id', 'consultorio_id', 'fecha_inicio', 'fecha_fin']
    for field in required:
        if not data.get(field):
            return jsonify(error=f'Campo requerido: {field}'), 400

    try:
        fecha_inicio = datetime.fromisoformat(data['fecha_inicio'])
        fecha_fin = datetime.fromisoformat(data['fecha_fin'])
    except ValueError:
        return jsonify(error='Formato de fecha invalido (ISO 8601)'), 400

    if fecha_fin <= fecha_inicio:
        return jsonify(error='La fecha de fin debe ser posterior al inicio'), 400

    # Verificar paciente
    paciente = Paciente.query.filter_by(id=data['paciente_id'], eliminado=False).first()
    if not paciente:
        return jsonify(error='Paciente no encontrado'), 404

    # Verificar dentista y consultorio
    Dentista.query.get_or_404(data['dentista_id'])
    Consultorio.query.get_or_404(data['consultorio_id'])

    # Verificar disponibilidad (sin colisiones)
    conflicto = verificar_disponibilidad(
        dentista_id=data['dentista_id'],
        consultorio_id=data['consultorio_id'],
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )
    if conflicto:
        return jsonify(
            error='Conflicto de horario',
            conflicto={
                'id': conflicto.id,
                'dentista': conflicto.dentista.nombre,
                'consultorio': conflicto.consultorio.nombre,
                'inicio': conflicto.fecha_inicio.isoformat(),
            }
        ), 409

    cita = Cita(
        paciente_id=data['paciente_id'],
        dentista_id=data['dentista_id'],
        consultorio_id=data['consultorio_id'],
        tipo_cita_id=data.get('tipo_cita_id'),
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        notas=data.get('notas', ''),
        anticipo_pagado=bool(data.get('anticipo_pagado', False)),
        anticipo_monto=data.get('anticipo_monto', 0),
        created_by=current_user.id,
    )
    db.session.add(cita)

    # Actualizar ultima_cita del paciente y CRM status
    paciente.ultima_cita = fecha_inicio
    if paciente.estatus_crm.value == 'prospecto':
        paciente.estatus_crm = EstatusCRM.activo

    db.session.commit()
    return jsonify(cita.to_dict()), 201


@citas_bp.route('/<int:cita_id>', methods=['PUT'])
@login_required
def actualizar(cita_id):
    cita = Cita.query.get_or_404(cita_id)
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400

    if 'fecha_inicio' in data and 'fecha_fin' in data:
        try:
            nueva_inicio = datetime.fromisoformat(data['fecha_inicio'])
            nueva_fin = datetime.fromisoformat(data['fecha_fin'])
        except ValueError:
            return jsonify(error='Formato de fecha invalido'), 400

        conflicto = verificar_disponibilidad(
            dentista_id=data.get('dentista_id', cita.dentista_id),
            consultorio_id=data.get('consultorio_id', cita.consultorio_id),
            fecha_inicio=nueva_inicio,
            fecha_fin=nueva_fin,
            ignorar_cita_id=cita_id,
        )
        if conflicto:
            return jsonify(error='Conflicto de horario', conflicto_id=conflicto.id), 409

        cita.fecha_inicio = nueva_inicio
        cita.fecha_fin = nueva_fin
        cita.reminder_24h_sent = False  # resetear reminder si se reprograma

    if 'status' in data:
        try:
            new_status = EstatusCita[data['status']]
            old_status = cita.status
            cita.status = new_status

            # Auto-set confirmacion_fecha al confirmar
            if new_status == EstatusCita.confirmada and not cita.confirmacion_fecha:
                cita.confirmacion_fecha = datetime.utcnow()

            # Al completar: actualizar ultima_cita del paciente
            if new_status == EstatusCita.completada:
                paciente = cita.paciente
                if paciente:
                    paciente.ultima_cita = cita.fecha_inicio
                # Guardar proximo_recordatorio_fecha si viene en el request
                if data.get('proximo_recordatorio_fecha') and cita.paciente:
                    try:
                        cita.paciente.proximo_recordatorio_fecha = datetime.strptime(
                            data['proximo_recordatorio_fecha'], '%Y-%m-%d'
                        ).date()
                    except ValueError:
                        pass

            # Al marcar no asistencia: enviar WA ofreciendo reagendar
            if new_status == EstatusCita.no_asistencia and old_status != EstatusCita.no_asistencia:
                try:
                    from services.whatsapp_service import enviar_reagendar_no_asistencia
                    enviar_reagendar_no_asistencia(cita)
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f'Error enviando msg no-asistencia: {e}')
        except KeyError:
            return jsonify(error='Status invalido'), 400

    if 'dentista_id' in data:
        cita.dentista_id = data['dentista_id']
    if 'consultorio_id' in data:
        cita.consultorio_id = data['consultorio_id']
    if 'tipo_cita_id' in data:
        cita.tipo_cita_id = data['tipo_cita_id']
    if 'notas' in data:
        cita.notas = data['notas']
    if 'anticipo_pagado' in data:
        anticipo_anterior = cita.anticipo_pagado
        cita.anticipo_pagado = bool(data['anticipo_pagado'])

        # Anticipo recien marcado como pagado → promover pre_cita + notificar
        if cita.anticipo_pagado and not anticipo_anterior:
            # Si era pre-cita, promover a pendiente
            if cita.status == EstatusCita.pre_cita:
                cita.status = EstatusCita.pendiente
                cita.pre_cita_expira = None

            # Notificar al paciente por WhatsApp
            _notificar_anticipo_recibido(cita)

    if 'anticipo_monto' in data:
        cita.anticipo_monto = data['anticipo_monto']

    db.session.commit()
    return jsonify(cita.to_dict())


@citas_bp.route('/<int:cita_id>', methods=['DELETE'])
@login_required
def cancelar(cita_id):
    cita = Cita.query.get_or_404(cita_id)
    cita.status = EstatusCita.cancelada
    db.session.commit()
    return jsonify(ok=True)


@citas_bp.route('/disponibilidad', methods=['GET'])
@login_required
def disponibilidad():
    """Retorna slots libres para un dentista en una fecha."""
    fecha_str = request.args.get('fecha')
    dentista_id = request.args.get('dentista_id', type=int)
    consultorio_id = request.args.get('consultorio_id', type=int)
    duracion = request.args.get('duracion', 60, type=int)

    if not fecha_str or not dentista_id:
        return jsonify(error='fecha y dentista_id son requeridos'), 400

    if duracion not in [15, 30, 45, 60, 90, 120]:
        return jsonify(error='Duracion invalida'), 400

    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify(error='Formato de fecha invalido'), 400

    slots = obtener_slots_disponibles(
        fecha=fecha,
        dentista_id=dentista_id,
        consultorio_id=consultorio_id,
        duracion_minutos=duracion,
    )
    return jsonify(slots=slots, fecha=fecha_str, duracion=duracion)


@citas_bp.route('/resumen-dia', methods=['GET'])
@login_required
def resumen_dia():
    """Resumen de citas del dia para enviar a doctores."""
    fecha_str = request.args.get('fecha')
    dentista_id = request.args.get('dentista_id', type=int)

    if not fecha_str:
        from datetime import date
        fecha_str = date.today().isoformat()

    try:
        fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify(error='Formato invalido'), 400

    inicio = datetime(fecha.year, fecha.month, fecha.day, 0, 0, 0)
    fin = datetime(fecha.year, fecha.month, fecha.day, 23, 59, 59)

    q = Cita.query.filter(
        Cita.fecha_inicio >= inicio,
        Cita.fecha_inicio <= fin,
        Cita.status.in_([EstatusCita.pendiente, EstatusCita.confirmada])
    )
    if dentista_id:
        q = q.filter_by(dentista_id=dentista_id)

    citas = q.order_by(Cita.dentista_id, Cita.fecha_inicio).all()
    return jsonify([c.to_dict() for c in citas])


def _notificar_anticipo_recibido(cita):
    """Envia WhatsApp al paciente confirmando la recepcion del anticipo."""
    import logging
    log = logging.getLogger(__name__)

    paciente = cita.paciente
    if not paciente:
        return

    numero = getattr(paciente, 'numero_contacto_wa', None) or paciente.whatsapp
    if not numero:
        return

    nombre = paciente.nombre_completo
    fecha_str = cita.fecha_inicio.strftime('%d/%m/%Y')
    hora_str = cita.fecha_inicio.strftime('%H:%M')
    hora_fin_str = cita.fecha_fin.strftime('%H:%M')
    dentista = cita.dentista.nombre if cita.dentista else 'su doctor'

    mensaje = (
        f'Hola {nombre} \U0001f60a\n\n'
        f'Hemos recibido su anticipo correctamente \u2705\n'
        f'Su cita queda confirmada:\n\n'
        f'\U0001f4c5 Fecha: {fecha_str}\n'
        f'\U0001f552 Horario: {hora_str} a {hora_fin_str}\n'
        f'\U0001f9b7 Doctor(a): {dentista}\n\n'
        f'Le esperamos en La Casa del Sr. Perez. '
        f'Si necesita reagendar, por favor hagalo con al menos 24hrs de anticipacion.\n'
        f'\U00002728 Gracias por su confianza!'
    )

    try:
        from services.whatsapp_service import enviar_mensaje
        enviar_mensaje(numero, mensaje)
        log.info(f'Notificacion anticipo enviada a {numero} (cita #{cita.id})')

        # Guardar en historial de conversacion
        from models import ConversacionWhatsapp
        conv = ConversacionWhatsapp(
            numero_telefono=numero,
            paciente_id=paciente.id,
            mensaje=mensaje,
            es_bot=True,
        )
        db.session.add(conv)
    except Exception as e:
        log.error(f'Error enviando notificacion anticipo cita #{cita.id}: {e}')
