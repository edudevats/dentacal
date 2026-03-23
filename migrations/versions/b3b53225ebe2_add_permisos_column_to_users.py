"""add permisos column to users

Revision ID: b3b53225ebe2
Revises: 915f0786f82f
Create Date: 2026-03-23 00:36:16.737643

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3b53225ebe2'
down_revision = '915f0786f82f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('permisos', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('permisos')
