"""
Extensiones Flask inicializadas sin app para evitar importaciones circulares.
Se inicializan con .init_app(app) en app.py.
"""
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_mail import Mail
from flask_caching import Cache

login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=['200 per day', '50 per hour'])
migrate = Migrate()
mail = Mail()
cache = Cache()
