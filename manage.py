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
# Ruta explicita para no depender del directorio de trabajo (ver nota en app.py).
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

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


# --- Diagnostico de plantillas de WhatsApp ---------------------------------
#
# Twilio rechaza un envio con "The Content Variables parameter is invalid"
# cuando lo que manda la app no encaja con la plantilla aprobada en Twilio.
# Estos dos comandos muestran los dos lados de esa comparacion sin gastar un
# mensaje. Necesitan las credenciales de Twilio, asi que corren en produccion.

# Tope de caracteres del cuerpo de un mensaje de plantilla de WhatsApp.
LIMITE_CUERPO = 1024


def _problemas_del_valor(valor):
    """Motivos por los que WhatsApp rechazaria este valor de variable.

    Meta no acepta saltos de linea, tabuladores, cuatro o mas espacios
    seguidos ni valores vacios dentro de una variable de plantilla.
    """
    import re

    problemas = []
    if not valor:
        problemas.append('viene vacio')
    if '\n' in valor:
        problemas.append(f'trae {valor.count(chr(10))} salto(s) de linea')
    if '\t' in valor:
        problemas.append('trae tabuladores')
    if re.search(r'    +', valor):
        problemas.append('trae 4 o mas espacios seguidos')
    return problemas


def _cliente_twilio():
    from flask import current_app

    sid = current_app.config.get('TWILIO_ACCOUNT_SID', '')
    token = current_app.config.get('TWILIO_AUTH_TOKEN', '')
    if not sid or not token or sid.startswith('test'):
        raise click.ClickException(
            'No hay credenciales reales de Twilio en este entorno. '
            'Este comando solo sirve en produccion.')
    from twilio.rest import Client
    return Client(sid, token)


@app.cli.command('verificar_plantillas')
def verificar_plantillas():
    """Compara cada ContentSid guardado contra la plantilla real de Twilio."""
    import re
    from models import PlantillaMensaje
    from services.whatsapp_service import orden_variables

    with app.app_context():
        cliente = _cliente_twilio()
        plantillas = (PlantillaMensaje.query
                      .filter(PlantillaMensaje.content_sid.isnot(None))
                      .order_by(PlantillaMensaje.tipo).all())
        if not plantillas:
            click.echo('Ninguna plantilla tiene ContentSid: todo sale como '
                       'texto libre.')
            return

        for p in plantillas:
            click.echo('')
            click.echo(f'== {p.tipo}  ({p.content_sid})')
            nombres = [n.strip() for n in orden_variables(p).split(',') if n.strip()]
            click.echo(f'   la app manda {len(nombres)} variable(s): '
                       f'{", ".join(nombres) or "ninguna"}')
            try:
                contenido = cliente.content.v1.contents(p.content_sid).fetch()
            except Exception as e:
                click.echo(f'   ERROR al leer la plantilla en Twilio: {e}')
                continue

            cuerpo = ''
            for _tipo_twilio, datos in (contenido.types or {}).items():
                if isinstance(datos, dict) and datos.get('body'):
                    cuerpo = datos['body']
                    break
            placeholders = re.findall(r'{{\s*([^}]+?)\s*}}', cuerpo)
            numeros = sorted({int(x) for x in placeholders if x.isdigit()})
            con_nombre = [x for x in placeholders if not x.isdigit()]

            click.echo(f'   Twilio la llama "{contenido.friendly_name}" '
                       f'({contenido.language})')
            click.echo(f'   declara: {contenido.variables}')
            click.echo(f'   cuerpo: {cuerpo[:200]!r}')

            esperado = list(range(1, len(nombres) + 1))
            if con_nombre:
                click.echo('   >>> NO COINCIDE: la plantilla usa variables con '
                           f'nombre ({con_nombre}) y la app manda numeradas '
                           f'{esperado}. Hay que volver a registrarla en Twilio '
                           'usando {{1}}, {{2}}, {{3}}.')
            elif numeros != esperado:
                click.echo('   >>> NO COINCIDE: la app manda las variables '
                           f'{esperado} y la plantilla usa {numeros}. '
                           'Esto es exactamente el error 21656 "Content '
                           'Variables parameter is invalid".')
            else:
                click.echo('   variables OK')

            try:
                aprobacion = cliente.content.v1.contents(
                    p.content_sid).approval_fetch().fetch()
                estado = (aprobacion.whatsapp or {}).get('status')
                click.echo(f'   aprobacion de WhatsApp: {estado}')
            except Exception as e:
                click.echo(f'   no se pudo leer la aprobacion: {e}')


@app.cli.command('revisar_envio_doctor')
@click.argument('dentista_id', type=int)
@click.argument('tipo', type=click.Choice(['horario', 'dia', 'semana']))
@click.option('--fecha', default=None, help='YYYY-MM-DD; por defecto hoy.')
def revisar_envio_doctor(dentista_id, tipo, fecha):
    """Muestra lo que se le mandaria a un doctor, SIN mandarlo."""
    from datetime import date

    from models import Dentista, PlantillaMensaje
    from services.doctor_envios import ARMADORES, EnvioDoctorError
    from services.paises import formatear_numero_e164
    from services.whatsapp_service import kwargs_plantilla

    with app.app_context():
        dentista = Dentista.query.get(dentista_id)
        if not dentista:
            raise click.ClickException(f'No hay dentista con id {dentista_id}.')

        cuando = date.fromisoformat(fecha) if fecha else None
        try:
            tipo_plantilla, valores, fallback = ARMADORES[tipo](dentista, cuando)
        except EnvioDoctorError as e:
            click.echo(f'No hay nada que mandar: {e}')
            return

        numero = formatear_numero_e164(dentista.telefono,
                                       getattr(dentista, 'pais', 'MX'))
        click.echo(f'Doctor: {dentista.nombre}  ->  {numero or "SIN NUMERO"}')

        plantilla = PlantillaMensaje.query.filter_by(
            tipo=tipo_plantilla, activo=True).first()
        if plantilla is None:
            click.echo(f'No existe la plantilla "{tipo_plantilla}": sale como '
                       'texto libre.')
        else:
            kwargs = kwargs_plantilla(plantilla, valores)
            if not kwargs:
                click.echo(f'La plantilla "{tipo_plantilla}" no tiene '
                           'ContentSid: sale como texto libre (solo llega '
                           'dentro de la ventana de 24 h).')
            else:
                click.echo(f'Plantilla "{tipo_plantilla}" -> '
                           f'{kwargs["content_sid"]}')
                click.echo(f'ContentVariables: {kwargs["content_variables"]}')

        click.echo('')
        for posicion, (nombre, valor) in enumerate(valores.items(), start=1):
            valor = str(valor)
            problemas = _problemas_del_valor(valor)
            marca = 'PROBLEMA' if problemas else 'ok'
            click.echo(f'  variable {posicion} ({nombre}): {len(valor)} '
                       f'caracteres [{marca}]')
            for problema in problemas:
                click.echo(f'        - {problema}')

        largo = len(fallback)
        click.echo('')
        click.echo(f'Cuerpo completo del mensaje: {largo} caracteres '
                   f'(WhatsApp corta en {LIMITE_CUERPO}).')
        if largo > LIMITE_CUERPO:
            click.echo('  >>> PASADO DEL LIMITE: no cabe en una plantilla de '
                       'WhatsApp.')


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
