import os
import logging
from logging.handlers import RotatingFileHandler

from flask import Flask, redirect, url_for, jsonify, render_template, request
from flask_wtf.csrf import CSRFError

from config import get_config
from extensions import login_manager, csrf, limiter, migrate, mail, cache
from models import db, User, Consultorio, TipoCita, PlantillaMensaje
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# ── Blueprints ────────────────────────────────────────────────────────────────
from routes.api_citas import bp_citas
from routes.api_pacientes import bp_pacientes
from routes.api_doctores import bp_doctores
from routes.api_calendario import bp_calendario
from routes.api_crm import bp_crm
from routes.webhook_whatsapp import bp_webhook
from routes.api_configuracion import bp_config
from routes.auth import bp_auth
from routes.admin_health import bp_health


def configure_logging(app):
    """Configura logging con rotación de archivos."""
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(module)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    file_handler = RotatingFileHandler(
        app.config.get('LOG_FILE', 'app.log'),
        maxBytes=app.config.get('LOG_MAX_BYTES', 10 * 1024 * 1024),
        backupCount=app.config.get('LOG_BACKUP_COUNT', 5),
        encoding='utf-8',
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(app.config.get('LOG_LEVEL', logging.INFO))

    app.logger.addHandler(file_handler)
    app.logger.setLevel(app.config.get('LOG_LEVEL', logging.INFO))

    if not app.debug:
        # También log a consola en producción
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        app.logger.addHandler(console_handler)


def create_app(env_name=None):
    app = Flask(__name__)
    config_class = get_config(env_name)
    app.config.from_object(config_class)

    # ── Logging ───────────────────────────────────────────────────────────────
    configure_logging(app)

    # ── Extensiones ───────────────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)
    cache.init_app(app)

    # Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Inicia sesión para acceder.'
    login_manager.login_message_category = 'warning'

    # Flask-Talisman (solo si está habilitado)
    if app.config.get('TALISMAN_ENABLED', False):
        from flask_talisman import Talisman
        csp = app.config.get('TALISMAN_CSP', {})
        Talisman(app, content_security_policy=csp, force_https=True)

    # ── Blueprints ────────────────────────────────────────────────────────────
    app.register_blueprint(bp_auth)
    app.register_blueprint(bp_citas)
    app.register_blueprint(bp_pacientes)
    app.register_blueprint(bp_doctores)
    app.register_blueprint(bp_calendario)
    app.register_blueprint(bp_crm)
    app.register_blueprint(bp_webhook)
    app.register_blueprint(bp_config)
    app.register_blueprint(bp_health)

    # Eximir webhook de CSRF (Twilio no envía token)
    csrf.exempt(bp_webhook)

    # ── Rutas raíz ────────────────────────────────────────────────────────────
    @app.route('/')
    def index():
        return redirect(url_for('calendario.view_calendario'))

    # ── Error handlers ────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/') or request.is_json:
            return jsonify(error='No encontrado'), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        app.logger.error(f'Error 500: {e}', exc_info=True)
        if request.path.startswith('/api/') or request.is_json:
            return jsonify(error='Error interno del servidor'), 500
        return render_template('errors/500.html'), 500

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        return jsonify(error='Token CSRF inválido o expirado.'), 400

    @app.errorhandler(429)
    def rate_limit_error(e):
        return jsonify(error='Demasiadas solicitudes. Intenta más tarde.', retry_after=str(e.retry_after)), 429

    return app


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def seed_initial_data(app):
    """Inserta datos base si la BD está vacía."""
    with app.app_context():
        # Consultorios
        if Consultorio.query.count() == 0:
            for i in range(1, 4):
                db.session.add(Consultorio(id=i, nombre=f'Consultorio {i}'))

        # Tipos de cita
        if TipoCita.query.count() == 0:
            tipos = [
                TipoCita(nombre='Primera Consulta', duracion_mins=60, costo=550),
                TipoCita(nombre='Limpieza + Flúor', duracion_mins=45, costo=0),
                TipoCita(nombre='Ortodoncia', duracion_mins=60, costo=0),
                TipoCita(nombre='Operatoria', duracion_mins=45, costo=0),
                TipoCita(nombre='Revisión', duracion_mins=30, costo=0),
                TipoCita(nombre='Extracción', duracion_mins=45, costo=0),
            ]
            db.session.add_all(tipos)

        # Plantillas de mensajes
        if PlantillaMensaje.query.count() == 0:
            clabe = app.config.get('CLABE_INTERBANCARIA', 'XXXXXXXXXXXXXXXXXX')
            maps_url = app.config.get('GOOGLE_MAPS_REVIEW_URL', 'https://g.page/r/review')
            plantillas = [
                PlantillaMensaje(
                    tipo='bienvenida',
                    contenido=(
                        'Hola buenos días / buenas tardes 😀\n'
                        'Claro, la consulta tiene un costo de $550.00, le incluye su diagnóstico, '
                        'plan de tratamiento, presupuesto y radiografías intraorales que requiera '
                        'su pequeño o pequeña 😀'
                    )
                ),
                PlantillaMensaje(
                    tipo='anticipo',
                    contenido=(
                        'Con gusto 😀 Para las citas de pacientes que vienen por 1ª vez a nuestro '
                        'consultorio dental, solicitamos un pago anticipado del 50% del total de la '
                        'consulta. Esto nos ayuda a garantizar su cita y a ofrecerle el mejor '
                        'servicio posible.\n\n'
                        'En caso de no poder acudir le pedimos reagendar con 24 hrs de anticipación. '
                        'Si no acude no será reembolsable.\n\n'
                        f'Le compartimos el dato para su transferencia:\nCLABE: {clabe}'
                    )
                ),
                PlantillaMensaje(
                    tipo='confirmacion',
                    contenido=(
                        'Perfecto, le compartimos toda la información.\n\n'
                        'Nos vemos el día {fecha} a las {hora} con {doctor} en el {consultorio}. '
                        '¡Hasta entonces! 🦷✨'
                    )
                ),
                PlantillaMensaje(
                    tipo='recordatorio_24h',
                    contenido=(
                        'Hola buenas tardes 😀\n'
                        '¿Cómo está? Le escribo para confirmar la cita de {paciente} '
                        'mañana a las {hora}.\n'
                        '¡Gracias! 😁'
                    )
                ),
                PlantillaMensaje(
                    tipo='sonrisas_magicas',
                    contenido=(
                        'Hola buenos días/tardes 😀 ¿Cómo está? Le escribo para agendar la cita de '
                        '{paciente}, ya nos toca su cita de revisión, control y mantenimiento para '
                        'realizar su limpieza y aplicación de flúor.\n\n'
                        '¿Les acomoda vernos entre semana o sábado?'
                    )
                ),
                PlantillaMensaje(
                    tipo='cumpleanos',
                    contenido=(
                        '¡Feliz cumpleaños {paciente}! 🎉🦷\n'
                        'Como regalo especial en su mes de cumpleaños, si acude a su cita este mes '
                        'recibe un PIN cumpleañero con beneficios exclusivos.\n'
                        '¿Le agendamos?'
                    )
                ),
                PlantillaMensaje(
                    tipo='resena',
                    contenido=(
                        'Hola {paciente} 😊 Esperamos que su visita haya sido excelente.\n'
                        'Su opinión es muy importante para nosotros. ¿Nos regala un minuto para '
                        'dejarnos una reseña en Google?\n\n'
                        f'👉 {maps_url}\n\n'
                        '¡Muchas gracias y hasta la próxima! 🦷✨'
                    )
                ),
            ]
            db.session.add_all(plantillas)

        db.session.commit()


def init_scheduler(app):
    from services.scheduler_jobs import (
        job_recordatorio_24h,
        job_sonrisas_magicas,
        job_crm_seguimiento,
        job_check_cumpleanos,
        job_resena_google,
    )

    scheduler = BackgroundScheduler(timezone='America/Mexico_City')

    scheduler.add_job(
        func=lambda: job_recordatorio_24h(app),
        trigger='interval',
        hours=1,
        id='recordatorio_24h',
        replace_existing=True,
    )
    scheduler.add_job(
        func=lambda: job_sonrisas_magicas(app),
        trigger='cron',
        hour=9,
        minute=0,
        id='sonrisas_magicas',
        replace_existing=True,
    )
    scheduler.add_job(
        func=lambda: job_crm_seguimiento(app),
        trigger='cron',
        hour=10,
        minute=0,
        id='crm_seguimiento',
        replace_existing=True,
    )
    scheduler.add_job(
        func=lambda: job_check_cumpleanos(app),
        trigger='cron',
        hour=9,
        minute=5,
        id='check_cumpleanos',
        replace_existing=True,
    )
    scheduler.add_job(
        func=lambda: job_resena_google(app),
        trigger='cron',
        hour=18,
        minute=0,
        id='resena_google',
        replace_existing=True,
    )

    scheduler.start()
    atexit.register(lambda: scheduler.shutdown(wait=False))
    return scheduler


if __name__ == '__main__':
    app = create_app()

    with app.app_context():
        db.create_all()
        seed_initial_data(app)

    init_scheduler(app)

    print("✅  La Casa del Sr. Pérez — Sistema iniciado en http://localhost:5000")
    app.run(debug=True, use_reloader=False, port=5000)
