"""plantillas resumen_doctor y cita_reagendada

Estos dos mensajes tenian su texto escrito directo en el codigo, sin fila en
plantillas_mensaje. Sin fila no hay donde pegar el ContentSid de la plantilla
aprobada de WhatsApp, asi que seguirian saliendo como texto libre y chocando
con el error 63016 fuera de la ventana de 24 h.

Ademas sincroniza el texto de 'recordatorio_cita_hoy' y 'postconsulta' con el
cuerpo que se registro en Twilio: la bitacora tiene que decir exactamente lo
que recibe el paciente. Solo se actualizan si siguen con el texto original —
una redaccion ya personalizada no se toca.

Revision ID: 8c31f4a9d275
Revises: 1e0720c0b24b
Create Date: 2026-08-13

"""
from alembic import op
import sqlalchemy as sa


revision = '8c31f4a9d275'
down_revision = '1e0720c0b24b'
branch_labels = None
depends_on = None


NUEVAS = (
    {
        'nombre': 'Resumen diario al doctor',
        'tipo': 'resumen_doctor',
        'contenido': (
            'Hola {nombre_doctor}! Estas son tus citas de manana {fecha}:\n'
            '{listado}\n'
            'Buen dia! La Casa del Sr. Perez'
        ),
    },
    {
        'nombre': 'Cita reagendada',
        'tipo': 'cita_reagendada',
        'contenido': (
            'Hola {nombre_paciente}, le escribimos de La Casa del Sr. Perez.\n'
            'Su cita fue reagendada para el {fecha} a las {hora} con {doctor}.\n'
            'Si la nueva fecha no le funciona, responda a este mensaje y la ajustamos.'
        ),
    },
)

# (tipo, texto anterior, texto que se registro en Twilio)
SINCRONIZAR = (
    (
        'recordatorio_cita_hoy',
        'No olvides tu cita hoy a las {hora} para {nombre_paciente} con {nombre_doctor}.',
        'Le recordamos la cita de hoy a las {hora} para {nombre_paciente} con {nombre_doctor}.\n'
        'Le esperamos en La Casa del Sr. Perez.',
    ),
    (
        'postconsulta',
        'Hola Sra/Sr buenas tardes :) Como esta? Le comparto la foto (DIPLOMA Y PIN) '
        'de {nombre_paciente}, nos encantaria conocer su experiencia con nosotros '
        'le mandare un link {google_reviews_link} y solo debe dar clic, muchas gracias :)',
        'Hola Sra/Sr buenas tardes :) Como esta? Le comparto la foto (DIPLOMA Y PIN) '
        'de {nombre_paciente}, nos encantaria conocer su experiencia con nosotros, '
        'le mandare un link {google_reviews_link} y solo debe dar clic, muchas gracias :)',
    ),
)


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table('plantillas_mensaje'):
        return

    for plantilla in NUEVAS:
        op.execute(sa.text("""
            INSERT INTO plantillas_mensaje (nombre, tipo, contenido, activo)
            SELECT :nombre, :tipo, :contenido, :activo
            WHERE NOT EXISTS (
                SELECT 1 FROM plantillas_mensaje WHERE tipo = :tipo
            )
        """).bindparams(activo=True, **plantilla))

    for tipo, anterior, nuevo in SINCRONIZAR:
        op.execute(sa.text("""
            UPDATE plantillas_mensaje
            SET contenido = :nuevo
            WHERE tipo = :tipo AND contenido = :anterior
        """).bindparams(tipo=tipo, anterior=anterior, nuevo=nuevo))


def downgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table('plantillas_mensaje'):
        return

    for tipo, anterior, nuevo in SINCRONIZAR:
        op.execute(sa.text("""
            UPDATE plantillas_mensaje
            SET contenido = :anterior
            WHERE tipo = :tipo AND contenido = :nuevo
        """).bindparams(tipo=tipo, anterior=anterior, nuevo=nuevo))

    for plantilla in NUEVAS:
        op.execute(sa.text(
            'DELETE FROM plantillas_mensaje WHERE tipo = :tipo'
        ).bindparams(tipo=plantilla['tipo']))
