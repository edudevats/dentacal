"""plantillas de los envios manuales a doctores

El horario de la semana, el resumen del dia y el resumen semanal se mandan a
demanda desde Configuracion -> Doctores. Cada uno necesita su propia fila en
plantillas_mensaje: sin fila no hay donde pegar el ContentSid de la plantilla
aprobada de WhatsApp y el mensaje sale siempre como texto libre, que fuera de
la ventana de 24 h choca con el error 63016.

No se reusa la plantilla 'resumen_doctor' porque su texto dice "tus citas de
manana", que no aplica a ninguno de los tres.

Revision ID: a1c73f5b8e42
Revises: 9a47b2e18f60
Create Date: 2026-08-14

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1c73f5b8e42'
down_revision = '9a47b2e18f60'
branch_labels = None
depends_on = None


NUEVAS = (
    {
        'nombre': 'Horario semanal al doctor',
        'tipo': 'horario_doctor',
        'contenido': (
            'Hola {nombre_doctor}! Este es tu horario del {rango}:\n'
            '{listado}\n'
            'Si algo no coincide avisanos. La Casa del Sr. Perez'
        ),
    },
    {
        'nombre': 'Resumen de citas del dia al doctor',
        'tipo': 'resumen_doctor_dia',
        'contenido': (
            'Hola {nombre_doctor}! Estas son tus citas del {fecha}:\n'
            '{listado}\n'
            'La Casa del Sr. Perez'
        ),
    },
    {
        'nombre': 'Resumen semanal de citas al doctor',
        'tipo': 'resumen_semanal_doctor',
        # El cuerpo tiene que decir algo distinto al del resumen diario: Meta
        # rechaza dos plantillas con el mismo texto en el mismo idioma.
        'contenido': (
            'Hola {nombre_doctor}! Estas son tus citas de la semana del {rango}:\n'
            '{listado}\n'
            'La Casa del Sr. Perez'
        ),
    },
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


def downgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table('plantillas_mensaje'):
        return

    for plantilla in NUEVAS:
        op.execute(sa.text(
            'DELETE FROM plantillas_mensaje WHERE tipo = :tipo'
        ).bindparams(tipo=plantilla['tipo']))
