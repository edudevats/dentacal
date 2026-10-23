"""cita confirmacion_reset_at

Hora local (naive) del ultimo cambio de fecha de la cita: los intentos de
confirmacion y los reintentos creados antes no cuentan para la fecha nueva.
Nullable y sin backfill: NULL = la cita nunca se movio (comportamiento previo).

Revision ID: 9518d1735c09
Revises: 495e3b54cf47
Create Date: 2026-10-23 01:47:22.343146

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9518d1735c09'
down_revision = '495e3b54cf47'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('citas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('confirmacion_reset_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('citas', schema=None) as batch_op:
        batch_op.drop_column('confirmacion_reset_at')
