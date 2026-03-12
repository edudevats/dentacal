"""add es_problematico to paciente

Revision ID: 16d910afd5e2
Revises: 8776800ae46e
Create Date: 2026-03-11 23:08:09.147033

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '16d910afd5e2'
down_revision = '8776800ae46e'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('es_problematico', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        batch_op.drop_column('es_problematico')
