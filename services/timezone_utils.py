"""
Utilidades de zona horaria usando pytz.
Zona principal: America/Mexico_City (CST/CDT)
"""
import pytz
from datetime import datetime

MEXICO_TZ = pytz.timezone('America/Mexico_City')
UTC = pytz.utc


def now_mexico():
    """Datetime actual en zona horaria de México (aware)."""
    return datetime.now(MEXICO_TZ)


def now_utc():
    """Datetime actual en UTC (aware)."""
    return datetime.now(UTC)


def to_mexico(dt):
    """Convierte un datetime (naive UTC o aware) a hora de México."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = UTC.localize(dt)
    return dt.astimezone(MEXICO_TZ)


def to_utc(dt):
    """Convierte un datetime (naive México o aware) a UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = MEXICO_TZ.localize(dt)
    return dt.astimezone(UTC)


def format_mexico(dt, fmt='%d/%m/%Y %H:%M'):
    """Formatea un datetime en hora de México."""
    if dt is None:
        return ''
    return to_mexico(dt).strftime(fmt)


def naive_utcnow():
    """datetime.utcnow() compatible (naive) para SQLite/SQLAlchemy."""
    return datetime.utcnow()
