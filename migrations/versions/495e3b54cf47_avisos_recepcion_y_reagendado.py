"""avisos recepcion y reagendado

Revision ID: 495e3b54cf47
Revises: b7e2d904cf13
Create Date: 2026-10-23 01:00:51.863965

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '495e3b54cf47'
down_revision = 'b7e2d904cf13'
branch_labels = None
depends_on = None


REC_ANTERIORES = (
    'confirmacion_24h', 'seguimiento_crm', 'cumpleanos', 'postconsulta',
    'sonrisas_magicas', 'confirmacion_mismo_dia', 'recordatorio_cita_hoy',
    'proxima_visita', 'no_asistencia', 'resumen_doctor', 'campana', 'manual',
    'confirmacion_anticipo', 'otro',
)
REC_NUEVOS = REC_ANTERIORES + ('reagendado_mismo_dia',)

SEG_ANTERIORES = (
    'confirmacion_cita', 'recordatorio_cita', 'post_consulta', 'reactivacion',
    'presupuesto', 'tratamiento_pendiente', 'limpieza_control',
    'anticipo_pendiente', 'resena', 'cumpleanos', 'whatsapp_1', 'whatsapp_2',
    'llamada',
)
SEG_NUEVOS = SEG_ANTERIORES + ('comentario_bot',)


def _rec(valores):
    return sa.Enum(*valores, name='tiporecordatorio')


def _seg(valores):
    return sa.Enum(*valores, name='tiposeguimiento')


def upgrade():
    op.create_table('avisos_recepcion',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('cita_id', sa.Integer(), nullable=True),
    sa.Column('paciente_id', sa.Integer(), nullable=True),
    sa.Column('detalle', sa.Text(), nullable=True),
    sa.Column('origen', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('leido', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['cita_id'], ['citas.id'], ),
    sa.ForeignKeyConstraint(['paciente_id'], ['pacientes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('avisos_recepcion', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_avisos_recepcion_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_avisos_recepcion_tipo'), ['tipo'], unique=False)

    with op.batch_alter_table('citas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('aviso_asistencia', sa.String(length=20), nullable=True))


    bind = op.get_bind()
    if bind.dialect.name == 'mysql':
        op.alter_column('mensajes_enviados', 'tipo',
                        existing_type=_rec(REC_ANTERIORES),
                        type_=_rec(REC_NUEVOS), existing_nullable=False)
        op.alter_column('seguimientos_crm', 'tipo',
                        existing_type=_seg(SEG_ANTERIORES),
                        type_=_seg(SEG_NUEVOS), existing_nullable=False)

    if sa.inspect(bind).has_table('plantillas_mensaje'):
        op.execute(sa.text("""
            INSERT INTO plantillas_mensaje (nombre, tipo, contenido, activo)
            SELECT :nombre, :tipo, :contenido, :activo
            WHERE NOT EXISTS (
                SELECT 1 FROM plantillas_mensaje WHERE tipo = :tipo
            )
        """).bindparams(
            nombre='Reagendar cita sin confirmar',
            tipo='reagendado_mismo_dia',
            contenido=(
                'Hola, no recibimos la confirmación de la cita de '
                '{nombre_paciente} hoy a las {hora} con {dentista}. Si no '
                'podrá asistir, respóndanos este mensaje y con gusto le '
                'buscamos otro día.'
            ),
            activo=True,
        ))


def downgrade():
    bind = op.get_bind()
    if sa.inspect(bind).has_table('plantillas_mensaje'):
        op.execute(sa.text(
            "DELETE FROM plantillas_mensaje "
            "WHERE tipo = 'reagendado_mismo_dia'"))

    if bind.dialect.name == 'mysql':
        op.execute(sa.text(
            "DELETE FROM mensajes_enviados "
            "WHERE tipo = 'reagendado_mismo_dia'"))
        op.execute(sa.text(
            "DELETE FROM seguimientos_crm WHERE tipo = 'comentario_bot'"))
        op.alter_column('seguimientos_crm', 'tipo',
                        existing_type=_seg(SEG_NUEVOS),
                        type_=_seg(SEG_ANTERIORES), existing_nullable=False)
        op.alter_column('mensajes_enviados', 'tipo',
                        existing_type=_rec(REC_NUEVOS),
                        type_=_rec(REC_ANTERIORES), existing_nullable=False)

    with op.batch_alter_table('citas', schema=None) as batch_op:
        batch_op.drop_column('aviso_asistencia')

    with op.batch_alter_table('avisos_recepcion', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_avisos_recepcion_tipo'))
        batch_op.drop_index(batch_op.f('ix_avisos_recepcion_created_at'))

    op.drop_table('avisos_recepcion')

