"""
Tareas programadas con APScheduler.
- Recordatorios 24h antes de la cita
- Postconsulta 2 dias despues
- Seguimientos CRM automaticos
- Resumen diario a doctores
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


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

    logger.info('Jobs del scheduler registrados.')


def _job_recordatorios_24h(app):
    """Envia recordatorios 24h antes de las citas."""
    with app.app_context():
        from models import Cita, EstatusCita, Recordatorio, TipoRecordatorio, EstatusRecordatorio
        from extensions import db

        ahora = datetime.utcnow()
        ventana_inicio = ahora + timedelta(hours=23)
        ventana_fin = ahora + timedelta(hours=25)

        citas = Cita.query.filter(
            Cita.fecha_inicio >= ventana_inicio,
            Cita.fecha_inicio <= ventana_fin,
            Cita.status.in_([EstatusCita.pendiente, EstatusCita.confirmada]),
            Cita.reminder_24h_sent == False,
        ).all()

        for cita in citas:
            try:
                from services.whatsapp_service import enviar_recordatorio_cita
                enviado = enviar_recordatorio_cita(cita)
                status = EstatusRecordatorio.enviado if enviado else EstatusRecordatorio.fallido

                recordatorio = Recordatorio(
                    cita_id=cita.id,
                    tipo=TipoRecordatorio.confirmacion_24h,
                    fecha_envio=datetime.utcnow(),
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

        ahora = datetime.utcnow()
        # Citas de hace 2 dias (±2 horas)
        hace_2_dias_inicio = ahora - timedelta(days=2, hours=2)
        hace_2_dias_fin = ahora - timedelta(days=1, hours=22)

        citas = Cita.query.filter(
            Cita.fecha_inicio >= hace_2_dias_inicio,
            Cita.fecha_inicio <= hace_2_dias_fin,
            Cita.status == EstatusCita.confirmada,
            Cita.postconsulta_sent == False,
        ).all()

        for cita in citas:
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
        from datetime import date

        manana = date.today() + timedelta(days=1)
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
        from datetime import date

        hoy = date.today()

        # Pacientes de alta sin cita en 4+ meses: programar sonrisas magicas
        limite = datetime(hoy.year, hoy.month, hoy.day) - timedelta(days=120)
        pacientes_alta = Paciente.query.filter(
            Paciente.estatus_crm == EstatusCRM.alta,
            Paciente.eliminado == False,
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
                    fecha_programada=datetime.utcnow(),
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
        from datetime import date

        mes_actual = date.today().month

        pacientes = Paciente.query.filter(
            db.func.strftime('%m', Paciente.fecha_nacimiento) == f'{mes_actual:02d}',
            Paciente.eliminado == False,
        ).all() if False else []  # Solo ejecutar el 1ro del mes

        # Solo el primero de cada mes
        if date.today().day != 1:
            return

        from extensions import db
        pacientes = Paciente.query.filter(
            Paciente.fecha_nacimiento != None,
            Paciente.eliminado == False,
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
