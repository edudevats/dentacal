"""content_sid para plantillas aprobadas de WhatsApp

WhatsApp solo entrega texto libre dentro de la ventana de 24 h que abre el
paciente al escribir. Fuera de ella hace falta una plantilla aprobada por Meta,
identificada por su ContentSid. La bitacora guarda con que se envio cada
mensaje para que un reintento lo reproduzca igual.

Revision ID: 1e0720c0b24b
Revises: 596106e9a8b6
Create Date: 2026-08-13 10:46:31.958250

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '1e0720c0b24b'
down_revision = '596106e9a8b6'
branch_labels = None
depends_on = None


# Igual que en la revision anterior, se omite el rewrite del ENUM 'tipo' que
# propone el autogenerador: mismos valores en distinto orden.


def upgrade():
    with op.batch_alter_table('mensajes_enviados', schema=None) as batch_op:
        batch_op.add_column(sa.Column('content_sid', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('content_variables', sa.Text(), nullable=True))

    with op.batch_alter_table('plantillas_mensaje', schema=None) as batch_op:
        batch_op.add_column(sa.Column('content_sid', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('content_variables_orden', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('plantillas_mensaje', schema=None) as batch_op:
        batch_op.drop_column('content_variables_orden')
        batch_op.drop_column('content_sid')

    with op.batch_alter_table('mensajes_enviados', schema=None) as batch_op:
        batch_op.drop_column('content_variables')
        batch_op.drop_column('content_sid')
