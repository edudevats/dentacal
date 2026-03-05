from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from passlib.context import CryptContext
from datetime import datetime, timedelta
import json
import jwt as pyjwt

db = SQLAlchemy()

# Contexto passlib — pbkdf2_sha256 como esquema principal (compatible con bcrypt 4.x)
# bcrypt 4.x eliminó __about__ rompiendo passlib 1.7.4; pbkdf2_sha256 es igualmente seguro
_pwd_context = CryptContext(schemes=['pbkdf2_sha256', 'bcrypt'], deprecated='auto',
                            pbkdf2_sha256__rounds=260000)


class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='recepcionista')
    # 'admin' | 'recepcionista'
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    def set_password(self, password):
        """Hash con bcrypt vía passlib."""
        self.password_hash = _pwd_context.hash(password)

    def check_password(self, password):
        """Verifica contra hash bcrypt. Migra hashes Werkzeug viejos automáticamente."""
        try:
            valid, new_hash = _pwd_context.verify_and_update(password, self.password_hash)
            if valid and new_hash:
                # Re-hash actualizado (p.ej. cambio de rounds)
                self.password_hash = new_hash
            return valid
        except Exception:
            # Fallback para hashes Werkzeug existentes (pbkdf2:sha256:...)
            from werkzeug.security import check_password_hash as _wz_check
            if _wz_check(self.password_hash, password):
                # Migrar al nuevo esquema
                self.set_password(password)
                return True
            return False

    def is_admin(self):
        return self.role == 'admin'

    # ── JWT API tokens ────────────────────────────────────────────────────────

    def generate_api_token(self, secret_key, expires_in=3600):
        """Genera un token JWT para acceso a la API."""
        payload = {
            'user_id': self.id,
            'username': self.username,
            'role': self.role,
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(seconds=expires_in),
        }
        return pyjwt.encode(payload, secret_key, algorithm='HS256')

    @staticmethod
    def verify_api_token(token, secret_key):
        """Verifica un token JWT. Retorna el User o None."""
        try:
            payload = pyjwt.decode(token, secret_key, algorithms=['HS256'])
            return db.session.get(User, payload['user_id'])
        except pyjwt.ExpiredSignatureError:
            return None
        except pyjwt.InvalidTokenError:
            return None

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'activo': self.activo,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
        }


class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    accion = db.Column(db.String(100), nullable=False)
    recurso = db.Column(db.String(50))
    recurso_id = db.Column(db.Integer)
    detalle = db.Column(db.Text)  # JSON
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='audit_logs')

    @staticmethod
    def registrar(user_id, accion, recurso=None, recurso_id=None, detalle=None, ip=None):
        log = AuditLog(
            user_id=user_id,
            accion=accion,
            recurso=recurso,
            recurso_id=recurso_id,
            detalle=json.dumps(detalle) if detalle else None,
            ip_address=ip,
        )
        db.session.add(log)
        # No hace commit — el caller lo hace


class Dentista(db.Model):
    __tablename__ = 'dentista'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(7), default='#3788d8')
    especialidad = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    activo = db.Column(db.Boolean, default=True)

    horarios = db.relationship('HorarioDentista', backref='dentista', lazy=True, cascade='all, delete-orphan')
    bloqueos = db.relationship('BloqueoDentista', backref='dentista', lazy=True, cascade='all, delete-orphan')
    citas = db.relationship('Cita', backref='dentista', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'color': self.color,
            'especialidad': self.especialidad,
            'telefono': self.telefono,
            'activo': self.activo,
        }


class HorarioDentista(db.Model):
    __tablename__ = 'horario_dentista'
    id = db.Column(db.Integer, primary_key=True)
    dentista_id = db.Column(db.Integer, db.ForeignKey('dentista.id'), nullable=False)
    dia_semana = db.Column(db.Integer, nullable=False)  # 0=Lunes … 6=Domingo
    hora_inicio = db.Column(db.String(5), nullable=False)  # "HH:MM"
    hora_fin = db.Column(db.String(5), nullable=False)

    def to_dict(self):
        dias = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        return {
            'id': self.id,
            'dentista_id': self.dentista_id,
            'dia_semana': self.dia_semana,
            'dia_nombre': dias[self.dia_semana],
            'hora_inicio': self.hora_inicio,
            'hora_fin': self.hora_fin,
        }


class BloqueoDentista(db.Model):
    __tablename__ = 'bloqueo_dentista'
    id = db.Column(db.Integer, primary_key=True)
    dentista_id = db.Column(db.Integer, db.ForeignKey('dentista.id'), nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_fin = db.Column(db.Date, nullable=False)
    motivo = db.Column(db.String(200))

    def to_dict(self):
        return {
            'id': self.id,
            'dentista_id': self.dentista_id,
            'fecha_inicio': self.fecha_inicio.isoformat(),
            'fecha_fin': self.fecha_fin.isoformat(),
            'motivo': self.motivo,
        }


class Consultorio(db.Model):
    __tablename__ = 'consultorio'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    activo = db.Column(db.Boolean, default=True)

    citas = db.relationship('Cita', backref='consultorio', lazy=True)

    def to_dict(self):
        return {'id': self.id, 'nombre': self.nombre, 'activo': self.activo}


class TipoCita(db.Model):
    __tablename__ = 'tipo_cita'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    duracion_mins = db.Column(db.Integer, default=30)
    costo = db.Column(db.Float, default=0)
    activo = db.Column(db.Boolean, default=True)

    citas = db.relationship('Cita', backref='tipo_cita', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'duracion_mins': self.duracion_mins,
            'costo': self.costo,
            'activo': self.activo,
        }


class Paciente(db.Model):
    __tablename__ = 'paciente'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(100))
    fecha_nacimiento = db.Column(db.Date)
    nombre_escuela = db.Column(db.String(150))
    notas = db.Column(db.Text)
    estado_crm = db.Column(db.String(30), default='nuevo')
    # nuevo | activo | seguimiento_1 | seguimiento_2 | llamada_pendiente | perdido
    fecha_ultima_cita = db.Column(db.DateTime)
    pin_cumpleanero_usado = db.Column(db.Boolean, default=False)
    eliminado = db.Column(db.Boolean, default=False)  # soft delete
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    citas = db.relationship('Cita', backref='paciente', lazy=True)
    seguimientos = db.relationship('SeguimientoCRM', backref='paciente', lazy=True)
    conversaciones = db.relationship('ConversacionWhatsapp', backref='paciente', lazy=True)
    justificantes = db.relationship('Justificante', backref='paciente', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'telefono': self.telefono,
            'email': self.email,
            'fecha_nacimiento': self.fecha_nacimiento.isoformat() if self.fecha_nacimiento else None,
            'nombre_escuela': self.nombre_escuela,
            'notas': self.notas,
            'estado_crm': self.estado_crm,
            'fecha_ultima_cita': self.fecha_ultima_cita.isoformat() if self.fecha_ultima_cita else None,
            'pin_cumpleanero_usado': self.pin_cumpleanero_usado,
            'creado_en': self.creado_en.isoformat() if self.creado_en else None,
        }


class Cita(db.Model):
    __tablename__ = 'cita'
    id = db.Column(db.Integer, primary_key=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey('paciente.id'), nullable=False)
    dentista_id = db.Column(db.Integer, db.ForeignKey('dentista.id'), nullable=False)
    consultorio_id = db.Column(db.Integer, db.ForeignKey('consultorio.id'), nullable=False)
    tipo_cita_id = db.Column(db.Integer, db.ForeignKey('tipo_cita.id'))
    fecha_inicio = db.Column(db.DateTime, nullable=False)
    fecha_fin = db.Column(db.DateTime, nullable=False)
    estado = db.Column(db.String(20), default='pendiente')
    # pendiente | confirmada | no_asistio | cancelada
    anticipo_registrado = db.Column(db.Boolean, default=False)
    anticipo_monto = db.Column(db.Float, default=0)
    notas = db.Column(db.Text)
    creado_por = db.Column(db.String(20), default='recepcionista')  # recepcionista | bot
    creado_en = db.Column(db.DateTime, default=datetime.utcnow)

    recordatorios = db.relationship('Recordatorio', backref='cita', lazy=True, cascade='all, delete-orphan')
    justificantes = db.relationship('Justificante', backref='cita', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'paciente_id': self.paciente_id,
            'paciente_nombre': self.paciente.nombre if self.paciente else '',
            'paciente_telefono': self.paciente.telefono if self.paciente else '',
            'dentista_id': self.dentista_id,
            'dentista_nombre': self.dentista.nombre if self.dentista else '',
            'dentista_color': self.dentista.color if self.dentista else '#3788d8',
            'consultorio_id': self.consultorio_id,
            'consultorio_nombre': self.consultorio.nombre if self.consultorio else '',
            'tipo_cita_id': self.tipo_cita_id,
            'tipo_cita_nombre': self.tipo_cita.nombre if self.tipo_cita else '',
            'fecha_inicio': self.fecha_inicio.isoformat(),
            'fecha_fin': self.fecha_fin.isoformat(),
            'estado': self.estado,
            'anticipo_registrado': self.anticipo_registrado,
            'anticipo_monto': self.anticipo_monto,
            'notas': self.notas,
            'creado_por': self.creado_por,
        }


class Recordatorio(db.Model):
    __tablename__ = 'recordatorio'
    id = db.Column(db.Integer, primary_key=True)
    cita_id = db.Column(db.Integer, db.ForeignKey('cita.id'), nullable=False)
    tipo = db.Column(db.String(30), nullable=False)
    # 24h | sonrisas_magicas | cumpleanos | resena
    programado_para = db.Column(db.DateTime, nullable=False)
    enviado = db.Column(db.Boolean, default=False)
    fecha_envio = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'cita_id': self.cita_id,
            'tipo': self.tipo,
            'programado_para': self.programado_para.isoformat(),
            'enviado': self.enviado,
            'fecha_envio': self.fecha_envio.isoformat() if self.fecha_envio else None,
        }


class SeguimientoCRM(db.Model):
    __tablename__ = 'seguimiento_crm'
    id = db.Column(db.Integer, primary_key=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey('paciente.id'), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # whatsapp_1 | whatsapp_2 | llamada
    fecha_programada = db.Column(db.DateTime, nullable=False)
    fecha_enviado = db.Column(db.DateTime)
    respondido = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            'id': self.id,
            'paciente_id': self.paciente_id,
            'tipo': self.tipo,
            'fecha_programada': self.fecha_programada.isoformat(),
            'fecha_enviado': self.fecha_enviado.isoformat() if self.fecha_enviado else None,
            'respondido': self.respondido,
        }


class ConversacionWhatsapp(db.Model):
    __tablename__ = 'conversacion_whatsapp'
    id = db.Column(db.Integer, primary_key=True)
    telefono = db.Column(db.String(20), nullable=False, unique=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey('paciente.id'), nullable=True)
    estado_flujo = db.Column(db.String(30), default='info')
    # info | agendando | pagando | confirmado
    historial_mensajes = db.Column(db.Text, default='[]')  # JSON
    ultima_actividad = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        import json
        return {
            'id': self.id,
            'telefono': self.telefono,
            'paciente_id': self.paciente_id,
            'estado_flujo': self.estado_flujo,
            'historial_mensajes': json.loads(self.historial_mensajes or '[]'),
            'ultima_actividad': self.ultima_actividad.isoformat() if self.ultima_actividad else None,
        }


class Justificante(db.Model):
    __tablename__ = 'justificante'
    id = db.Column(db.Integer, primary_key=True)
    paciente_id = db.Column(db.Integer, db.ForeignKey('paciente.id'), nullable=False)
    cita_id = db.Column(db.Integer, db.ForeignKey('cita.id'), nullable=False)
    tratamiento = db.Column(db.String(200))
    escuela = db.Column(db.String(150))
    fecha_emision = db.Column(db.Date, default=datetime.utcnow)
    numero_justificante = db.Column(db.String(20), unique=True)
    pdf_path = db.Column(db.String(255))

    def to_dict(self):
        return {
            'id': self.id,
            'paciente_id': self.paciente_id,
            'cita_id': self.cita_id,
            'tratamiento': self.tratamiento,
            'escuela': self.escuela,
            'fecha_emision': self.fecha_emision.isoformat() if self.fecha_emision else None,
            'numero_justificante': self.numero_justificante,
            'pdf_path': self.pdf_path,
        }


class PlantillaMensaje(db.Model):
    __tablename__ = 'plantilla_mensaje'
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(50), unique=True, nullable=False)
    # bienvenida | anticipo | confirmacion | recordatorio_24h |
    # sonrisas_magicas | cumpleanos | resena
    contenido = db.Column(db.Text, nullable=False)
    activo = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'tipo': self.tipo,
            'contenido': self.contenido,
            'activo': self.activo,
        }
