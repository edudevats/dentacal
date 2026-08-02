"""
Singletons de extensiones Flask.
Importar desde aqui para evitar importaciones circulares.
"""
from functools import wraps
from flask import flash, redirect, url_for, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from flask_mail import Mail
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import event
from sqlalchemy.orm import Session as OrmSession


# Una sesion secundaria no es una frontera durable si la scoped session ya
# escribio dentro de su transaccion outer. Los listeners se registran al
# importar las extensiones, antes de que create_app() pueda provocar un flush.
LEDGER_FLUSHED_UNCOMMITTED = 'ledger_flushed_uncommitted'


@event.listens_for(OrmSession, 'after_flush_postexec')
def _marcar_flush_pendiente(session, _flush_context):
    session.info[LEDGER_FLUSHED_UNCOMMITTED] = True


@event.listens_for(OrmSession, 'after_transaction_end')
def _limpiar_flush_al_terminar_outer(session, transaction):
    if transaction.parent is None:
        session.info.pop(LEDGER_FLUSHED_UNCOMMITTED, None)


def permiso_requerido(permiso):
    """Decorator that checks if the current user has the given permission."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            if not current_user.tiene_permiso(permiso):
                if request.is_json or request.path.startswith('/api/'):
                    return jsonify(error='No tienes permisos para esta seccion.'), 403
                flash('No tienes permisos para acceder a esta seccion.', 'danger')
                return redirect(url_for('main.dashboard'))  # dashboard handles routing
            return f(*args, **kwargs)
        return decorated_function
    return decorator

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)
cache = Cache()
mail = Mail()
scheduler = BackgroundScheduler(timezone='America/Mexico_City')
