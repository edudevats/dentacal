import os
import logging
from flask import Flask, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)

    # Config
    from config import config_map
    app.config.from_object(config_map.get(config_name, config_map['default']))

    # Logging
    logging.basicConfig(
        level=app.config.get('LOG_LEVEL', logging.INFO),
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    )

    # Extensions
    _init_extensions(app)

    # Blueprints
    _register_blueprints(app)

    # Error handlers
    _register_error_handlers(app)

    # Scheduler (reminders)
    if app.config.get('SCHEDULER_ENABLED', True):
        _start_scheduler(app)

    return app


def _init_extensions(app):
    from extensions import db, migrate, login_manager, csrf, limiter, cache, mail

    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    limiter.init_app(app)
    cache.init_app(app)
    mail.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Debes iniciar sesion para acceder.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return User.query.get(int(user_id))

    # Crear tablas si no existen (util en PythonAnywhere sin migrations)
    with app.app_context():
        import models  # noqa: F401 — registers all models with SQLAlchemy metadata
        db.create_all()
        _seed_initial_data()


def _register_blueprints(app):
    from routes.auth import auth_bp
    from routes.main import main_bp
    from routes.api_citas import citas_bp
    from routes.api_pacientes import pacientes_bp
    from routes.api_dentistas import dentistas_bp
    from routes.api_calendario import calendario_bp
    from routes.api_crm import crm_bp
    from routes.api_configuracion import configuracion_bp
    from routes.api_justificantes import justificantes_bp
    from routes.webhook_whatsapp import webhook_bp
    from routes.api_bot import bot_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(citas_bp)
    app.register_blueprint(pacientes_bp)
    app.register_blueprint(dentistas_bp)
    app.register_blueprint(calendario_bp)
    app.register_blueprint(crm_bp)
    app.register_blueprint(configuracion_bp)
    app.register_blueprint(justificantes_bp)
    app.register_blueprint(webhook_bp)
    app.register_blueprint(bot_bp)


def _register_error_handlers(app):
    @app.errorhandler(404)
    def not_found(e):
        if _is_api_request():
            return jsonify(error='No encontrado'), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(e):
        from extensions import db
        db.session.rollback()
        if _is_api_request():
            return jsonify(error='Error interno del servidor'), 500
        return render_template('errors/500.html'), 500

    @app.errorhandler(403)
    def forbidden(e):
        if _is_api_request():
            return jsonify(error='Acceso denegado'), 403
        return render_template('errors/404.html'), 403


def _is_api_request():
    from flask import request
    return request.path.startswith('/api/') or request.path.startswith('/webhook/')


def _start_scheduler(app):
    from extensions import scheduler
    from services.reminder_service import setup_scheduler_jobs

    if not scheduler.running:
        setup_scheduler_jobs(scheduler, app)
        scheduler.start()
        app.logger.info('APScheduler iniciado.')


def _seed_initial_data():
    """Inserta datos iniciales si la BD esta vacia."""
    from models import (Consultorio, TipoCita, PlantillaMensaje,
                        ConfiguracionConsultorio, Dentista, HorarioDentista)
    from extensions import db

    # Consultorios
    if not Consultorio.query.first():
        for i in range(1, 4):
            db.session.add(Consultorio(nombre=f'Consultorio {i}'))

    # Tipos de cita
    if not TipoCita.query.first():
        tipos = [
            TipoCita(nombre='Primera Consulta', duracion_minutos=60, precio=550,
                     requiere_anticipo=True, color='#E84375'),
            TipoCita(nombre='Limpieza y Fluor', duracion_minutos=45, precio=600,
                     requiere_anticipo=False, color='#00B5AD'),
            TipoCita(nombre='Ortodoncia', duracion_minutos=30, precio=800,
                     requiere_anticipo=False, color='#72B843'),
            TipoCita(nombre='Operatoria / Restauracion', duracion_minutos=60, precio=700,
                     requiere_anticipo=False, color='#F2853D'),
            TipoCita(nombre='Revision / Control', duracion_minutos=30, precio=300,
                     requiere_anticipo=False, color='#F5DC57'),
            TipoCita(nombre='Extraccion', duracion_minutos=45, precio=500,
                     requiere_anticipo=False, color='#AB47BC'),
            TipoCita(nombre='Endodoncia', duracion_minutos=90, precio=2500,
                     requiere_anticipo=True, color='#1E88E5'),
            TipoCita(nombre='Sonrisas Magicas (Seguimiento)', duracion_minutos=45, precio=600,
                     requiere_anticipo=False, color='#00B5AD'),
        ]
        db.session.add_all(tipos)

    # Dentistas con sus colores del cliente
    if not Dentista.query.first():
        dentistas_data = [
            ('Fernanda', 'Odontologia General', '#FF7043'),
            ('Karen', 'Odontologia General', '#E53935'),
            ('Ale', 'Odontopediatria', '#7B1FA2'),
            ('Sofia', 'Endodoncia', '#2E7D32'),
            ('Carmen', 'Odontopediatria', '#1565C0'),
            ('Giovanni', 'Ortodoncia', '#F48FB1'),
            ('Daniel Martinez', 'Periodoncia', '#F9A825'),
            ('Antonio', 'Cirugia Maxilofacial', '#757575'),
            ('Eli', 'Tecnico de Laboratorio', '#546E7A'),
            ('Jose', 'Protesis Dental', '#1E88E5'),
            ('Paulina', 'Odontopediatria', '#AB47BC'),
        ]
        for nombre, especialidad, color in dentistas_data:
            d = Dentista(nombre=nombre, especialidad=especialidad, color=color)
            db.session.add(d)
            db.session.flush()
            # Horario L-V 9-18
            for dia in range(5):
                from datetime import time as t
                db.session.add(HorarioDentista(
                    dentista_id=d.id, dia_semana=dia,
                    hora_inicio=t(9, 0), hora_fin=t(18, 0)
                ))

    # Configuracion consultorio
    if not ConfiguracionConsultorio.query.first():
        db.session.add(ConfiguracionConsultorio())

    # Plantillas de mensajes
    if not PlantillaMensaje.query.first():
        plantillas = [
            PlantillaMensaje(
                nombre='Info Primera Consulta',
                tipo='info_consulta',
                contenido='Hola buenos dias/ buenas tardes\nClaro\nLa consulta tiene un costo de $550.00 le incluye su diagnostico, plan de tratamiento, presupuesto y radiografias intraorales que requiera su pequeno o pequena :)'
            ),
            PlantillaMensaje(
                nombre='Solicitud de Anticipo',
                tipo='anticipo',
                contenido='Con gusto :) para las citas de pacientes que vienen por 1a vez a nuestro consultorio dental, solicitamos un pago anticipado del 50% del total de la consulta. Esto nos ayuda a garantizar tu cita y a ofrecerte el mejor servicio posible.\n\nTRANSFERENCIAS:\nPaulina Mendoza Ordonez\nBBVA\nTarjeta: 4152314207155287\nCLABE: 012180015419659725\n\nEn caso de no poder acudir les pedimos reagendar con 24hrs de anticipacion, si no acuden no sera reembolsable.'
            ),
            PlantillaMensaje(
                nombre='Confirmacion de Cita',
                tipo='confirmacion',
                contenido='Perfecto\nLe compartimos toda la informacion\n\nNos vemos el dia {fecha} de {hora_inicio} a las {hora_fin}'
            ),
            PlantillaMensaje(
                nombre='Recordatorio 24h',
                tipo='recordatorio_24h',
                contenido='Hola buenas tardes\nComo esta? Le escribo para confirmar la cita de {nombre_paciente} manana a las {hora}.\nGracias :)'
            ),
            PlantillaMensaje(
                nombre='Sonrisas Magicas',
                tipo='sonrisas_magicas',
                contenido='Hola buenos dias/tardes :) Como esta? Le escribo para agendar la cita de {nombre_paciente}, ya nos toca su cita de revision, control y mantenimiento para realizar su limpieza y aplicacion de fluor\nLes acomoda vernos (ofrecer dias de acuerdo cuando viene el Dr/a y entre semana o sabado de acuerdo a las necesidades del Px)?'
            ),
            PlantillaMensaje(
                nombre='Protocolo Postconsulta',
                tipo='postconsulta',
                contenido='Hola Sra/Sr buenas tardes :) Como esta? Le comparto la foto (DIPLOMA Y PIN) de {nombre_paciente}, nos encantaria conocer su experiencia con nosotros le mandare un link {google_reviews_link} y solo debe dar clic, muchas gracias :)'
            ),
            PlantillaMensaje(
                nombre='Cumpleanos',
                tipo='cumpleanos',
                contenido='Hola {nombre_tutor}! En el mes de cumpleanos de {nombre_paciente} tiene un regalo especial esperandole: su PIN cumpleanero. Solo tiene que venir a su cita este mes para recibirlo. Le esperamos con gusto!'
            ),
        ]
        db.session.add_all(plantillas)

    # Plantillas nuevas (agregar si no existen, para BDs existentes)
    if not PlantillaMensaje.query.filter_by(tipo='no_asistencia_reagendar').first():
        db.session.add(PlantillaMensaje(
            nombre='Reagendar No Asistencia',
            tipo='no_asistencia_reagendar',
            contenido='Estimado/a, le escribimos de La Casa del Sr. Perez.\nLamentamos que {nombre_paciente} no haya podido asistir a su cita programada el {fecha}.\nNos encantaria poder atenderle en otra fecha. Responda a este mensaje y con gusto le ayudamos a reagendar su cita.',
        ))
    if not PlantillaMensaje.query.filter_by(tipo='proxima_visita').first():
        db.session.add(PlantillaMensaje(
            nombre='Recordatorio Proxima Visita',
            tipo='proxima_visita',
            contenido='Hola {nombre_tutor}! Le recordamos que ya es momento de programar la proxima cita de {nombre_paciente} en La Casa del Sr. Perez.\nEscribanos para buscarle un horario disponible :)',
        ))

    db.session.commit()


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
