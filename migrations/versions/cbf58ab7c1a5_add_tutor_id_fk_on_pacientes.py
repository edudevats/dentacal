"""add tutor_id FK on pacientes

Revision ID: cbf58ab7c1a5
Revises: bb32d3389144
Create Date: 2026-03-11 17:37:15.369837

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cbf58ab7c1a5'
down_revision = 'bb32d3389144'
branch_labels = None
depends_on = None


def upgrade():
    # Solo agregar columna tutor_id (sin FK constraint en SQLite)
    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tutor_id', sa.Integer(), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        batch_op.drop_column('tutor_id')
