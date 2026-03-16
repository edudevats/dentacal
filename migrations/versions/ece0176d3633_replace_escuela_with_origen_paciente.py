"""replace escuela with origen_paciente

Revision ID: ece0176d3633
Revises: 1425c7b63b63
Create Date: 2026-03-16 01:24:45.385831

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ece0176d3633'
down_revision = '1425c7b63b63'
branch_labels = None
depends_on = None


def upgrade():
    # Create origenes_paciente table if it doesn't exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if 'origenes_paciente' not in inspector.get_table_names():
        op.create_table('origenes_paciente',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('nombre', sa.String(length=100), nullable=False, unique=True),
            sa.Column('activo', sa.Boolean(), default=True),
            sa.Column('created_at', sa.DateTime()),
        )

    # Add origen_paciente_id and remove escuela from pacientes
    columns = [c['name'] for c in inspector.get_columns('pacientes')]
    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        if 'origen_paciente_id' not in columns:
            batch_op.add_column(sa.Column('origen_paciente_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_pacientes_origen', 'origenes_paciente', ['origen_paciente_id'], ['id'])
        if 'escuela' in columns:
            batch_op.drop_column('escuela')


def downgrade():
    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('escuela', sa.VARCHAR(length=200), nullable=True))
        batch_op.drop_constraint('fk_pacientes_origen', type_='foreignkey')
        batch_op.drop_column('origen_paciente_id')

    op.drop_table('origenes_paciente')
