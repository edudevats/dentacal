"""retire recordatorios table into mensajes_enviados

Revision ID: 4448e15287da
Revises: c9065cbec233
Create Date: 2026-08-02 11:46:51.677744

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4448e15287da'
down_revision = 'c9065cbec233'
branch_labels = None
depends_on = None


def upgrade():
    # Copia el historial de recordatorios a la bitacora unificada.
    # numero_destino y mensaje van vacios porque la tabla vieja nunca los guardo:
    # estas filas son historicas y no se pueden reenviar. proximo_intento queda
    # NULL, que es justo lo que el job de reenvio usa para ignorarlas.
    op.execute("""
        INSERT INTO mensajes_enviados
            (tipo, numero_destino, mensaje, cita_id, estatus,
             intentos, proximo_intento, fecha_creacion, fecha_envio)
        SELECT tipo, '', '', cita_id, status,
               0, NULL, fecha_envio, fecha_envio
        FROM recordatorios
    """)
    op.drop_table('recordatorios')


def downgrade():
    op.create_table(
        'recordatorios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cita_id', sa.Integer(), nullable=False),
        sa.Column(
            'tipo',
            sa.Enum(
                'confirmacion_24h', 'seguimiento_crm', 'cumpleanos',
                'postconsulta', 'sonrisas_magicas',
                'confirmacion_mismo_dia', 'proxima_visita',
                'no_asistencia', 'resumen_doctor', 'campana', 'manual',
                'confirmacion_anticipo', 'otro',
                name='tiporecordatorio',
            ),
            nullable=False,
        ),
        sa.Column('mensaje_enviado', sa.Text(), nullable=True),
        sa.Column('fecha_envio', sa.DateTime(), nullable=True),
        sa.Column(
            'status',
            sa.Enum(
                'pendiente', 'enviado', 'fallido', 'fallido_definitivo',
                'caducado', name='estatusrecordatorio',
            ),
            nullable=True,
        ),
        sa.Column('error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['cita_id'], ['citas.id']),
        sa.PrimaryKeyConstraint('id'),
    )
