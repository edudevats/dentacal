"""
Tareas programadas con APScheduler.
- Recordatorios 24h antes de la cita
- Postconsulta 2 dias despues
- Seguimientos CRM automaticos
- Resumen diario a doctores
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo('America/Mexico_City')


def _ahora_local():
    """Retorna datetime actual en la timezone del consultorio."""
    return datetime.now(TIMEZONE).replace(tzinfo=None)


def setup_scheduler_jobs(scheduler, app):
    """Registra todos los jobs del scheduler."""

    # Recordatorios 24h - cada hora
    scheduler.add_job(
        func=_job_recordatorios_24h,
        trigger='interval',
        hours=1,
        id='recordatorios_24h',
        replace_existing=True,
        kwargs={'app': app},
    )

    # Postconsulta - diario a las 10am
    scheduler.add_job(
        func=_job_postconsulta,
        trigger='cron',
        hour=10,
        minute=0,
        id='postconsulta',
        replace_existing=True,
        kwargs={'app': app},
    )

    # Resumen diario a doctores - cada dia a las 8pm
    scheduler.add_job(
        func=_job_resumen_doctores,
        trigger='cron',
        hour=20,
        minute=0,
        id='resumen_doctores',
        replace_existing=True,
        kwargs={'app': app},
    )

    # Seguimientos CRM - diario a las 9am
    scheduler.add_job(
        func=_job_seguimientos_crm,
        trigger='cron',
        hour=9,
        minute=0,
        id='seguimientos_crm',
        replace_existing=True,
        kwargs={'app': app},
    )

    # Mensajes de cumpleanos - diario a las 10am
    scheduler.add_job(
        func=_job_cumpleanos,
        trigger='cron',
        hour=10,
        minute=30,
        id='cumpleanos',
        replace_existing=True,
        kwargs={'app': app},
    )

    # Recordatorio proxima visita - 1ro de cada mes a las 10:15am
    scheduler.add_job(
        func=_job_recordatorio_proxima_visita,
        trigger='cron',
        day=1,
        hour=10,
        minute=15,
        id='recordatorio_proxima_visita',
        replace_existing=True,
        kwargs={'app': app},
    )

    logger.info('Jobs del scheduler registrados.')


def _job_recordatorios_24h(app):
    """Envia recordatorios 24h antes de las citas."""
    with app.app_context():
        from models import Cita, EstatusCita, Recordatorio, TipoRecordatorio, EstatusRecordatorio
        from extensions import db

        ahora = _ahora_local()
        ventana_inicio = ahora + timedelta(hours=23)
        ventana_fin = ahora + timedelta(hours=25)

        citas = Cita.query.filter(
            Cita.fecha_inicio >= ventana_inicio,
            Cita.fecha_inicio <= ventana_fin,
            Cita.status.in_([EstatusCita.pendiente, EstatusCita.confirmada]),
            Cita.reminder_24h_sent == False,
        ).all()

        for cita in citas:
            if cita.paciente and cita.paciente.es_problematico:
                logger.info(f'Saltando recordatorio para paciente problematico: cita {cita.id}')
                continue
            try:
                from services.whatsapp_service import enviar_recordatorio_cita
                enviado = enviar_recordatorio_cita(cita)
                status = EstatusRecordatorio.enviado if enviado else EstatusRecordatorio.fallido

                recordatorio = Recordatorio(
                    cita_id=cita.id,
                    tipo=TipoRecordatorio.confirmacion_24h,
                    fecha_envio=_ahora_local(),
                    status=status,
                )
                db.session.add(recordatorio)
                cita.reminder_24h_sent = True
                db.session.commit()
                logger.info(f'Recordatorio enviado para cita {cita.id}')
            except Exception as e:
                logger.error(f'Error en recordatorio cita {cita.id}: {e}')
                db.session.rollback()


def _job_postconsulta(app):
    """Envia mensaje postconsulta 2 dias despues de citas completadas."""
    with app.app_context():
        from models import Cita, EstatusCita
        from extensions import db

        ahora = _ahora_local()
        # Citas de hace 2 dias (±2 horas)
        hace_2_dias_inicio = ahora - timedelta(days=2, hours=2)
        hace_2_dias_fin = ahora - timedelta(days=1, hours=22)

        citas = Cita.query.filter(
            Cita.fecha_inicio >= hace_2_dias_inicio,
            Cita.fecha_inicio <= hace_2_dias_fin,
            Cita.status == EstatusCita.completada,
            Cita.postconsulta_sent == False,
        ).all()

        for cita in citas:
            if cita.paciente and cita.paciente.es_problematico:
                logger.info(f'Saltando postconsulta para paciente problematico: cita {cita.id}')
                continue
            try:
                from services.whatsapp_service import enviar_postconsulta
                enviado = enviar_postconsulta(cita)
                if enviado:
                    cita.postconsulta_sent = True
                    db.session.commit()
                    logger.info(f'Postconsulta enviada para cita {cita.id}')
            except Exception as e:
                logger.error(f'Error postconsulta cita {cita.id}: {e}')
                db.session.rollback()


def _job_resumen_doctores(app):
    """Envia resumen de citas del siguiente dia a cada doctor."""
    with app.app_context():
        from models import Cita, Dentista, EstatusCita

        manana = _ahora_local().date() + timedelta(days=1)
        inicio = datetime(manana.year, manana.month, manana.day, 0, 0, 0)
        fin = datetime(manana.year, manana.month, manana.day, 23, 59, 59)
        fecha_str = manana.strftime('%d/%m/%Y')

        dentistas = Dentista.query.filter_by(activo=True).all()
        for dentista in dentistas:
            citas = Cita.query.filter(
                Cita.dentista_id == dentista.id,
                Cita.fecha_inicio >= inicio,
                Cita.fecha_inicio <= fin,
                Cita.status.in_([EstatusCita.pendiente, EstatusCita.confirmada]),
            ).order_by(Cita.fecha_inicio).all()

            if citas and dentista.telefono:
                try:
                    from services.whatsapp_service import enviar_resumen_diario_doctor
                    enviar_resumen_diario_doctor(dentista, citas, fecha_str)
                except Exception as e:
                    logger.error(f'Error resumen doctor {dentista.nombre}: {e}')


def _job_seguimientos_crm(app):
    """Crea seguimientos automaticos para pacientes que no han regresado."""
    with app.app_context():
        from models import Paciente, EstatusCRM, SeguimientoCRM, TipoSeguimiento, Cita
        from extensions import db

        hoy = _ahora_local().date()

        # Pacientes de alta sin cita en 4+ meses: programar sonrisas magicas
        limite = datetime(hoy.year, hoy.month, hoy.day) - timedelta(days=120)
        pacientes_alta = Paciente.query.filter(
            Paciente.estatus_crm == EstatusCRM.alta,
            Paciente.eliminado == False,
            Paciente.es_problematico == False,
            db.or_(
                Paciente.ultima_cita < limite,
                Paciente.ultima_cita == None,
            )
        ).all()

        for paciente in pacientes_alta:
            # Verificar que no tenga seguimiento pendiente reciente
            seg_existente = SeguimientoCRM.query.filter_by(
                paciente_id=paciente.id,
                tipo=TipoSeguimiento.whatsapp_1,
                completado=False,
            ).first()
            if not seg_existente:
                seg = SeguimientoCRM(
                    paciente_id=paciente.id,
                    tipo=TipoSeguimiento.whatsapp_1,
                    fecha_programada=_ahora_local(),
                    notas='Auto: Recordatorio Sonrisas Magicas',
                )
                db.session.add(seg)

        db.session.commit()
        logger.info(f'Seguimientos CRM actualizados: {len(pacientes_alta)} pacientes')


def _job_cumpleanos(app):
    """Envia mensajes de cumpleanos a pacientes que cumplen este mes."""
    with app.app_context():
        from models import Paciente, PlantillaMensaje
        from services.whatsapp_service import enviar_mensaje
        from extensions import db

        hoy = _ahora_local().date()

        # Solo el primero de cada mes
        if hoy.day != 1:
            return

        mes_actual = hoy.month

        pacientes = Paciente.query.filter(
            Paciente.fecha_nacimiento != None,
            Paciente.eliminado == False,
            Paciente.es_problematico == False,
        ).all()
        # Filtrar por mes de nacimiento
        pacientes_cumple = [p for p in pacientes
                            if p.fecha_nacimiento and p.fecha_nacimiento.month == mes_actual]

        plantilla = PlantillaMensaje.query.filter_by(tipo='cumpleanos', activo=True).first()

        for paciente in pacientes_cumple:
            numero = paciente.numero_contacto_wa
            if not numero:
                continue
            tutor = paciente.nombre_tutor or 'Estimado padre/madre'
            if plantilla:
                mensaje = plantilla.contenido.format(
                    nombre_tutor=tutor,
                    nombre_paciente=paciente.nombre_completo,
                )
            else:
                mensaje = (f'Hola {tutor}! En el mes de cumpleanos de {paciente.nombre_completo} '
                           f'tiene un regalo especial. Solo tiene que venir a su cita este mes. '
                           f'Le esperamos con gusto!')
            try:
                enviar_mensaje(numero, mensaje)
                logger.info(f'Mensaje cumpleanos enviado a {paciente.nombre_completo}')
            except Exception as e:
                logger.error(f'Error cumpleanos {paciente.nombre_completo}: {e}')


def _job_recordatorio_proxima_visita(app):
    """Envia recordatorios de proxima visita a pacientes programados para este mes."""
    with app.app_context():
        from models import Paciente
        from extensions import db

        hoy = _ahora_local().date()

        # Solo el primero de cada mes
        if hoy.day != 1:
            return

        pacientes = Paciente.query.filter(
            Paciente.proximo_recordatorio_fecha != None,
            Paciente.eliminado == False,
            Paciente.es_problematico == False,
            db.extract('year', Paciente.proximo_recordatorio_fecha) == hoy.year,
            db.extract('month', Paciente.proximo_recordatorio_fecha) == hoy.month,
        ).all()

        for paciente in pacientes:
            try:
                from services.whatsapp_service import enviar_recordatorio_proxima_visita
                enviado = enviar_recordatorio_proxima_visita(paciente)
                if enviado:
                    paciente.proximo_recordatorio_fecha = None
                    logger.info(f'Recordatorio proxima visita enviado a {paciente.nombre_completo}')
            except Exception as e:
                logger.error(f'Error recordatorio proxima visita {paciente.nombre_completo}: {e}')

        db.session.commit()
        logger.info(f'Recordatorios proxima visita procesados: {len(pacientes)} pacientes')
