"""delivery_status en mensajes_enviados

Separa "Twilio acepto el mensaje" de "WhatsApp lo entrego". El 201 de la API
solo prueba lo primero; el rechazo (por ejemplo 63016, mensaje libre fuera de
la ventana de 24 h) llega despues por el Status Callback.

Revision ID: 596106e9a8b6
Revises: 7d2c9a4b1e60
Create Date: 2026-08-13 10:38:36.669771

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '596106e9a8b6'
down_revision = '7d2c9a4b1e60'
branch_labels = None
depends_on = None


# El autogenerador tambien propuso reescribir el ENUM 'tipo': mismos valores en
# distinto orden. Se omite a proposito — no cambia nada y forzaria un rewrite
# completo de la tabla en produccion.


def upgrade():
    with op.batch_alter_table('mensajes_enviados', schema=None) as batch_op:
        batch_op.add_column(sa.Column('delivery_status', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('delivery_error_code', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('delivery_error_mensaje', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('delivery_updated_at', sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f('ix_mensajes_enviados_delivery_status'),
                              ['delivery_status'], unique=False)


def downgrade():
    with op.batch_alter_table('mensajes_enviados', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mensajes_enviados_delivery_status'))
        batch_op.drop_column('delivery_updated_at')
        batch_op.drop_column('delivery_error_mensaje')
        batch_op.drop_column('delivery_error_code')
        batch_op.drop_column('delivery_status')
