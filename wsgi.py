import sys
import os

path = '/home/edudracos/dentacal'
if path not in sys.path:
    sys.path.append(path)

from app import create_app

# Usar 'production' de forma predeterminada para el entorno WSGI a menos que se especifique lo contrario
application = create_app(os.environ.get('FLASK_ENV', 'production'))
