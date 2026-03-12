from datetime import datetime, date, time
from enum import Enum as PyEnum
from extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


# --- Enums ---

class RolUsuario(PyEnum):
    admin = 'admin'
    recepcionista = 'recepcionista'


class EstatusCita(PyEnum):
    pendiente = 'pendiente'
    confirmada = 'confirmada'
    no_asistencia = 'no_asistencia'
    cancelada = 'cancelada'


class EstatusCRM(PyEnum):
    alta = 'alta'
    activo = 'activo'
    prospecto = 'prospecto'
    baja = 'baja'


class TipoSeguimiento(PyEnum):
    whatsapp_1 = 'whatsapp_1'
    whatsapp_2 = 'whatsapp_2'
    llamada = 'llamada'


class TipoRecordatorio(PyEnum):
    confirmacion_24h = 'confirmacion_24h'
    seguimiento_crm = 'seguimiento_crm'
    cumpleanos = 'cumpleanos'
    postconsulta = 'postconsulta'
    sonrisas_magicas = 'sonrisas_magicas'


class EstatusRecordatorio(PyEnum):
    pendiente = 'pendiente'
    enviado = 'enviado'
    fallido = 'fallido'


# --- Modelos ---

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.Enum(RolUsuario), nullable=False, default=RolUsuario.recepcionista)
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_admin(self):
        return self.rol == RolUsuario.admin

    def __repr__(self):
        return f'<User {self.username}>'


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    accion = db.Column(db.String(100), nullable=False)
    tabla = db.Column(db.String(50))
    registro_id = db.Column(db.Integer)
    datos_anteriores = db.Column(db.Text)
    datos_nuevos = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='audit_logs')


class Dentista(db.Model):
    __tablename__ = 'dentistas'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    especialidad = db.Column(db.String(100))
    color = db.Column(db.String(7), default='#3788d8')  # Hex
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(120))
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    horarios = db.relationship('HorarioDentista', backref='dentista',
                               lazy=True, cascade='all, delete-orphan')
    bloqueos = db.relationship('BloqueoDentista', backref='dentista',
                               lazy=True, cascade='all, delete-orphan')
    citas = db.relationship('Cita', backref='dentista', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'especialidad': self.especialidad,
            'color': self.color,
            'telefono': self.telefono,
            'email': self.email,
            'activo': self.activo,
        }


class HorarioDentista(db.Model):
    """Horario semanal del dentista. dia_semana: 0=Lun, 6=Dom."""
    __tablename__ = 'horarios_dentista'

    id = db.Column(db.Integer, primary_key=True)
    dentista_id = db.Column(db.Integer, db.ForeignKey('dentistas.id'), nullable=False)
    dia_semana = db.Column(db.Integer, nullable=False)  # 0-6
    hora_inicio = db.Column(db.Time, nullable=False, default=time(9, 0))
    hora_fin = db.Column(db.Time, nullable=False, default=time(18, 0))
    activo = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint('dentista_id', 'dia_semana', name='uq_horario_dentista_dia'),
    )


class BloqueoDentista(db.Model):
    """Bloqueos de tiempo del dentista (vacaciones, permisos, etc.)."""
    __tablename__ = 'bloqueos_dentista'

    id = db.Column(db.Integer, primary_key=True)
    dentista_id = db.Column(db.Integer, db.ForeignKey('dentistas.id'), nullable=False)
    fecha_inicio = db.Column(db.DateTime, nullable=False)
    fecha_fin = db.Column(db.DateTime, nullable=False)
    motivo = db.Column(db.String(200))


class Consultorio(db.Model):
    __tablename__ = 'consultorios'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False, unique=True)
    descripcion = db.Column(db.String(200))
    activo = db.Column(db.Boolean, default=True)

    citas = db.relationship('Cita', backref='consultorio', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.nombre,
            'descripcion': self.descripcion,
        }


class TipoCita(db.Model):
    __tablename__ = 'tipos_cita'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    duracion_minutos = db.Column(db.Integer, default=60)
    precio = db.Column(db.Numeric(10, 2), default=0)
    descripcion = db.Column(db.String(200))
    color = db.Column(db.String(7), default='#3788d8')
    requiere_anticipo = db.Column(db.Boolean, default=False)
    activo = db.Column(db.Boolean, default=True)

    citas = db.relationship('Cita', backref='tipo_cita', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'duracion_minutos': self.duracion_minutos,
            'precio': float(self.precio),
            'requiere_anticipo': self.requiere_anticipo,
        }


class Paciente(db.Model):
    __tablename__ = 'pacientes'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    fecha_nacimiento = db.Column(db.Date)
    telefono = db.Column(db.String(20))
    whatsapp = db.Column(db.String(20), unique=True)
    email = db.Column(db.String(120))
    doctor_id = db.Column(db.Integer, db.ForeignKey('dentistas.id'), nullable=True)

    # Tutor (pacientes pediatricos)
    tutor_id = db.Column(db.Integer, db.ForeignKey('pacientes.id'), nullable=True)
    nombre_tutor = db.Column(db.String(200))
    telefono_tutor = db.Column(db.String(20))

    # Datos escolares (para justificantes)
    escuela = db.Column(db.String(200))

    notas = db.Column(db.Text)
    estatus_crm = db.Column(db.Enum(EstatusCRM), default=EstatusCRM.prospecto)
    fecha_alta = db.Column(db.DateTime, default=datetime.utcnow)
    ultima_cita = db.Column(db.DateTime)

    eliminado = db.Column(db.Boolean, default=False)  # soft delete
    es_problematico = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    citas = db.relationship('Cita', backref='paciente', lazy=True)
    doctor = db.relationship('Dentista', backref='pacientes_asignados')
    conversaciones = db.relationship('ConversacionWhatsapp', backref='paciente', lazy=True)
    seguimientos = db.relationship('SeguimientoCRM', backref='paciente',
                                   lazy=True, order_by='SeguimientoCRM.fecha_programada')
    justificantes = db.relationship('Justificante', backref='paciente', lazy=True)
    tutor = db.relationship('Paciente', remote_side='Paciente.id',
                            backref=db.backref('menores_a_cargo', lazy=True),
                            foreign_keys=[tutor_id])

    @property
    def nombre_completo(self):
        return self.nombre

    @property
    def mes_cumpleanos(self):
        if self.fecha_nacimiento:
            return self.fecha_nacimiento.month
        return None

    @property
    def es_menor_edad(self):
        """True si el paciente tiene menos de 18 anios."""
        if not self.fecha_nacimiento:
            return False
        hoy = date.today()
        edad = hoy.year - self.fecha_nacimiento.year - (
            (hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day)
        )
        return edad < 18

    @property
    def numero_contacto_wa(self):
        """Numero de WhatsApp de contacto. Para menores con tutor vinculado
        usa el WA del tutor; sino fallback a telefono_tutor y luego propio."""
        if self.tutor_id and self.tutor and self.tutor.whatsapp:
            return self.tutor.whatsapp
        return self.whatsapp or self.telefono_tutor or self.telefono

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'nombre_completo': self.nombre_completo,
            'fecha_nacimiento': self.fecha_nacimiento.isoformat() if self.fecha_nacimiento else None,
            'telefono': self.telefono or '',
            'whatsapp': self.whatsapp or '',
            'email': self.email or '',
            'doctor_id': self.doctor_id,
            'doctor_nombre': self.doctor.nombre if self.doctor else None,
            'tutor_id': self.tutor_id,
            'tutor_nombre': self.tutor.nombre_completo if self.tutor else None,
            'tutor_whatsapp': self.tutor.whatsapp if self.tutor else None,
            'es_menor_edad': self.es_menor_edad,
            'nombre_tutor': self.nombre_tutor or '',
            'telefono_tutor': self.telefono_tutor or '',
            'escuela': self.escuela or '',
            'notas': self.notas or '',
            'estatus_crm': self.estatus_crm.value if self.estatus_crm else 'prospecto',
            'ultima_cita': self.ultima_cita.isoformat() if self.ultima_cita else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'es_problematico': self.es_problematico,
        }


class Cita(db.Model):
    __tablename__ = 'citas'

    id = db.Column(db.Integer, primary_key=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey('pacientes.id'), nullable=False)
    dentista_id = db.Column(db.Integer, db.ForeignKey('dentistas.id'), nullable=False)
    consultorio_id = db.Column(db.Integer, db.ForeignKey('consultorios.id'), nullable=False)
    tipo_cita_id = db.Column(db.Integer, db.ForeignKey('tipos_cita.id'))

    fecha_inicio = db.Column(db.DateTime, nullable=False, index=True)
    fecha_fin = db.Column(db.DateTime, nullable=False)

    status = db.Column(db.Enum(EstatusCita), default=EstatusCita.pendiente)
    notas = db.Column(db.Text)

    anticipo_pagado = db.Column(db.Boolean, default=False)
    anticipo_monto = db.Column(db.Numeric(10, 2), default=0)

    reminder_24h_sent = db.Column(db.Boolean, default=False)
    postconsulta_sent = db.Column(db.Boolean, default=False)

    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    recordatorios = db.relationship('Recordatorio', backref='cita',
                                    lazy=True, cascade='all, delete-orphan')
    justificantes = db.relationship('Justificante', backref='cita', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'paciente_id': self.paciente_id,
            'paciente': self.paciente.nombre_completo if self.paciente else '',
            'dentista_id': self.dentista_id,
            'dentista': self.dentista.nombre if self.dentista else '',
            'dentista_color': self.dentista.color if self.dentista else '#3788d8',
            'consultorio_id': self.consultorio_id,
            'consultorio': self.consultorio.nombre if self.consultorio else '',
            'tipo_cita_id': self.tipo_cita_id,
            'tipo_cita': self.tipo_cita.nombre if self.tipo_cita else '',
            'fecha_inicio': self.fecha_inicio.isoformat(),
            'fecha_fin': self.fecha_fin.isoformat(),
            'status': self.status.value,
            'notas': self.notas or '',
            'anticipo_pagado': self.anticipo_pagado,
            'anticipo_monto': float(self.anticipo_monto) if self.anticipo_monto else 0,
        }

    def to_calendar_event(self):
        """Formato FullCalendar con resource (consultorio) y color del dentista."""
        status_colors = {
            EstatusCita.pendiente: None,  # usa color del dentista
            EstatusCita.confirmada: None,
            EstatusCita.no_asistencia: '#9e9e9e',
            EstatusCita.cancelada: '#bdbdbd',
        }
        color = status_colors.get(self.status) or (self.dentista.color if self.dentista else '#3788d8')

        return {
            'id': self.id,
            'title': f'{self.paciente.nombre_completo if self.paciente else "?"} - {self.dentista.nombre if self.dentista else "?"}',
            'start': self.fecha_inicio.isoformat(),
            'end': self.fecha_fin.isoformat(),
            'resourceId': str(self.consultorio_id),
            'backgroundColor': color,
            'borderColor': color,
            'textColor': '#ffffff',
            'extendedProps': {
                'paciente_id': self.paciente_id,
                'dentista_id': self.dentista_id,
                'consultorio_id': self.consultorio_id,
                'status': self.status.value,
                'tipo_cita': self.tipo_cita.nombre if self.tipo_cita else '',
                'anticipo_pagado': self.anticipo_pagado,
                'notas': self.notas or '',
            }
        }


class Recordatorio(db.Model):
    __tablename__ = 'recordatorios'

    id = db.Column(db.Integer, primary_key=True)
    cita_id = db.Column(db.Integer, db.ForeignKey('citas.id'), nullable=False)
    tipo = db.Column(db.Enum(TipoRecordatorio), nullable=False)
    mensaje_enviado = db.Column(db.Text)
    fecha_envio = db.Column(db.DateTime)
    status = db.Column(db.Enum(EstatusRecordatorio), default=EstatusRecordatorio.pendiente)
    error = db.Column(db.Text)


class SeguimientoCRM(db.Model):
    __tablename__ = 'seguimientos_crm'

    id = db.Column(db.Integer, primary_key=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey('pacientes.id'), nullable=False)
    tipo = db.Column(db.Enum(TipoSeguimiento), nullable=False)
    fecha_programada = db.Column(db.DateTime)
    fecha_enviado = db.Column(db.DateTime)
    notas = db.Column(db.Text)
    completado = db.Column(db.Boolean, default=False)


class ConversacionWhatsapp(db.Model):
    __tablename__ = 'conversaciones_whatsapp'

    id = db.Column(db.Integer, primary_key=True)
    numero_telefono = db.Column(db.String(20), nullable=False, index=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey('pacientes.id'), nullable=True)
    mensaje = db.Column(db.Text, nullable=False)
    es_bot = db.Column(db.Boolean, default=False)  # False=paciente, True=bot
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    session_context = db.Column(db.Text)  # JSON con contexto de la sesion


class Justificante(db.Model):
    __tablename__ = 'justificantes'

    id = db.Column(db.Integer, primary_key=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey('pacientes.id'), nullable=False)
    cita_id = db.Column(db.Integer, db.ForeignKey('citas.id'), nullable=True)
    fecha_emision = db.Column(db.Date, default=date.today)
    escuela = db.Column(db.String(200))
    tratamiento_realizado = db.Column(db.Text, nullable=False)
    doctor_firmante = db.Column(db.String(200), default='C.D.E.O. Paulina Mendoza Ordoñez')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    creator = db.relationship('User', backref='justificantes')


class PlantillaMensaje(db.Model):
    __tablename__ = 'plantillas_mensaje'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    contenido = db.Column(db.Text, nullable=False)
    activo = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'tipo': self.tipo,
            'contenido': self.contenido,
        }


class ConfiguracionConsultorio(db.Model):
    """Configuracion global del consultorio (singleton)."""
    __tablename__ = 'configuracion_consultorio'

    id = db.Column(db.Integer, primary_key=True)
    nombre_consultorio = db.Column(db.String(200), default='La Casa del Sr. Perez')
    direccion = db.Column(db.Text, default='Av. Claveria, CDMX (puerta negra lado derecho de Farmacia Similares)')
    telefono = db.Column(db.String(20))
    whatsapp_negocio = db.Column(db.String(20))
    horario_apertura = db.Column(db.Time, default=time(9, 0))
    horario_cierre = db.Column(db.Time, default=time(18, 0))
    precio_primera_consulta = db.Column(db.Numeric(10, 2), default=550.00)
    porcentaje_anticipo = db.Column(db.Integer, default=50)
    clabe = db.Column(db.String(20), default='012180015419659725')
    tarjeta = db.Column(db.String(20), default='4152314207155287')
    titular_cuenta = db.Column(db.String(200), default='Paulina Mendoza Ordoñez')
    google_reviews_link = db.Column(db.String(500), default='https://n9.cl/ufkug')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
