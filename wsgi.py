"""
Entry point para PythonAnywhere y Gunicorn.

PythonAnywhere WSGI config:
    import sys
    sys.path.insert(0, '/home/TU_USUARIO/lacasadelsrperez')
    from wsgi import application
"""
import os
from dotenv import load_dotenv

# Cargar .env (util en desarrollo; en produccion las vars se setean en el panel)
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from app import create_app

application = create_app(os.environ.get('FLASK_ENV', 'production'))

if __name__ == '__main__':
    application.run()
