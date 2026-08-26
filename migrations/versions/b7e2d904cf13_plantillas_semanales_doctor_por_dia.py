"""las plantillas semanales del doctor mandan un dia por variable

Twilio rechazaba estos envios con el error 21656 ("The Content Variables
parameter is invalid"): Meta no admite saltos de linea dentro del valor de una
variable de plantilla, y el listado completo viajaba en {{3}}.

La solucion es mover los saltos de linea al CUERPO de la plantilla, que si los
admite: cada dia de la semana viaja en su propia variable ({{3}} a {{9}}) y las
citas de un mismo dia van en un renglon separadas por " · ".

Eso cambia la cantidad de variables de 3 a 9, asi que los ContentSid que ya
estaban pegados quedaron invalidos: apuntan a plantillas de Twilio de 3
variables y seguirian dando 21656. Se limpian aqui para que el mensaje salga
como texto libre (que al menos llega dentro de la ventana de 24 h) hasta que se
registren las nuevas en Twilio y se peguen los ContentSid nuevos. El
procedimiento esta en PLANTILLAS_WHATSAPP.txt, bloques 10 y 12.

Las otras dos plantillas de doctores (resumen_doctor y resumen_doctor_dia)
siguen con 3 variables y su ContentSid sigue siendo valido: solo cambio el
valor del listado, que ahora va en un solo renglon.

Revision ID: b7e2d904cf13
Revises: a1c73f5b8e42
Create Date: 2026-08-26

"""
from alembic import op
import sqlalchemy as sa


revision = 'b7e2d904cf13'
down_revision = 'a1c73f5b8e42'
branch_labels = None
depends_on = None


_DIAS = '\n'.join(f'- {{dia_{i}}}' for i in range(1, 8))

# Cuerpo nuevo de cada plantilla. Tiene que decir exactamente lo mismo que el
# texto de respaldo de services/doctor_envios.py — tests/test_envios_manuales
# _doctor.py lo verifica.
CUERPOS = {
    'horario_doctor': (
        'Hola {nombre_doctor}! Este es tu horario del {rango}:\n'
        f'{_DIAS}\n'
        'Si algo no coincide avisanos. La Casa del Sr. Perez'
    ),
    # El cuerpo tiene que decir algo distinto al del resumen diario: Meta
    # rechaza dos plantillas con el mismo texto en el mismo idioma.
    'resumen_semanal_doctor': (
        'Hola {nombre_doctor}! Estas son tus citas de la semana del {rango}:\n'
        f'{_DIAS}\n'
        'La Casa del Sr. Perez'
    ),
}

# Lo que decian antes, para poder volver atras.
CUERPOS_PREVIOS = {
    'horario_doctor': (
        'Hola {nombre_doctor}! Este es tu horario del {rango}:\n'
        '{listado}\n'
        'Si algo no coincide avisanos. La Casa del Sr. Perez'
    ),
    'resumen_semanal_doctor': (
        'Hola {nombre_doctor}! Estas son tus citas de la semana del {rango}:\n'
        '{listado}\n'
        'La Casa del Sr. Perez'
    ),
}


def _reescribir(cuerpos, limpiar_content_sid):
    bind = op.get_bind()
    if not sa.inspect(bind).has_table('plantillas_mensaje'):
        return

    for tipo, contenido in cuerpos.items():
        if limpiar_content_sid:
            op.execute(sa.text("""
                UPDATE plantillas_mensaje
                   SET contenido = :contenido,
                       content_sid = NULL,
                       content_variables_orden = NULL
                 WHERE tipo = :tipo
            """).bindparams(tipo=tipo, contenido=contenido))
        else:
            op.execute(sa.text("""
                UPDATE plantillas_mensaje
                   SET contenido = :contenido
                 WHERE tipo = :tipo
            """).bindparams(tipo=tipo, contenido=contenido))


def upgrade():
    _reescribir(CUERPOS, limpiar_content_sid=True)


def downgrade():
    # El ContentSid viejo no se restaura: se perdio al subir, y de todos modos
    # apuntaba a una plantilla de Twilio que ya no coincide.
    _reescribir(CUERPOS_PREVIOS, limpiar_content_sid=False)
