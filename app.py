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

    # Verificar que la BD existe antes de iniciar
    with app.app_context():
        import models  # noqa: F401 — registers all models with SQLAlchemy metadata
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if db_uri.startswith('sqlite:///'):
            db_path = db_uri.replace('sqlite:///', '')
            if os.path.exists(db_path):
                app.logger.info('BD encontrada: %s (%d bytes)', db_path, os.path.getsize(db_path))
            else:
                app.logger.warning('BD NO encontrada en %s — se crearan tablas vacias.', db_path)
        # Crear tablas que falten (no borra ni modifica tablas existentes)
        db.create_all()


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
    from routes.api_recordatorios import recordatorios_bp

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
    app.register_blueprint(recordatorios_bp)


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


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
