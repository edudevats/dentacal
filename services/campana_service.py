"""
Servicio de campanas de WhatsApp masivo.
Maneja la logica de audiencia, envio y programacion de campanas.
"""
import json
import logging
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta

from extensions import db
from models import (Paciente, EstatusCRM, Campana, CampanaDestinatario,
                    EstatusCampana, EstatusDestinatario, ConversacionWhatsapp)

logger = logging.getLogger(__name__)


def obtener_audiencia(filtros_dict):
    """
    Retorna lista de pacientes que cumplen los filtros.
    Siempre excluye eliminados y problematicos.
    filtros_dict: {
        "estatus_crm": ["baja", "activo", ...],
        "meses_sin_cita": 6  (0 = cualquiera)
    }
    """
    q = Paciente.query.filter_by(eliminado=False, es_problematico=False)

    # Filtro por estatus CRM
    estatus_list = filtros_dict.get('estatus_crm', [])
    if estatus_list:
        enums = []
        for e in estatus_list:
            try:
                enums.append(EstatusCRM[e])
            except KeyError:
                pass
        if enums:
            q = q.filter(Paciente.estatus_crm.in_(enums))

    # Filtro por meses sin cita
    meses = filtros_dict.get('meses_sin_cita', 0)
    if meses and int(meses) > 0:
        fecha_limite = datetime.utcnow() - relativedelta(months=int(meses))
        q = q.filter(
            db.or_(
                Paciente.ultima_cita == None,
                Paciente.ultima_cita < fecha_limite,
            )
        )

    pacientes = q.all()

    # Solo pacientes con numero de WhatsApp valido
    return [p for p in pacientes if p.numero_contacto_wa]


def crear_campana(nombre, mensaje, filtros, fecha_programada, user_id):
    """Crea una campana en estado borrador."""
    campana = Campana(
        nombre=nombre,
        mensaje=mensaje,
        filtros=json.dumps(filtros) if filtros else '{}',
        estatus=EstatusCampana.borrador,
        fecha_programada=fecha_programada,
        created_by=user_id,
    )
    db.session.add(campana)
    db.session.commit()
    return campana


def preparar_destinatarios(campana):
    """
    Genera la lista de destinatarios a partir de los filtros.
    Retorna la cantidad de destinatarios creados.
    """
    filtros = json.loads(campana.filtros) if campana.filtros else {}
    pacientes = obtener_audiencia(filtros)

    count = 0
    for p in pacientes:
        numero = p.numero_contacto_wa
        if not numero:
            continue
        dest = CampanaDestinatario(
            campana_id=campana.id,
            paciente_id=p.id,
            numero_destino=numero,
            estatus=EstatusDestinatario.pendiente,
        )
        db.session.add(dest)
        count += 1

    campana.total_destinatarios = count
    db.session.commit()
    return count


def enviar_campana(campana_id, app):
    """
    Envia la campana a todos los destinatarios pendientes.
    Se ejecuta en un thread de background o desde el scheduler.
    """
    with app.app_context():
        from services.whatsapp_service import enviar_mensaje

        campana = db.session.get(Campana, campana_id)
        if not campana:
            logger.error(f'Campana {campana_id} no encontrada')
            return

        campana.estatus = EstatusCampana.enviando
        campana.fecha_envio_inicio = datetime.utcnow()
        db.session.commit()

        destinatarios = CampanaDestinatario.query.filter_by(
            campana_id=campana_id,
            estatus=EstatusDestinatario.pendiente,
        ).all()

        for dest in destinatarios:
            # Personalizar mensaje
            mensaje = campana.mensaje.replace(
                '{nombre_paciente}',
                dest.paciente.nombre_completo if dest.paciente else ''
            )

            try:
                sid = enviar_mensaje(dest.numero_destino, mensaje)
                dest.estatus = EstatusDestinatario.enviado
                dest.fecha_envio = datetime.utcnow()
                dest.message_sid = sid
                dest.delivery_status = 'queued'
                campana.enviados += 1

                # Guardar en historial de conversacion
                conv = ConversacionWhatsapp(
                    numero_telefono=dest.numero_destino,
                    paciente_id=dest.paciente_id,
                    mensaje=mensaje,
                    es_bot=True,
                    timestamp=datetime.utcnow(),
                )
                db.session.add(conv)
            except Exception as e:
                dest.estatus = EstatusDestinatario.fallido
                dest.error_mensaje = str(e)[:500]
                campana.fallidos += 1
                logger.error(f'Campana {campana_id} - Error enviando a {dest.numero_destino}: {e}')

            db.session.commit()

            # Rate limiting para Twilio
            time.sleep(1)

        campana.estatus = EstatusCampana.completada
        campana.fecha_envio_fin = datetime.utcnow()
        db.session.commit()

        logger.info(
            f'Campana {campana_id} completada: '
            f'{campana.enviados} enviados, {campana.fallidos} fallidos'
        )


def programar_campana(campana_id, app, scheduler):
    """Registra un job APScheduler para enviar la campana en la fecha programada."""
    campana = db.session.get(Campana, campana_id)
    if not campana or not campana.fecha_programada:
        return False

    job_id = f'campana_{campana_id}'
    scheduler.add_job(
        func=enviar_campana,
        trigger='date',
        run_date=campana.fecha_programada,
        id=job_id,
        replace_existing=True,
        args=[campana_id, app],
    )

    campana.estatus = EstatusCampana.programada
    db.session.commit()
    logger.info(f'Campana {campana_id} programada para {campana.fecha_programada}')
    return True
