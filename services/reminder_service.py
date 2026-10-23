"""
Tareas programadas con APScheduler.
- Confirmacion a pendientes el dia anterior (turnos 9am y 9pm; el fin de
  semana cubre el lunes: sabado 9/21 y domingo 9am)
- Mensaje del mismo dia 1h antes de la apertura del consultorio
- Postconsulta 2 dias despues
- Seguimientos CRM automaticos
- Resumen diario a doctores
"""
import logging
from datetime import datetime, time, timedelta, timezone
from services.tiempo import TIMEZONE, ahora_local

logger = logging.getLogger(__name__)

TURNO_MANANA = 'manana'
TURNO_NOCHE = 'noche'
_HORAS_TURNO = (time(9, 0), time(21, 0))


def _ahora_local():
    """Retorna datetime actual en la timezone del consultorio."""
    return ahora_local()


def _hora_resumen_doctores(app):
    """Lee la hora configurada del resumen a doctores. Fallback 21:00 (9pm)."""
    try:
        with app.app_context():
            from models import ConfiguracionConsultorio
            config = ConfiguracionConsultorio.query.first()
            if config and config.hora_resumen_doctores:
                return config.hora_resumen_doctores.hour, config.hora_resumen_doctores.minute
    except Exception as e:
        logger.warning(f'No se pudo leer hora_resumen_doctores, usando 21:00: {e}')
    return 21, 0


def setup_scheduler_jobs(scheduler, app):
    """Registra todos los jobs del scheduler."""

    # Turno de la manana (9am CDMX): confirmacion de las citas PENDIENTES del
    # dia siguiente (sabado: domingo y lunes; domingo: lunes). Las confirmadas
    # y las marcadas "no asistira" no reciben nada.
    scheduler.add_job(
        func=_job_recordatorios_24h,
        trigger='cron',
        hour=9,
        minute=0,
        id='recordatorios_24h',
        replace_existing=True,
        kwargs={'app': app, 'turno': TURNO_MANANA},
    )

    # Turno de la noche (9pm CDMX): segundo intento a quien no contesto y
    # primer aviso a lo agendado durante el dia. intentos_confirmacion topa
    # los envios por cita.
    scheduler.add_job(
        func=_job_recordatorios_24h,
        trigger='cron',
        hour=21,
        minute=0,
        id='recordatorios_24h_noche',
        replace_existing=True,
        kwargs={'app': app, 'turno': TURNO_NOCHE},
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

    # Resumen diario a doctores - hora configurable (default 21:00 / 9pm)
    _resumen_hora, _resumen_min = _hora_resumen_doctores(app)
    scheduler.add_job(
        func=_job_resumen_doctores,
        trigger='cron',
        hour=_resumen_hora,
        minute=_resumen_min,
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

    # Campanas programadas - safety net cada 5 min
    scheduler.add_job(
        func=_job_campanas_programadas,
        trigger='interval',
        minutes=5,
        id='campanas_programadas',
        replace_existing=True,
        kwargs={'app': app},
    )

    # Recordatorios manuales - diario a las 9am
    scheduler.add_job(
        func=_job_recordatorios_manuales,
        trigger='cron',
        hour=9,
        minute=5,
        id='recordatorios_manuales',
        replace_existing=True,
        kwargs={'app': app},
    )

    # Pre-citas expiradas - cada 30 min
    scheduler.add_job(
        func=_job_cancelar_pre_citas_expiradas,
        trigger='interval',
        minutes=30,
        id='cancelar_pre_citas_expiradas',
        replace_existing=True,
        kwargs={'app': app},
    )

    # Mensaje del mismo dia - revisa cada 10 min; solo envia a partir de 1h
    # antes de la apertura del consultorio de ese dia (HorarioConsultorio).
    # MensajeEnviado evita duplicados entre corridas.
    scheduler.add_job(
        func=_job_confirmacion_mismo_dia,
        trigger='interval',
        minutes=10,
        id='confirmacion_mismo_dia',
        replace_existing=True,
        kwargs={'app': app},
    )

    # Reenvio de mensajes fallidos - cada 15 min
    scheduler.add_job(
        func=_job_reenviar_fallidos,
        trigger='interval',
        minutes=15,
        id='reenviar_fallidos',
        replace_existing=True,
        kwargs={'app': app},
    )

    logger.info('Jobs del scheduler registrados.')


def _hora_envio_mismo_dia(fecha):
    """
    Hora local (naive) a partir de la cual sale el mensaje del mismo dia:
    1 hora antes de la apertura del consultorio ese dia.
    None si el consultorio no abre ese dia o no tiene horario configurado.
    """
    from models import HorarioConsultorio

    horario = HorarioConsultorio.del_dia(fecha.weekday())
    if horario is None:
        logger.warning(
            f'Sin horario de consultorio configurado para el dia '
            f'{fecha.weekday()} ({fecha}); no se envia mensaje del mismo dia.')
        return None
    if horario.cerrado:
        return None
    apertura = horario.hora_apertura or time(9, 0)
    return datetime.combine(fecha, apertura) - timedelta(hours=1)


def _local_a_utc_naive(dt_local):
    """Convierte hora local naive a UTC naive (formato de Cita.created_at)."""
    return (dt_local.replace(tzinfo=TIMEZONE)
            .astimezone(timezone.utc).replace(tzinfo=None))


def _job_confirmacion_mismo_dia(app):
    """
    Envia el mensaje de HOY segun el estado real de cada cita.
    Las pendientes reciben una solicitud de confirmacion; las confirmadas, un
    recordatorio informativo. MensajeEnviado evita duplicados por cita y tipo.

    Corre cada 10 min, pero solo actua a partir de 1h antes de la apertura del
    consultorio de hoy (HorarioConsultorio). Si hoy no abre, no hace nada.
    Solo toma citas que aun no empiezan y que fueron creadas antes de la hora
    de envio: las agendadas despues ya se acaban de acordar con el paciente.
    """
    with app.app_context():
        from sqlalchemy import or_
        from models import (AvisoRecepcion, Cita, EstatusCita, MensajeEnviado,
                            TipoRecordatorio)

        ahora = _ahora_local()
        hora_envio = _hora_envio_mismo_dia(ahora.date())
        if hora_envio is None or ahora < hora_envio:
            return

        hoy_fin = ahora.replace(hour=23, minute=59, second=59, microsecond=0)
        # created_at se guarda con datetime.utcnow() (UTC naive)
        limite_creacion = _local_a_utc_naive(hora_envio)

        # El recordatorio de 24h es independiente: todas las citas vigentes de
        # hoy deben recibir exactamente el mensaje que corresponda a su estado.
        citas = Cita.query.filter(
            Cita.fecha_inicio > ahora,
            Cita.fecha_inicio <= hoy_fin,
            Cita.status.in_([EstatusCita.pendiente, EstatusCita.confirmada]),
            or_(Cita.created_at.is_(None),
                Cita.created_at < limite_creacion),
        ).all()

        from extensions import db
        from services.avisos_service import (
            MARCA_NO_ASISTIRA, MARCA_SIN_CONFIRMAR, TIPO_NO_CONTESTO,
            _rango_hoy_utc, crear_aviso, marcar_cita)
        from services.whatsapp_service import (
            enviar_confirmacion_mismo_dia,
            enviar_recordatorio_cita_hoy,
            enviar_reagendado_mismo_dia,
        )

        inicio_hoy = datetime.combine(ahora.date(), time.min)
        aviso_desde, aviso_hasta = _rango_hoy_utc(ahora)

        for cita in citas:
            if cita.paciente and cita.paciente.es_problematico:
                continue
            reagenda = False
            if cita.status == EstatusCita.confirmada:
                if _contesto_mensaje_de_hoy(cita.id, inicio_hoy):
                    continue  # acaba de confirmar respondiendo el de hoy
                tipo, enviar = (TipoRecordatorio.recordatorio_cita_hoy,
                                enviar_recordatorio_cita_hoy)
            elif cita.aviso_asistencia == MARCA_NO_ASISTIRA:
                continue
            elif intentos_confirmacion(cita) >= 1:
                tipo, enviar = (TipoRecordatorio.reagendado_mismo_dia,
                                enviar_reagendado_mismo_dia)
                reagenda = True
            else:
                tipo, enviar = (TipoRecordatorio.confirmacion_mismo_dia,
                                enviar_confirmacion_mismo_dia)
            if MensajeEnviado.query.filter(
                    MensajeEnviado.cita_id == cita.id,
                    MensajeEnviado.tipo == tipo,
                    MensajeEnviado.fecha_creacion >= inicio_hoy).first() is None:
                try:
                    if enviar(cita):
                        logger.info(
                            f'Mensaje {tipo.value} enviado para cita {cita.id}')
                except Exception as e:
                    db.session.rollback()
                    logger.error(f'Error en mensaje del dia cita {cita.id}: {e}')
            if reagenda:
                # El hecho "no confirmo" es independiente de que el envio llegue.
                try:
                    if AvisoRecepcion.query.filter(
                            AvisoRecepcion.tipo == TIPO_NO_CONTESTO,
                            AvisoRecepcion.cita_id == cita.id,
                            AvisoRecepcion.created_at >= aviso_desde,
                            AvisoRecepcion.created_at < aviso_hasta,
                    ).first() is None:
                        marcar_cita(cita, MARCA_SIN_CONFIRMAR)
                        crear_aviso(
                            TIPO_NO_CONTESTO, cita=cita,
                            detalle='No contestó la confirmación; se le envió '
                                    'mensaje para reagendar',
                            origen='sistema')
                        db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    logger.error(f'Error creando aviso cita {cita.id}: {e}')


def _contesto_mensaje_de_hoy(cita_id, inicio_hoy):
    """
    True si hoy ya salio (no fallido) la confirmacion o el reagendado del
    mismo dia: si la cita esta confirmada, el paciente acaba de contestarlo y
    el recordatorio informativo sobra.
    """
    from models import EstatusRecordatorio, MensajeEnviado, TipoRecordatorio

    return MensajeEnviado.query.filter(
        MensajeEnviado.cita_id == cita_id,
        MensajeEnviado.tipo.in_([TipoRecordatorio.confirmacion_mismo_dia,
                                 TipoRecordatorio.reagendado_mismo_dia]),
        MensajeEnviado.fecha_creacion >= inicio_hoy,
        MensajeEnviado.estatus.notin_([
            EstatusRecordatorio.fallido,
            EstatusRecordatorio.fallido_definitivo,
            EstatusRecordatorio.caducado,
        ]),
    ).first() is not None


def _job_cancelar_pre_citas_expiradas(app):
    """Cancela automaticamente las pre-citas cuya reserva de 12h haya expirado sin anticipo."""
    with app.app_context():
        from models import Cita, EstatusCita
        from extensions import db

        ahora = datetime.utcnow()
        expiradas = Cita.query.filter(
            Cita.status == EstatusCita.pre_cita,
            Cita.pre_cita_expira.isnot(None),
            Cita.pre_cita_expira <= ahora,
        ).all()

        for cita in expiradas:
            cita.status = EstatusCita.cancelada
            cita.notas = (cita.notas or '') + ' | Cancelada automaticamente: pre-cita expirada sin anticipo.'
            logger.info(
                f'Pre-cita #{cita.id} expirada (paciente_id={cita.paciente_id}). '
                f'Expiraba: {cita.pre_cita_expira}. Cancelada.'
            )

        if expiradas:
            db.session.commit()
            logger.info(f'{len(expiradas)} pre-cita(s) expirada(s) cancelada(s).')


def objetivos_confirmacion(hoy, turno):
    """
    Pares (fecha_de_cita, max_intentos) que cubre un turno de confirmacion.
    Sabado: domingo y lunes. Domingo: solo lunes (3er intento, solo en la
    manana). Otro dia: manana. max_intentos es el tope acumulado de envios.
    """
    un_dia = timedelta(days=1)
    noche = turno == TURNO_NOCHE
    if hoy.weekday() == 5:
        tope = 2 if noche else 1
        return [(hoy + un_dia, tope), (hoy + 2 * un_dia, tope)]
    if hoy.weekday() == 6:
        return [] if noche else [(hoy + un_dia, 3)]
    return [(hoy + un_dia, 2 if noche else 1)]


def _confirmaciones_contadas(cita_id, desde=None):
    """
    Query de confirmacion_24h de una cita que no fallaron ni caducaron. Con
    desde, solo las creadas (hora local naive) a partir de ese instante.
    """
    from models import EstatusRecordatorio, MensajeEnviado, TipoRecordatorio

    query = MensajeEnviado.query.filter(
        MensajeEnviado.cita_id == cita_id,
        MensajeEnviado.tipo == TipoRecordatorio.confirmacion_24h,
        MensajeEnviado.estatus.notin_([
            EstatusRecordatorio.fallido,
            EstatusRecordatorio.fallido_definitivo,
            EstatusRecordatorio.caducado,
        ]),
    )
    if desde is not None:
        query = query.filter(MensajeEnviado.fecha_creacion >= desde)
    return query


def _inicio_conteo(cita, desde):
    """El mas tardio entre desde y el ultimo cambio de fecha de la cita."""
    reset = getattr(cita, 'confirmacion_reset_at', None)
    if reset is not None and reset > desde:
        return reset
    return desde


def intentos_confirmacion(cita):
    """
    Envios de confirmacion_24h de la cita para su fecha actual: no fallaron ni
    caducaron y se crearon desde 2 dias antes de fecha_inicio y despues del
    ultimo cambio de fecha (confirmacion_reset_at): una cita reagendada no
    arrastra los intentos de su fecha anterior.
    """
    desde = datetime.combine(
        cita.fecha_inicio.date() - timedelta(days=2), time(0, 0))
    return _confirmaciones_contadas(
        cita.id, _inicio_conteo(cita, desde)).count()


def _enviado_en_turno(cita, inicio_turno):
    """
    True si ya hay una confirmacion_24h de esta cita desde inicio_turno (o
    desde su ultimo cambio de fecha, si es posterior): una contada, o una
    fallida con reintento en curso (ya se mando, solo no llego).
    """
    from models import EstatusRecordatorio, MensajeEnviado, TipoRecordatorio

    reciente = MensajeEnviado.fecha_creacion >= _inicio_conteo(
        cita, inicio_turno)
    if _confirmaciones_contadas(cita.id).filter(reciente).first() is not None:
        return True
    return MensajeEnviado.query.filter(
        MensajeEnviado.cita_id == cita.id,
        MensajeEnviado.tipo == TipoRecordatorio.confirmacion_24h,
        MensajeEnviado.estatus == EstatusRecordatorio.fallido,
        MensajeEnviado.proximo_intento.isnot(None),
        reciente,
    ).first() is not None


def _paso_turno_confirmacion(creado_local, ahora):
    """True si entre creado_local y ahora pasó un turno (9:00 o 21:00)."""
    dia = creado_local.date()
    while dia <= ahora.date():
        for hora in _HORAS_TURNO:
            turno = datetime.combine(dia, hora)
            if creado_local < turno <= ahora:
                return True
        dia += timedelta(days=1)
    return False


def _job_recordatorios_24h(app, turno):
    """
    Envia la confirmacion a las citas PENDIENTES de las fechas que cubre el
    turno (objetivos_confirmacion) que no esten marcadas "no asistira", cuyo
    paciente no sea problematico y que no hayan llegado al tope de intentos.
    Las confirmadas no reciben nada (les llega el recordatorio del mismo dia).
    """
    with app.app_context():
        from models import Cita, EstatusCita
        from extensions import db
        from services.avisos_service import MARCA_NO_ASISTIRA
        from sqlalchemy import or_

        hoy = _ahora_local().date()
        hora_turno = _HORAS_TURNO[1 if turno == TURNO_NOCHE else 0]
        inicio_turno = datetime.combine(hoy, hora_turno)
        for fecha, maximo in objetivos_confirmacion(hoy, turno):
            inicio = datetime(fecha.year, fecha.month, fecha.day, 0, 0, 0)
            fin = datetime(fecha.year, fecha.month, fecha.day, 23, 59, 59)

            citas = Cita.query.filter(
                Cita.fecha_inicio >= inicio,
                Cita.fecha_inicio <= fin,
                Cita.status == EstatusCita.pendiente,
                or_(Cita.aviso_asistencia.is_(None),
                    Cita.aviso_asistencia != MARCA_NO_ASISTIRA),
            ).all()

            for cita in citas:
                if cita.paciente and cita.paciente.es_problematico:
                    logger.info(f'Saltando recordatorio para paciente problematico: cita {cita.id}')
                    continue
                if intentos_confirmacion(cita) >= maximo:
                    continue
                if _enviado_en_turno(cita, inicio_turno):
                    continue  # el mismo turno nunca manda dos veces
                try:
                    from services.whatsapp_service import enviar_recordatorio_cita
                    enviado = enviar_recordatorio_cita(cita)
                    if enviado:
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
        from models import Paciente, PlantillaMensaje, TipoRecordatorio
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
            valores = {'nombre_tutor': tutor,
                       'nombre_paciente': paciente.nombre_completo}
            if plantilla:
                mensaje = plantilla.contenido.format(**valores)
            else:
                mensaje = (f'Hola {tutor}! En el mes de cumpleanos de {paciente.nombre_completo} '
                           f'tiene un regalo especial. Solo tiene que venir a su cita este mes. '
                           f'Le esperamos con gusto!')
            try:
                from services.whatsapp_service import kwargs_plantilla
                enviar_mensaje(numero, mensaje, tipo=TipoRecordatorio.cumpleanos,
                               paciente_id=paciente.id,
                               **kwargs_plantilla(plantilla, valores))
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


def _job_campanas_programadas(app):
    """Safety net: envia campanas programadas cuya fecha ya paso."""
    with app.app_context():
        from models import Campana, EstatusCampana
        from extensions import db

        ahora = _ahora_local()
        campanas = Campana.query.filter(
            Campana.estatus == EstatusCampana.programada,
            Campana.fecha_programada <= ahora,
        ).all()

        for campana in campanas:
            try:
                from services.campana_service import enviar_campana
                enviar_campana(campana.id, app)
                logger.info(f'Campana programada {campana.id} enviada por safety-net')
            except Exception as e:
                logger.error(f'Error enviando campana programada {campana.id}: {e}')


def _job_recordatorios_manuales(app):
    """Envia recordatorios manuales de seguimiento programados para hoy o dias anteriores."""
    with app.app_context():
        from models import RecordatorioManual, ConversacionWhatsapp, TipoRecordatorio
        from extensions import db

        hoy = _ahora_local().date()
        pendientes = RecordatorioManual.query.filter(
            RecordatorioManual.status == 'pendiente',
            RecordatorioManual.fecha_programada <= hoy,
        ).all()

        for rec in pendientes:
            if rec.paciente and rec.paciente.es_problematico:
                logger.info(f'Saltando recordatorio manual {rec.id}: paciente problematico')
                continue
            try:
                from services.whatsapp_service import enviar_mensaje
                numero = rec.paciente.numero_contacto_wa if rec.paciente else None
                if not numero:
                    rec.status = 'fallido'
                    rec.error = 'Sin numero de WhatsApp'
                    db.session.commit()
                    continue

                enviar_mensaje(numero, rec.mensaje, tipo=TipoRecordatorio.manual,
                               paciente_id=rec.paciente_id)
                rec.status = 'enviado'
                rec.fecha_envio = _ahora_local()

                conv = ConversacionWhatsapp(
                    numero_telefono=numero,
                    paciente_id=rec.paciente_id,
                    mensaje=rec.mensaje,
                    es_bot=True,
                )
                db.session.add(conv)
                logger.info(f'Recordatorio manual {rec.id} enviado a {numero}')
            except Exception as e:
                logger.error(f'Error enviando recordatorio manual {rec.id}: {e}')
                rec.status = 'fallido'
                rec.error = str(e)
            db.session.commit()


def _sincronizar_campana(registro, sid=None, fecha_envio=None):
    """
    Si el mensaje reenviado pertenecia a una campana, corrige el estatus del
    destinatario y los contadores, para que la campana no quede marcando un
    fallo que ya se resolvio.
    """
    if not registro.campana_destinatario_id:
        return

    from extensions import db
    from models import CampanaDestinatario, EstatusDestinatario

    dest = db.session.get(CampanaDestinatario, registro.campana_destinatario_id)
    if not dest or dest.estatus == EstatusDestinatario.enviado:
        return

    dest.estatus = EstatusDestinatario.enviado
    dest.fecha_envio = fecha_envio or registro.fecha_envio
    dest.message_sid = sid or registro.message_sid
    dest.error_mensaje = None

    campana = dest.campana
    if campana:
        campana.enviados = (campana.enviados or 0) + 1
        campana.fallidos = max((campana.fallidos or 0) - 1, 0)


def _reclamar_fila_reenvio(registro_id, ahora):
    """Reclama atomícamente una fila por un lapso acotado para evitar duplicados."""
    from extensions import db
    from models import MensajeEnviado, EstatusRecordatorio
    from services.whatsapp_service import BACKOFF_MINUTOS

    reconciliar_despues = ahora + timedelta(minutes=BACKOFF_MINUTOS[0])
    try:
        reclamadas = MensajeEnviado.query.filter(
            MensajeEnviado.id == registro_id,
            MensajeEnviado.estatus == EstatusRecordatorio.fallido,
            MensajeEnviado.message_sid.is_(None),
            MensajeEnviado.proximo_intento.isnot(None),
            MensajeEnviado.proximo_intento <= ahora,
        ).update(
            {
                MensajeEnviado.estatus: EstatusRecordatorio.pendiente,
                # Marca operativa: pendiente no vuelve a seleccionarse sola.
                MensajeEnviado.proximo_intento: reconciliar_despues,
            },
            synchronize_session=False,
        )
        db.session.commit()
        return reclamadas == 1
    except Exception as e:
        db.session.rollback()
        logger.error(f'No se pudo reclamar mensaje {registro_id}: {e}')
        return False


def _cita_ya_no_requiere(tipo, cita, registro=None, ahora=None):
    """
    True si el estado actual de la cita vuelve obsoleto el mensaje:
    - la confirmacion del dia anterior ya no sirve el dia de la cita (ese dia
      le toca el mensaje del mismo dia);
    - un reintento creado antes de mover la cita lleva la fecha vieja;
    - el status/marca de la cita ya no corresponde al tipo de mensaje.
    """
    from models import EstatusCita, TipoRecordatorio
    from services.avisos_service import MARCA_NO_ASISTIRA

    if (tipo == TipoRecordatorio.confirmacion_24h and ahora is not None
            and ahora.date() >= cita.fecha_inicio.date()):
        return True
    reset = getattr(cita, 'confirmacion_reset_at', None)
    if (tipo in (TipoRecordatorio.confirmacion_24h,
                 TipoRecordatorio.confirmacion_mismo_dia,
                 TipoRecordatorio.reagendado_mismo_dia,
                 TipoRecordatorio.recordatorio_cita_hoy)
            and reset is not None and registro is not None
            and registro.fecha_creacion is not None
            and registro.fecha_creacion < reset):
        return True
    if tipo in (TipoRecordatorio.confirmacion_24h,
                TipoRecordatorio.confirmacion_mismo_dia,
                TipoRecordatorio.reagendado_mismo_dia):
        return (cita.status != EstatusCita.pendiente
                or cita.aviso_asistencia == MARCA_NO_ASISTIRA)
    if tipo == TipoRecordatorio.recordatorio_cita_hoy:
        return cita.status != EstatusCita.confirmada
    return False


def _job_reenviar_fallidos(app):
    """
    Reintenta los mensajes fallidos cuyo proximo_intento ya vencio.

    Salvaguardas: no reintenta mensajes de citas que ya pasaron, ni a pacientes
    problematicos, ni filas que ya tienen SID (Twilio ya las acepto).
    """
    with app.app_context():
        from extensions import db
        from models import (Cita, MensajeEnviado, EstatusRecordatorio,
                            TipoRecordatorio)
        from services.whatsapp_service import (
            enviar_mensaje, _persistir_sid_aceptado, _programar_reintento)

        ahora = _ahora_local()
        pendientes = MensajeEnviado.query.filter(
            MensajeEnviado.estatus == EstatusRecordatorio.fallido,
            MensajeEnviado.message_sid.is_(None),
            MensajeEnviado.proximo_intento.isnot(None),
            MensajeEnviado.proximo_intento <= ahora,
        ).all()

        for candidato in pendientes:
            if not _reclamar_fila_reenvio(candidato.id, ahora):
                continue

            registro = db.session.get(MensajeEnviado, candidato.id)
            if registro is None:
                continue

            tipos_previos_a_cita = {
                TipoRecordatorio.confirmacion_24h,
                TipoRecordatorio.confirmacion_mismo_dia,
                TipoRecordatorio.recordatorio_cita_hoy,
                TipoRecordatorio.confirmacion_anticipo,
                TipoRecordatorio.reagendado_mismo_dia,
            }
            if (registro.tipo == TipoRecordatorio.confirmacion_24h
                    and registro.fecha_creacion
                    and _paso_turno_confirmacion(registro.fecha_creacion, ahora)):
                # Ya hubo otro turno: el siguiente decide si vuelve a mandar.
                registro.estatus = EstatusRecordatorio.caducado
                registro.proximo_intento = None
                db.session.commit()
                logger.info(f'Mensaje {registro.id} caducado: paso un turno de confirmacion.')
                continue
            if registro.cita_id and registro.tipo in tipos_previos_a_cita:
                cita = db.session.get(Cita, registro.cita_id)
                if cita and cita.fecha_inicio and cita.fecha_inicio < ahora:
                    registro.estatus = EstatusRecordatorio.caducado
                    registro.proximo_intento = None
                    db.session.commit()
                    logger.info(f'Mensaje {registro.id} caducado: la cita ya paso.')
                    continue
                if cita and _cita_ya_no_requiere(registro.tipo, cita,
                                                registro=registro,
                                                ahora=ahora):
                    registro.estatus = EstatusRecordatorio.caducado
                    registro.proximo_intento = None
                    db.session.commit()
                    logger.info(f'Mensaje {registro.id} caducado: cambio el estado de la cita.')
                    continue
            if registro.tipo in tipos_previos_a_cita and (
                    ahora.hour >= 22 or ahora.hour < 7):
                # Nada al paciente de madrugada: la fila se reclamo (pendiente),
                # se devuelve a fallido para el proximo 07:00 local.
                dia = ahora.date() + timedelta(days=1 if ahora.hour >= 22 else 0)
                registro.estatus = EstatusRecordatorio.fallido
                registro.proximo_intento = datetime.combine(dia, time(7, 0))
                db.session.commit()
                continue

            if registro.paciente and registro.paciente.es_problematico:
                registro.estatus = EstatusRecordatorio.fallido_definitivo
                registro.error = 'No reintentado: paciente marcado como problematico'
                registro.proximo_intento = None
                db.session.commit()
                continue

            try:
                # Se repite el envio tal cual: si salio por plantilla aprobada,
                # reintentarlo como texto libre volveria a chocar con el 63016.
                sid = enviar_mensaje(
                    registro.numero_destino, registro.mensaje, registrar=False,
                    content_sid=registro.content_sid,
                    content_variables=registro.content_variables)
            except Exception as e:
                logger.error(f'Reintento fallido del mensaje {registro.id}: {e}')
                _programar_reintento(registro, e)
                continue

            # Una vez que Twilio entrega un SID, persistir esa aceptación antes
            # de cualquier trabajo local que pueda fallar.
            fecha_envio = _persistir_sid_aceptado(registro, sid)
            if fecha_envio is None:
                continue

            try:
                _sincronizar_campana(
                    registro, sid=sid, fecha_envio=fecha_envio)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(
                    f'Entrega aceptada para mensaje {registro.id}, pero fallo '
                    f'la sincronizacion local: {e}')
                continue

            logger.info(f'Mensaje {registro.id} reenviado con exito (SID={sid}).')
