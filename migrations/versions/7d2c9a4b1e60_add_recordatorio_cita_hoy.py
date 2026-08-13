"""add recordatorio cita hoy

Revision ID: 7d2c9a4b1e60
Revises: 2a5e9d8c4f10
Create Date: 2026-08-13

"""
from alembic import op
import sqlalchemy as sa


revision = '7d2c9a4b1e60'
down_revision = '2a5e9d8c4f10'
branch_labels = None
depends_on = None


TIPOS_ANTERIORES = (
    'confirmacion_24h', 'seguimiento_crm', 'cumpleanos', 'postconsulta',
    'sonrisas_magicas', 'confirmacion_mismo_dia', 'proxima_visita',
    'no_asistencia', 'resumen_doctor', 'campana', 'manual',
    'confirmacion_anticipo', 'otro',
)
TIPOS_NUEVOS = TIPOS_ANTERIORES + ('recordatorio_cita_hoy',)


def _tipo_recordatorio(valores):
    return sa.Enum(*valores, name='tiporecordatorio')


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'mysql':
        op.alter_column(
            'mensajes_enviados', 'tipo',
            existing_type=_tipo_recordatorio(TIPOS_ANTERIORES),
            type_=_tipo_recordatorio(TIPOS_NUEVOS),
            existing_nullable=False,
        )

    if sa.inspect(bind).has_table('plantillas_mensaje'):
        op.execute(sa.text("""
            INSERT INTO plantillas_mensaje (nombre, tipo, contenido, activo)
            SELECT :nombre, :tipo, :contenido, :activo
            WHERE NOT EXISTS (
                SELECT 1 FROM plantillas_mensaje WHERE tipo = :tipo
            )
        """).bindparams(
            nombre='Recordatorio de cita hoy',
            tipo='recordatorio_cita_hoy',
            contenido=(
                'No olvides tu cita hoy a las {hora} para '
                '{nombre_paciente} con {nombre_doctor}.'
            ),
            activo=True,
        ))


def downgrade():
    bind = op.get_bind()
    if sa.inspect(bind).has_table('plantillas_mensaje'):
        op.execute(sa.text(
            "DELETE FROM plantillas_mensaje "
            "WHERE tipo = 'recordatorio_cita_hoy'"
        ))

    if bind.dialect.name == 'mysql':
        op.execute(sa.text(
            "DELETE FROM mensajes_enviados "
            "WHERE tipo = 'recordatorio_cita_hoy'"
        ))
        op.alter_column(
            'mensajes_enviados', 'tipo',
            existing_type=_tipo_recordatorio(TIPOS_NUEVOS),
            type_=_tipo_recordatorio(TIPOS_ANTERIORES),
            existing_nullable=False,
        )
