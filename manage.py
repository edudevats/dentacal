"""
CLI de administracion del proyecto.

Uso:
    python manage.py crear_admin
    python manage.py seed
    python manage.py db upgrade
    python manage.py test
    python manage.py shell
"""
import os
import click
from dotenv import load_dotenv
load_dotenv()

from app import create_app
from extensions import db

app = create_app(os.environ.get('FLASK_ENV', 'development'))


@app.cli.command('crear_admin')
@click.option('--username', default=lambda: os.environ.get('ADMIN_USERNAME', 'admin'))
@click.option('--email', default=lambda: os.environ.get('ADMIN_EMAIL', 'admin@consultorio.com'))
@click.option('--password', default=lambda: os.environ.get('ADMIN_PASSWORD', 'Admin123!'))
def crear_admin(username, email, password):
    """Crea el usuario administrador inicial."""
    from models import User, RolUsuario
    with app.app_context():
        if User.query.filter_by(username=username).first():
            click.echo(f'El usuario {username} ya existe.')
            return
        user = User(username=username, email=email, rol=RolUsuario.admin)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f'Admin {username} creado correctamente.')


@app.cli.command('seed')
def seed():
    """Inserta datos de prueba adicionales."""
    from models import Paciente, EstatusCRM
    with app.app_context():
        if Paciente.query.first():
            click.echo('Ya existen pacientes. Seed omitido.')
            return
        pacientes = [
            Paciente(
                nombre='Maria Garcia Lopez',
                fecha_nacimiento=None,
                telefono='5551234567', whatsapp='5551234567',
                nombre_tutor='Rosa Lopez', telefono_tutor='5559876543',
                escuela='Escuela Primaria Juarez',
                estatus_crm=EstatusCRM.activo,
            ),
            Paciente(
                nombre='Carlos Martinez Perez',
                telefono='5552345678', whatsapp='5552345678',
                estatus_crm=EstatusCRM.prospecto,
            ),
            Paciente(
                nombre='Sofia Hernandez',
                telefono='5553456789', whatsapp='5553456789',
                estatus_crm=EstatusCRM.alta,
            ),
        ]
        db.session.add_all(pacientes)
        db.session.commit()
        click.echo(f'{len(pacientes)} pacientes de prueba creados.')


@app.cli.command('test')
@click.argument('path', default='tests/')
def run_tests(path):
    """Ejecuta los tests con pytest."""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', path, '-v'],
        cwd=os.path.dirname(__file__)
    )
    raise SystemExit(result.returncode)


@app.cli.command('migrar_grupos')
def migrar_grupos():
    """Crea grupos familiares a partir de relaciones tutor_id existentes
    y pacientes que compartan numero de WhatsApp."""
    from models import Paciente, GrupoFamiliar
    with app.app_context():
        grupos_creados = 0
        pacientes_asignados = 0

        # Paso 1: Agrupar por tutor_id
        menores = Paciente.query.filter(
            Paciente.tutor_id.isnot(None),
            Paciente.eliminado == False,
            Paciente.grupo_familiar_id == None,
        ).all()

        for menor in menores:
            tutor = db.session.get(Paciente, menor.tutor_id)
            if not tutor or tutor.eliminado:
                continue

            if tutor.grupo_familiar_id:
                # Tutor ya tiene grupo: asignar menor al mismo
                menor.grupo_familiar_id = tutor.grupo_familiar_id
                pacientes_asignados += 1
            else:
                # Crear grupo nuevo
                apellido = tutor.nombre.split()[-1] if tutor.nombre else 'Sin nombre'
                tel = tutor.whatsapp or tutor.telefono or ''
                grupo = GrupoFamiliar(nombre=f'Familia {apellido}', telefono_principal=tel)
                db.session.add(grupo)
                db.session.flush()
                tutor.grupo_familiar_id = grupo.id
                menor.grupo_familiar_id = grupo.id
                grupos_creados += 1
                pacientes_asignados += 2

        # Paso 2: Agrupar pacientes que compartan mismo whatsapp (sin grupo aun)
        from sqlalchemy import func
        duplicados = db.session.query(
            Paciente.whatsapp
        ).filter(
            Paciente.eliminado == False,
            Paciente.whatsapp.isnot(None),
            Paciente.whatsapp != '',
            Paciente.grupo_familiar_id == None,
        ).group_by(Paciente.whatsapp).having(func.count(Paciente.id) > 1).all()

        for (wa_num,) in duplicados:
            pacs = Paciente.query.filter_by(
                whatsapp=wa_num, eliminado=False, grupo_familiar_id=None
            ).all()
            if len(pacs) < 2:
                continue
            apellido = pacs[0].nombre.split()[-1] if pacs[0].nombre else 'Sin nombre'
            grupo = GrupoFamiliar(nombre=f'Familia {apellido}', telefono_principal=wa_num)
            db.session.add(grupo)
            db.session.flush()
            for p in pacs:
                p.grupo_familiar_id = grupo.id
                pacientes_asignados += 1
            grupos_creados += 1

        db.session.commit()
        click.echo(f'{grupos_creados} grupo(s) familiar(es) creado(s).')
        click.echo(f'{pacientes_asignados} paciente(s) asignado(s) a grupos.')


@app.cli.command('shell')
def shell():
    """Shell interactivo con contexto de la app."""
    import code
    with app.app_context():
        ctx = {'app': app, 'db': db}
        from models import (User, Paciente, Cita, Dentista, Consultorio,
                            TipoCita, ConfiguracionConsultorio)
        ctx.update(locals())
        code.interact(local=ctx, banner='La Casa del Sr. Perez - Shell')


if __name__ == '__main__':
    app.cli()
