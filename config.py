import os
import logging
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_key_change_in_production')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(BASE_DIR, 'app.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 280,   # Evita "MySQL server has gone away" (timeout 5min)
        'pool_size': 3,        # Máx conexiones permanentes
        'max_overflow': 2,     # Conexiones extra bajo carga
        'pool_timeout': 20,    # Segundos antes de error si no hay conexión libre
    }

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600

    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_SECURE = False  # True en produccion con HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Rate limiting
    RATELIMIT_STORAGE_URL = 'memory://'
    RATELIMIT_DEFAULT = '200 per hour'

    # Cache
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 300

    # Logging
    LOG_LEVEL = logging.INFO

    # Bot IA
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
    AI_MODEL = 'gemini-3-flash-preview'

    # Twilio
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
    TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')

    # Datos consultorio para el bot
    CLABE_INTERBANCARIA = os.environ.get('CLABE_INTERBANCARIA', '012180015419659725')
    TARJETA_BBVA = os.environ.get('TARJETA_BBVA', '4152314207155287')
    NOMBRE_TITULAR_CUENTA = os.environ.get('NOMBRE_TITULAR_CUENTA', 'Paulina Mendoza Ordoñez')
    GOOGLE_REVIEWS_LINK = os.environ.get('GOOGLE_REVIEWS_LINK', 'https://n9.cl/ufkug')

    # Scheduler
    SCHEDULER_ENABLED = os.environ.get('SCHEDULER_ENABLED', 'true').lower() == 'true'

    # Zona horaria
    TIMEZONE = 'America/Mexico_City'


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    LOG_LEVEL = logging.DEBUG


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    LOG_LEVEL = logging.WARNING
    RATELIMIT_DEFAULT = '100 per hour'

    # En produccion usar PostgreSQL:
    # SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    # SQLite no soporta pool_size/max_overflow/pool_timeout
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    WTF_CSRF_ENABLED = False
    SCHEDULER_ENABLED = False
    GEMINI_API_KEY = 'test_key'
    TWILIO_ACCOUNT_SID = 'test_sid'
    TWILIO_AUTH_TOKEN = 'test_token'


config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig,
}
