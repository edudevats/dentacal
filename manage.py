#!/usr/bin/env python
"""
CLI de gestión — La Casa del Sr. Pérez

Uso:
  python manage.py db init          # Inicializar Alembic
  python manage.py db migrate -m "msg"  # Generar migración
  python manage.py db upgrade       # Aplicar migraciones
  python manage.py crear_admin      # Crear usuario admin interactivo
  python manage.py shell            # Shell con contexto Flask
  python manage.py test             # Correr pytest
  python manage.py seed             # Insertar datos semilla
"""
import sys
import os
import click
from flask.cli import FlaskGroup, with_appcontext

from app import create_app
from models import db

# Determinar entorno
env = os.environ.get('FLASK_ENV', 'development')


def get_app():
    return create_app(env)


@click.group(cls=FlaskGroup, create_app=get_app)
def cli():
    """La Casa del Sr. Pérez — CLI de gestión."""
    pass


@cli.command('crear_admin')
@with_appcontext
def crear_admin():
    """Crea un usuario administrador de forma interactiva."""
    from models import User

    click.echo('\n=== Crear Usuario Administrador ===')
    username = click.prompt('Username')
    email = click.prompt('Email')
    password = click.prompt('Password', hide_input=True, confirmation_prompt=True)

    if User.query.filter((User.username == username) | (User.email == email)).first():
        click.secho('Error: El usuario o email ya existe.', fg='red')
        sys.exit(1)

    user = User(username=username, email=email, role='admin')
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    click.secho(f'✅  Admin "{username}" creado correctamente.', fg='green')


@cli.command('seed')
@with_appcontext
def seed():
    """Inserta datos semilla (consultorios, tipos de cita, plantillas)."""
    from app import seed_initial_data, create_app
    app = create_app(env)
    seed_initial_data(app)
    click.secho('✅  Datos semilla insertados.', fg='green')


@cli.command('shell')
@with_appcontext
def shell():
    """Abre un shell Python con contexto Flask."""
    import code
    from models import (
        db, User, Paciente, Cita, Dentista,
        Consultorio, TipoCita, PlantillaMensaje,
    )
    ctx = {
        'db': db,
        'User': User,
        'Paciente': Paciente,
        'Cita': Cita,
        'Dentista': Dentista,
        'Consultorio': Consultorio,
        'TipoCita': TipoCita,
        'PlantillaMensaje': PlantillaMensaje,
    }
    click.echo('Flask shell — variables disponibles: ' + ', '.join(ctx.keys()))
    code.interact(local=ctx)


@cli.command('test')
@click.argument('path', default='tests/', required=False)
@click.option('--cov', is_flag=True, default=False, help='Generar reporte de cobertura')
@click.option('--no-cov', 'skip_cov', is_flag=True, default=False, help='Omitir cobertura')
def run_tests(path, cov, skip_cov):
    """Corre la suite de tests con pytest (+ coverage por defecto)."""
    import subprocess
    cmd = [sys.executable, '-m', 'pytest', path, '-v']
    if not skip_cov:
        cmd += ['--cov=.', '--cov-report=term-missing', '--cov-config=.coveragerc']
    result = subprocess.run(cmd, check=False)
    sys.exit(result.returncode)


if __name__ == '__main__':
    cli()
