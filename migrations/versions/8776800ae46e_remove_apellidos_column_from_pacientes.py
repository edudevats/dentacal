"""remove apellidos column from pacientes

Revision ID: 8776800ae46e
Revises: cbf58ab7c1a5
Create Date: 2026-03-11 21:02:44.809166

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8776800ae46e'
down_revision = 'cbf58ab7c1a5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        batch_op.drop_column('apellidos')


def downgrade():
    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('apellidos', sa.VARCHAR(length=100), nullable=True))
