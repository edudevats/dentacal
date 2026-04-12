"""add atiende_ninos atiende_adultos to dentistas

Revision ID: f241f920f95e
Revises: b3a7700a0acc
Create Date: 2026-04-12 15:55:47.433972

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f241f920f95e'
down_revision = 'b3a7700a0acc'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('dentistas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('atiende_ninos', sa.Boolean(), nullable=True, server_default=sa.text('1')))
        batch_op.add_column(sa.Column('atiende_adultos', sa.Boolean(), nullable=True, server_default=sa.text('1')))


def downgrade():
    with op.batch_alter_table('dentistas', schema=None) as batch_op:
        batch_op.drop_column('atiende_adultos')
        batch_op.drop_column('atiende_ninos')
