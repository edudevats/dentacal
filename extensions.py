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
