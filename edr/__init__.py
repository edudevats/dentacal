"""Persistencia, logica y paginas del modulo contable EDR."""

from .pages import edr_pages_bp
from .api import edr_api_bp

__all__ = ['edr_pages_bp', 'edr_api_bp']
