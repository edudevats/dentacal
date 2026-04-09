"""add solicitudes_registro

Revision ID: 514ed7ae6a1a
Revises: b3b53225ebe2
Create Date: 2026-04-07 22:58:13.419649

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '514ed7ae6a1a'
down_revision = 'b3b53225ebe2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'solicitudes_registro',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('numero_whatsapp', sa.String(length=20), nullable=False),
        sa.Column('fecha_preferida', sa.String(length=100), nullable=True),
        sa.Column('hora_preferida', sa.String(length=20), nullable=True),
        sa.Column('notas', sa.Text(), nullable=True),
        sa.Column('atendida', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('solicitudes_registro')
