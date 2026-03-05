"""
WSGI entry point para PythonAnywhere.

En el panel de PythonAnywhere (Web > WSGI configuration file):
  - Apuntar a este archivo
  - Ajustar PYTHONANYWHERE_USER con tu usuario

Ejemplo de ruta en PythonAnywhere:
  /home/tupyuser/dental_app/wsgi.py
"""
import sys
import os

# Ajusta esta ruta a la ubicación real del proyecto en PythonAnywhere
project_path = os.path.dirname(os.path.abspath(__file__))
if project_path not in sys.path:
    sys.path.insert(0, project_path)

os.environ.setdefault('FLASK_ENV', 'production')

from app import create_app

application = create_app('production')
