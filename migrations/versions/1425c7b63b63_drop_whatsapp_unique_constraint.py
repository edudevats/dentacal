"""drop whatsapp unique constraint

Revision ID: 1425c7b63b63
Revises: 09f4a9e1e21f
Create Date: 2026-03-14 15:57:52.057037

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1425c7b63b63'
down_revision = '09f4a9e1e21f'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite tiene UNIQUE (whatsapp) sin nombre — hay que reconstruir la tabla
    # manualmente para eliminarlo, ya que batch_alter_table no puede dropear
    # constraints anonimas de forma confiable.
    conn = op.get_bind()

    # 1. Crear tabla temporal sin la constraint UNIQUE
    conn.execute(sa.text("""
        CREATE TABLE pacientes_new (
            id INTEGER NOT NULL PRIMARY KEY,
            nombre VARCHAR(100) NOT NULL,
            fecha_nacimiento DATE,
            telefono VARCHAR(20),
            whatsapp VARCHAR(20),
            email VARCHAR(120),
            nombre_tutor VARCHAR(200),
            telefono_tutor VARCHAR(20),
            escuela VARCHAR(200),
            notas TEXT,
            estatus_crm VARCHAR(9),
            fecha_alta DATETIME,
            ultima_cita DATETIME,
            eliminado BOOLEAN,
            created_at DATETIME,
            doctor_id INTEGER,
            tutor_id INTEGER,
            es_problematico BOOLEAN,
            proximo_recordatorio_fecha DATE,
            grupo_familiar_id INTEGER,
            CONSTRAINT fk_paciente_doctor_id FOREIGN KEY(doctor_id) REFERENCES dentistas (id),
            CONSTRAINT fk_pacientes_grupo_familiar FOREIGN KEY(grupo_familiar_id) REFERENCES grupos_familiares (id)
        )
    """))

    # 2. Copiar datos
    conn.execute(sa.text("""
        INSERT INTO pacientes_new SELECT * FROM pacientes
    """))

    # 3. Borrar tabla vieja y renombrar
    conn.execute(sa.text("DROP TABLE pacientes"))
    conn.execute(sa.text("ALTER TABLE pacientes_new RENAME TO pacientes"))

    # 4. Recrear indices
    conn.execute(sa.text("CREATE INDEX ix_pacientes_whatsapp ON pacientes (whatsapp)"))


def downgrade():
    with op.batch_alter_table('pacientes', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_pacientes_whatsapp', ['whatsapp'])
