"""campana destinatario message_sid delivery_status

Revision ID: 8ca96506b1ab
Revises: 514ed7ae6a1a
Create Date: 2026-04-10 14:01:25.351390

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8ca96506b1ab'
down_revision = '514ed7ae6a1a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('campana_destinatarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('message_sid', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('delivery_status', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('delivery_updated_at', sa.DateTime(), nullable=True))
        batch_op.create_index(batch_op.f('ix_campana_destinatarios_message_sid'), ['message_sid'], unique=False)


def downgrade():
    with op.batch_alter_table('campana_destinatarios', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_campana_destinatarios_message_sid'))
        batch_op.drop_column('delivery_updated_at')
        batch_op.drop_column('delivery_status')
        batch_op.drop_column('message_sid')
