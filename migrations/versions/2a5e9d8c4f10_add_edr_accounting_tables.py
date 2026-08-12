"""add EDR accounting tables

Revision ID: 2a5e9d8c4f10
Revises: 1bce4cb456c7
Create Date: 2026-08-09

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2a5e9d8c4f10'
down_revision = '1bce4cb456c7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'metodos_pago',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nombre'),
    )
    op.create_table(
        'gastos_conceptos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('tipo_default', sa.String(length=20), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "tipo_default IN ('fijo', 'variable')",
            name='ck_gasto_concepto_tipo',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('nombre'),
    )
    op.create_table(
        'ingresos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('cita_id', sa.Integer(), nullable=True),
        sa.Column('paciente_id', sa.Integer(), nullable=True),
        sa.Column('dentista_id', sa.Integer(), nullable=True),
        sa.Column('tipo_cita_id', sa.Integer(), nullable=True),
        sa.Column('metodo_pago_id', sa.Integer(), nullable=False),
        sa.Column('paciente_nombre', sa.String(length=200), nullable=False),
        sa.Column('nombre_tratamiento', sa.String(length=200), nullable=False),
        sa.Column('monto', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            'comision_bancaria',
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column(
            'comision_doctor',
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column(
            'descuento_pct',
            sa.Numeric(precision=5, scale=2),
            nullable=False,
        ),
        sa.Column('factura', sa.Boolean(), nullable=False),
        sa.Column('tipo_servicio', sa.String(length=20), nullable=False),
        sa.Column('comentarios', sa.Text(), nullable=True),
        sa.Column('anulado', sa.Boolean(), nullable=False),
        sa.Column('anulado_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('anulado_por_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "tipo_servicio IN ('clinico', 'estetico')",
            name='ck_ingreso_tipo_servicio',
        ),
        sa.ForeignKeyConstraint(['anulado_por_id'], ['users.id']),
        sa.ForeignKeyConstraint(['cita_id'], ['citas.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['dentista_id'], ['dentistas.id']),
        sa.ForeignKeyConstraint(['metodo_pago_id'], ['metodos_pago.id']),
        sa.ForeignKeyConstraint(['paciente_id'], ['pacientes.id']),
        sa.ForeignKeyConstraint(['tipo_cita_id'], ['tipos_cita.id']),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'gastos_operativos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('concepto_id', sa.Integer(), nullable=True),
        sa.Column('concepto_nombre', sa.String(length=200), nullable=False),
        sa.Column('tipo', sa.String(length=20), nullable=False),
        sa.Column('monto', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('comentarios', sa.Text(), nullable=True),
        sa.Column('anulado', sa.Boolean(), nullable=False),
        sa.Column('anulado_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('anulado_por_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.CheckConstraint("tipo IN ('fijo', 'variable')", name='ck_gasto_tipo'),
        sa.ForeignKeyConstraint(['anulado_por_id'], ['users.id']),
        sa.ForeignKeyConstraint(['concepto_id'], ['gastos_conceptos.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'pagos_doctores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('dentista_id', sa.Integer(), nullable=False),
        sa.Column('concepto', sa.String(length=200), nullable=False),
        sa.Column('tipo', sa.String(length=20), nullable=False),
        sa.Column('monto', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            'descuento_saldo',
            sa.Numeric(precision=12, scale=2),
            nullable=False,
        ),
        sa.Column('anulado', sa.Boolean(), nullable=False),
        sa.Column('anulado_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('anulado_por_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "tipo IN ('comision', 'salario', 'otro')",
            name='ck_pago_doctor_tipo',
        ),
        sa.ForeignKeyConstraint(['anulado_por_id'], ['users.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['dentista_id'], ['dentistas.id']),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'pago_comision_ingreso',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pago_id', sa.Integer(), nullable=False),
        sa.Column('ingreso_id', sa.Integer(), nullable=False),
        sa.Column('monto', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ingreso_id'], ['ingresos.id']),
        sa.ForeignKeyConstraint(['pago_id'], ['pagos_doctores.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ingreso_id', name='uq_pago_comision_ingreso'),
    )
    op.create_index(
        'ix_ingresos_anulado',
        'ingresos',
        ['anulado'],
        unique=False,
    )
    op.create_index(
        'ix_gastos_operativos_anulado',
        'gastos_operativos',
        ['anulado'],
        unique=False,
    )
    op.create_index(
        'ix_pagos_doctores_anulado',
        'pagos_doctores',
        ['anulado'],
        unique=False,
    )
    op.create_index(
        'ix_ingresos_fecha_anulado',
        'ingresos',
        ['fecha', 'anulado'],
        unique=False,
    )
    op.create_index(
        'ix_gastos_fecha_anulado',
        'gastos_operativos',
        ['fecha', 'anulado'],
        unique=False,
    )
    op.create_index(
        'ix_pagos_doctores_fecha_anulado',
        'pagos_doctores',
        ['fecha', 'anulado'],
        unique=False,
    )


def downgrade():
    op.drop_table('pago_comision_ingreso')
    op.drop_table('pagos_doctores')
    op.drop_table('gastos_operativos')
    op.drop_table('ingresos')
    op.drop_table('gastos_conceptos')
    op.drop_table('metodos_pago')
