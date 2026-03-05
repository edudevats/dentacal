import os
import logging
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuración base compartida."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///consultorio.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Flask-WTF CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hora

    # Flask-Limiter
    RATELIMIT_DEFAULT = '200 per day;50 per hour'
    RATELIMIT_STORAGE_URI = 'memory://'

    # Flask-Caching
    CACHE_TYPE = 'SimpleCache'        # dev: SimpleCache, prod: RedisCache
    CACHE_DEFAULT_TIMEOUT = 300       # 5 minutos
    CACHE_REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

    # Flask-Mail
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.environ.get(
        'MAIL_DEFAULT_SENDER',
        'La Casa del Sr. Pérez <noreply@consultorio.com>'
    )
    MAIL_SUPPRESS_SEND = False

    # JWT (API tokens)
    JWT_EXPIRATION_SECONDS = int(os.environ.get('JWT_EXPIRATION_SECONDS', 3600))
    JWT_ALGORITHM = 'HS256'

    # Timezone
    TIMEZONE = 'America/Mexico_City'

    # Twilio
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
    TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')

    # Anthropic
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

    # Consultorio
    CLABE_INTERBANCARIA = os.environ.get('CLABE_INTERBANCARIA', '')
    GOOGLE_MAPS_REVIEW_URL = os.environ.get('GOOGLE_MAPS_REVIEW_URL', '')
    CONSULTORIO_NOMBRE = os.environ.get('CONSULTORIO_NOMBRE', 'La Casa del Sr. Pérez')
    CONSULTORIO_DIRECCION = os.environ.get('CONSULTORIO_DIRECCION', '')
    CONSULTORIO_TELEFONO = os.environ.get('CONSULTORIO_TELEFONO', '')

    # Admin inicial
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@consultorio.com')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Admin1234!')

    # Logging
    LOG_LEVEL = logging.INFO
    LOG_FILE = 'app.log'
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT = 5


class DevelopmentConfig(Config):
    DEBUG = True
    WTF_CSRF_ENABLED = True
    LOG_LEVEL = logging.DEBUG
    TALISMAN_ENABLED = False
    CACHE_TYPE = 'SimpleCache'
    MAIL_SUPPRESS_SEND = True   # No enviar emails reales en desarrollo


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True
    TALISMAN_ENABLED = True
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'SimpleCache')
    TALISMAN_CSP = {
        'default-src': "'self'",
        'script-src': ["'self'", 'cdn.jsdelivr.net', "'unsafe-inline'"],
        'style-src': ["'self'", 'cdn.jsdelivr.net', "'unsafe-inline'"],
        'font-src': ["'self'", 'cdn.jsdelivr.net'],
        'img-src': ["'self'", 'data:'],
        'connect-src': ["'self'"],
    }


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    RATELIMIT_ENABLED = False
    TALISMAN_ENABLED = False
    CACHE_TYPE = 'NullCache'        # Sin caché en tests
    MAIL_SUPPRESS_SEND = True
    SERVER_NAME = 'localhost'


config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}


def get_config(env_name=None):
    env = env_name or os.environ.get('FLASK_ENV', 'development')
    return config_map.get(env, DevelopmentConfig)
