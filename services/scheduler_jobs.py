"""Jobs programados con APScheduler."""
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def job_recordatorio_24h(app):
    """Envía recordatorio WA a pacientes con cita mañana."""
    with app.app_context():
        from models import db, Cita, Recordatorio
        from services.whatsapp_service import enviar_mensaje
        from services.crm_service import obtener_plantilla_mensaje

        ahora = datetime.now()
        manana_inicio = (ahora + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        manana_fin = manana_inicio.replace(hour=23, minute=59, second=59)

        citas = Cita.query.filter(
            Cita.fecha_inicio >= manana_inicio,
            Cita.fecha_inicio <= manana_fin,
            Cita.estado == 'pendiente',
        ).all()

        for cita in citas:
            # Verificar si ya se envió recordatorio 24h
            ya_enviado = Recordatorio.query.filter_by(
                cita_id=cita.id, tipo='24h', enviado=True
            ).first()
            if ya_enviado:
                continue

            paciente = cita.paciente
            if not paciente or not paciente.telefono:
                continue

            try:
                mensaje = obtener_plantilla_mensaje('recordatorio_24h', {
                    'paciente': paciente.nombre,
                    'hora': cita.fecha_inicio.strftime('%H:%M'),
                    'doctor': cita.dentista.nombre if cita.dentista else '',
                    'consultorio': cita.consultorio.nombre if cita.consultorio else '',
                })
                enviar_mensaje(paciente.telefono, mensaje)

                rec = Recordatorio(
                    cita_id=cita.id,
                    tipo='24h',
                    programado_para=manana_inicio,
                    enviado=True,
                    fecha_envio=datetime.utcnow(),
                )
                db.session.add(rec)
                db.session.commit()
                logger.info(f'[Scheduler] Recordatorio 24h enviado a {paciente.nombre}')
            except Exception as e:
                logger.error(f'[Scheduler] Error recordatorio 24h: {e}')


def job_sonrisas_magicas(app):
    """Envía WA a pacientes sin cita en 4-6 meses."""
    with app.app_context():
        from models import db, Paciente, SeguimientoCRM
        from services.whatsapp_service import enviar_mensaje
        from services.crm_service import obtener_plantilla_mensaje

        ahora = datetime.now()
        hace_4_meses = ahora - timedelta(days=120)
        hace_6_meses = ahora - timedelta(days=180)

        pacientes = Paciente.query.filter(
            Paciente.estado_crm == 'activo',
            Paciente.fecha_ultima_cita != None,
            Paciente.fecha_ultima_cita <= hace_4_meses,
            Paciente.fecha_ultima_cita >= hace_6_meses,
        ).all()

        for p in pacientes:
            # Verificar si ya se envió seguimiento_1 recientemente
            ya_enviado = SeguimientoCRM.query.filter_by(
                paciente_id=p.id, tipo='whatsapp_1'
            ).order_by(SeguimientoCRM.fecha_enviado.desc()).first()

            if ya_enviado and ya_enviado.fecha_enviado and \
               (ahora - ya_enviado.fecha_enviado).days < 15:
                continue

            try:
                mensaje = obtener_plantilla_mensaje('sonrisas_magicas', {'paciente': p.nombre})
                enviar_mensaje(p.telefono, mensaje)

                p.estado_crm = 'seguimiento_1'
                seg = SeguimientoCRM(
                    paciente_id=p.id,
                    tipo='whatsapp_1',
                    fecha_programada=ahora,
                    fecha_enviado=ahora,
                )
                db.session.add(seg)
                db.session.commit()
                logger.info(f'[Scheduler] Sonrisas Mágicas → {p.nombre}')
            except Exception as e:
                logger.error(f'[Scheduler] Error Sonrisas Mágicas: {e}')


def job_crm_seguimiento(app):
    """Escala estados CRM según tiempo sin respuesta."""
    with app.app_context():
        from models import db, Paciente, SeguimientoCRM
        from services.whatsapp_service import enviar_mensaje
        from services.crm_service import obtener_plantilla_mensaje, TRANSICIONES_CRM

        ahora = datetime.now()

        for estado, transicion in TRANSICIONES_CRM.items():
            if transicion is None:
                continue
            nuevo_estado, dias_limite = transicion

            pacientes = Paciente.query.filter_by(estado_crm=estado).all()
            for p in pacientes:
                ultimo_seg = SeguimientoCRM.query.filter_by(paciente_id=p.id).order_by(
                    SeguimientoCRM.fecha_enviado.desc()
                ).first()

                if not ultimo_seg or not ultimo_seg.fecha_enviado:
                    continue

                dias_transcurridos = (ahora - ultimo_seg.fecha_enviado).days
                if dias_transcurridos < dias_limite:
                    continue

                try:
                    if nuevo_estado == 'seguimiento_2':
                        tipo_seg = 'whatsapp_2'
                        mensaje = obtener_plantilla_mensaje('sonrisas_magicas', {'paciente': p.nombre})
                        enviar_mensaje(p.telefono, mensaje)
                        seg = SeguimientoCRM(
                            paciente_id=p.id, tipo=tipo_seg,
                            fecha_programada=ahora, fecha_enviado=ahora
                        )
                        db.session.add(seg)
                    elif nuevo_estado == 'llamada_pendiente':
                        tipo_seg = 'llamada'
                        # Solo alerta visual en CRM, no envía WA
                        seg = SeguimientoCRM(
                            paciente_id=p.id, tipo=tipo_seg,
                            fecha_programada=ahora
                        )
                        db.session.add(seg)

                    p.estado_crm = nuevo_estado
                    db.session.commit()
                    logger.info(f'[CRM] {p.nombre}: {estado} → {nuevo_estado}')
                except Exception as e:
                    logger.error(f'[CRM] Error escalando {p.nombre}: {e}')

        # Mover a "perdido" si llevan más de 45 días en llamada_pendiente
        ahora_menos_45 = ahora - timedelta(days=45)
        perdidos = Paciente.query.filter_by(estado_crm='llamada_pendiente').all()
        for p in perdidos:
            ultimo = SeguimientoCRM.query.filter_by(paciente_id=p.id).order_by(
                SeguimientoCRM.fecha_enviado.desc()
            ).first()
            if ultimo and ultimo.fecha_enviado and ultimo.fecha_enviado <= ahora_menos_45:
                p.estado_crm = 'perdido'
                logger.info(f'[CRM] {p.nombre}: llamada_pendiente → perdido')
        db.session.commit()


def job_check_cumpleanos(app):
    """Envía PIN cumpleañero a pacientes con cita en su mes de cumpleaños."""
    with app.app_context():
        from models import db, Paciente, Cita
        from services.whatsapp_service import enviar_mensaje
        from services.crm_service import obtener_plantilla_mensaje

        ahora = datetime.now()
        mes_actual = ahora.month

        pacientes = Paciente.query.filter(
            Paciente.fecha_nacimiento != None,
            Paciente.pin_cumpleanero_usado == False,
        ).all()

        for p in pacientes:
            if not p.fecha_nacimiento or p.fecha_nacimiento.month != mes_actual:
                continue

            # Verificar que tenga cita este mes
            inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0)
            fin_mes = (inicio_mes + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)

            cita_mes = Cita.query.filter(
                Cita.paciente_id == p.id,
                Cita.fecha_inicio >= inicio_mes,
                Cita.fecha_inicio <= fin_mes,
                Cita.estado.in_(['pendiente', 'confirmada']),
            ).first()

            if not cita_mes:
                continue

            try:
                mensaje = obtener_plantilla_mensaje('cumpleanos', {'paciente': p.nombre})
                enviar_mensaje(p.telefono, mensaje)
                p.pin_cumpleanero_usado = True
                db.session.commit()
                logger.info(f'[Scheduler] PIN cumpleañero → {p.nombre}')
            except Exception as e:
                logger.error(f'[Scheduler] Error cumpleaños: {e}')


def job_resena_google(app):
    """Envía solicitud de reseña 3 horas después de una cita completada."""
    with app.app_context():
        from models import db, Cita, Recordatorio
        from services.whatsapp_service import enviar_mensaje
        from services.crm_service import obtener_plantilla_mensaje

        ahora = datetime.now()
        hace_3h = ahora - timedelta(hours=3)
        hace_4h = ahora - timedelta(hours=4)

        citas = Cita.query.filter(
            Cita.estado == 'confirmada',
            Cita.fecha_fin >= hace_4h,
            Cita.fecha_fin <= hace_3h,
        ).all()

        for cita in citas:
            ya_enviado = Recordatorio.query.filter_by(
                cita_id=cita.id, tipo='resena', enviado=True
            ).first()
            if ya_enviado:
                continue

            paciente = cita.paciente
            if not paciente:
                continue

            try:
                mensaje = obtener_plantilla_mensaje('resena', {'paciente': paciente.nombre})
                enviar_mensaje(paciente.telefono, mensaje)

                rec = Recordatorio(
                    cita_id=cita.id,
                    tipo='resena',
                    programado_para=cita.fecha_fin + timedelta(hours=3),
                    enviado=True,
                    fecha_envio=datetime.utcnow(),
                )
                db.session.add(rec)
                db.session.commit()
                logger.info(f'[Scheduler] Reseña Google → {paciente.nombre}')
            except Exception as e:
                logger.error(f'[Scheduler] Error reseña: {e}')
