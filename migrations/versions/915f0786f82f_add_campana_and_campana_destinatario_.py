"""add campana and campana_destinatario models

Revision ID: 915f0786f82f
Revises: ece0176d3633
Create Date: 2026-03-16 22:51:19.207289

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '915f0786f82f'
down_revision = 'ece0176d3633'
branch_labels = None
depends_on = None


def upgrade():
    # Crear tabla campanas si no existe
    op.create_table('campanas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=200), nullable=False),
        sa.Column('mensaje', sa.Text(), nullable=False),
        sa.Column('filtros', sa.Text(), nullable=True),
        sa.Column('estatus', sa.Enum('borrador', 'programada', 'enviando', 'completada', 'cancelada', name='estatuscampana'), nullable=True),
        sa.Column('fecha_programada', sa.DateTime(), nullable=True),
        sa.Column('fecha_envio_inicio', sa.DateTime(), nullable=True),
        sa.Column('fecha_envio_fin', sa.DateTime(), nullable=True),
        sa.Column('total_destinatarios', sa.Integer(), nullable=True),
        sa.Column('enviados', sa.Integer(), nullable=True),
        sa.Column('fallidos', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Crear tabla campana_destinatarios si no existe
    op.create_table('campana_destinatarios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('campana_id', sa.Integer(), nullable=False),
        sa.Column('paciente_id', sa.Integer(), nullable=False),
        sa.Column('numero_destino', sa.String(length=20), nullable=True),
        sa.Column('estatus', sa.Enum('pendiente', 'enviado', 'fallido', name='estatusdestinatario'), nullable=True),
        sa.Column('error_mensaje', sa.Text(), nullable=True),
        sa.Column('fecha_envio', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['campana_id'], ['campanas.id'], ),
        sa.ForeignKeyConstraint(['paciente_id'], ['pacientes.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('campana_id', 'paciente_id', name='uq_campana_paciente')
    )


def downgrade():
    op.drop_table('campana_destinatarios')
    op.drop_table('campanas')
