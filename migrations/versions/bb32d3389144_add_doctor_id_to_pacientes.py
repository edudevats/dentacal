"""add_doctor_id_to_pacientes

Revision ID: bb32d3389144
Revises: 
Create Date: 2026-03-10 10:37:41.962496

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bb32d3389144'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('doctor_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_paciente_doctor_id', 'dentistas', ['doctor_id'], ['id'])


def downgrade():
    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        batch_op.drop_constraint('fk_paciente_doctor_id', type_='foreignkey')
        batch_op.drop_column('doctor_id')
