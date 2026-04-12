"""add pre_cita status and expira field

Revision ID: b3a7700a0acc
Revises: 8ca96506b1ab
Create Date: 2026-04-12 15:25:03.559846

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3a7700a0acc'
down_revision = '8ca96506b1ab'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('citas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pre_cita_expira', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('citas', schema=None) as batch_op:
        batch_op.drop_column('pre_cita_expira')
