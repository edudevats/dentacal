import os
import sys
import logging
from flask import Flask, jsonify, render_template
from dotenv import load_dotenv

# Ruta explicita: load_dotenv() sin argumento busca el .env desde el CWD hacia
# arriba, asi que arrancar desde otra carpeta (config del IDE, tarea, flask run
# desde un subdir) no lo encontraba, DATABASE_URL quedaba vacio y la app caia a
# SQLite (app.db) en silencio. Anclarlo al directorio de este archivo lo evita.
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Subcomandos de Flask-Migrate/Alembic (`flask db <x>`).
_COMANDOS_ALEMBIC = {
    'upgrade', 'downgrade', 'migrate', 'revision', 'stamp', 'history',
    'current', 'heads', 'branches', 'show', 'merge', 'init', 'edit', 'check',
}


def _corriendo_comando_migracion():
    """True si el proceso actual es un `flask db <subcomando>`.

    Flask-Migrate importa la app para correr Alembic, asi que el create_all() de
    _init_extensions() se ejecuta ANTES que las migraciones. Sobre una BD vacia
    eso crea todas las tablas desde los modelos sin registrar nada en
    alembic_version, y el upgrade siguiente muere con "Duplicate column name"
    al intentar aplicar la migracion 1 sobre un esquema que ya esta en head.
    En SQLite nunca se noto porque app.db ya existia creado.
    """
    try:
        i = sys.argv.index('db')
    except ValueError:
        return False
    return i + 1 < len(sys.argv) and sys.argv[i + 1] in _COMANDOS_ALEMBIC


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    app = Flask(__name__)

    # Config
    from config import config_map
    app.config.from_object(config_map.get(config_name, config_map['default']))

    # DATABASE_URL es obligatoria fuera de la suite de tests. Sin ella no
    # arrancamos: antes se caia a SQLite (app.db) en silencio, y en PythonAnywhere
    # SQLite provoca "disk I/O error" y perdida de pacientes. 'testing' usa su
    # propia URI (SQLite en memoria), asi que se exceptua.
    if config_name != 'testing':
        uri = str(app.config.get('SQLALCHEMY_DATABASE_URI') or '')
        if not uri:
            raise RuntimeError(
                'Falta DATABASE_URL en el .env. Configúrala con la cadena '
                'mysql+pymysql://... (la BD local de desarrollo, la misma que MySQL '
                'en producción). Revisa que el .env esté en %s.'
                % os.path.dirname(__file__)
            )
        if uri.startswith('sqlite'):
            raise RuntimeError(
                'La app está apuntando a SQLite. Configura DATABASE_URL con la '
                'cadena mysql+pymysql://... en el .env '
                '(guía: scripts/migrate_sqlite_to_mysql.py).'
            )

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

    # Sesion o token CSRF expirados en llamadas /api/: responder JSON claro
    # (401/400) en vez de redirigir al HTML de login. Antes, el fetch seguia el
    # redirect 302 y recibia el HTML del login, rompiendo el guardado en silencio
    # (el paciente NO se guardaba y la recepcionista no se enteraba).
    from flask import request, jsonify, redirect, url_for
    from flask_wtf.csrf import CSRFError

    @login_manager.unauthorized_handler
    def _unauthorized():
        if request.path.startswith('/api/'):
            return jsonify(error='session_expired',
                           mensaje='Tu sesión expiró. Inicia sesión de nuevo.'), 401
        return redirect(url_for('auth.login', next=request.path))

    @app.errorhandler(CSRFError)
    def _csrf_error(e):
        if request.path.startswith('/api/'):
            return jsonify(error='csrf_expired',
                           mensaje='Tu sesión expiró. Inicia sesión de nuevo.'), 400
        return redirect(url_for('auth.login'))

    @login_manager.user_loader
    def load_user(user_id):
        # Corre en CADA request autenticado, dentro de preprocess_request. Un
        # 2013 de MySQL aqui tumba la pagina entera antes de llegar a la vista:
        # el 2026-08-26 dejo a recepcion sin calendario. Es una lectura pura,
        # asi que se puede reintentar sin riesgo.
        from models import User
        from services.db_resiliencia import reintentar_lectura

        def _cargar():
            return User.query.get(int(user_id))

        try:
            return reintentar_lectura(_cargar, descripcion='load_user')
        except Exception as e:
            app.logger.error(f'No se pudo cargar el usuario {user_id}: {e}')
            return None

    # Verificar que la BD existe antes de iniciar
    with app.app_context():
        import models  # noqa: F401 — registers all models with SQLAlchemy metadata
        import edr.models  # noqa: F401 — registers EDR models in shared metadata
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
        if db_uri.startswith('sqlite:///'):
            db_path = db_uri.replace('sqlite:///', '')
            if os.path.exists(db_path):
                app.logger.info('BD encontrada: %s (%d bytes)', db_path, os.path.getsize(db_path))
            else:
                app.logger.warning('BD NO encontrada en %s — se crearan tablas vacias.', db_path)
        # Crear tablas que falten (no borra ni modifica tablas existentes).
        # Durante `flask db upgrade` se omite: ahi el dueño del esquema es
        # Alembic, y adelantarse con create_all() rompe las migraciones.
        if _corriendo_comando_migracion():
            app.logger.info('Comando de migracion detectado: se omite create_all().')
        else:
            db.create_all()
            from edr.seed import seed_edr_catalogos
            seed_edr_catalogos()


def _register_blueprints(app):
    from edr import edr_api_bp, edr_pages_bp
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
    from routes.api_turnos import turnos_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(edr_pages_bp)
    app.register_blueprint(edr_api_bp)
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
    app.register_blueprint(turnos_bp)


def _register_error_handlers(app):
    from flask import request
    from sqlalchemy.exc import OperationalError

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

    @app.errorhandler(OperationalError)
    def bd_no_disponible(e):
        """
        MySQL se cayo a media consulta (error 2013).

        Un 500 con traceback no le dice nada a recepcion. Un 503 con un mensaje
        claro si: el problema es momentaneo y basta recargar. El rollback deja
        la sesion limpia para el siguiente request de este worker.
        """
        from services.db_resiliencia import sanear_sesion
        sanear_sesion()
        app.logger.error(f'BD no disponible en {request.path}: {e}')
        if _is_api_request():
            return jsonify(
                error='bd_no_disponible',
                mensaje=('La base de datos no respondió. Vuelve a intentarlo '
                         'en unos segundos.')), 503
        return render_template('errors/500.html'), 503


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
