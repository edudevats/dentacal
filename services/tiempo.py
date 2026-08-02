"""
Reloj del consultorio. Unica fuente de la hora local para todo el sistema.

Todo lo que se persista o compare en el dominio de citas y mensajes debe usar
ahora_local(), nunca datetime.utcnow(), para que los jobs no se disparen con
horas de desfase.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo('America/Mexico_City')


def ahora_local():
    """Retorna el datetime actual en la timezone del consultorio, sin tzinfo."""
    return datetime.now(TIMEZONE).replace(tzinfo=None)
