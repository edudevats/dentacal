"""add grupo_familiar model remove whatsapp unique

Revision ID: 09f4a9e1e21f
Revises: 375e3c99aa1a
Create Date: 2026-03-13 20:57:52.476226

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '09f4a9e1e21f'
down_revision = '375e3c99aa1a'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Crear tabla grupos_familiares (IF NOT EXISTS para compatibilidad con db.create_all)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'grupos_familiares' not in inspector.get_table_names():
        op.create_table('grupos_familiares',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('nombre', sa.String(200), nullable=False),
            sa.Column('telefono_principal', sa.String(20)),
            sa.Column('notas', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
        )
        op.create_index('ix_grupos_familiares_telefono', 'grupos_familiares', ['telefono_principal'])

    # 2. Agregar grupo_familiar_id + quitar unique de whatsapp (batch para SQLite)
    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('grupo_familiar_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_pacientes_whatsapp'), ['whatsapp'], unique=False)
        batch_op.create_foreign_key('fk_pacientes_grupo_familiar', 'grupos_familiares', ['grupo_familiar_id'], ['id'])


def downgrade():
    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        batch_op.drop_constraint('fk_pacientes_grupo_familiar', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_pacientes_whatsapp'))
        batch_op.drop_column('grupo_familiar_id')

    op.drop_index('ix_grupos_familiares_telefono', 'grupos_familiares')
    op.drop_table('grupos_familiares')
