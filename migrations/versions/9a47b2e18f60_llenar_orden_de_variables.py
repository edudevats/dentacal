"""llenar orden de variables de las plantillas

Recepcion solo tiene que pegar el ContentSid. El orden de las variables lo
sabe la app, asi que se deja precargado en cada plantilla en vez de pedirselo
al usuario: escribirlo mal no da error, manda el nombre donde va la hora.

Solo llena las que estan vacias — un orden ya ajustado a mano no se toca.

Revision ID: 9a47b2e18f60
Revises: 8c31f4a9d275
Create Date: 2026-08-13

"""
from alembic import op
import sqlalchemy as sa


revision = '9a47b2e18f60'
down_revision = '8c31f4a9d275'
branch_labels = None
depends_on = None


# Copia literal de ORDEN_VARIABLES_POR_TIPO en services/whatsapp_service.py.
# Se duplica a proposito: una migracion tiene que seguir corriendo igual
# aunque el codigo de la app cambie despues.
ORDEN_POR_TIPO = {
    'recordatorio_24h': 'nombre_paciente,hora',
    'confirmacion_mismo_dia': 'nombre_paciente,hora,dentista',
    'recordatorio_cita_hoy': 'hora,nombre_paciente,nombre_doctor',
    'postconsulta': 'nombre_paciente,google_reviews_link',
    'proxima_visita': 'nombre_tutor,nombre_paciente',
    'no_asistencia_reagendar': 'nombre_paciente,fecha',
    'cumpleanos': 'nombre_tutor,nombre_paciente',
    'resumen_doctor': 'nombre_doctor,fecha,listado',
    'cita_reagendada': 'nombre_paciente,fecha,hora,doctor',
}


def upgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table('plantillas_mensaje'):
        return

    for tipo, orden in ORDEN_POR_TIPO.items():
        op.execute(sa.text("""
            UPDATE plantillas_mensaje
            SET content_variables_orden = :orden
            WHERE tipo = :tipo
              AND (content_variables_orden IS NULL
                   OR content_variables_orden = '')
        """).bindparams(tipo=tipo, orden=orden))


def downgrade():
    bind = op.get_bind()
    if not sa.inspect(bind).has_table('plantillas_mensaje'):
        return

    for tipo, orden in ORDEN_POR_TIPO.items():
        op.execute(sa.text("""
            UPDATE plantillas_mensaje
            SET content_variables_orden = NULL
            WHERE tipo = :tipo AND content_variables_orden = :orden
        """).bindparams(tipo=tipo, orden=orden))
