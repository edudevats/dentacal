from datetime import datetime

from sqlalchemy.orm import declared_attr

from extensions import db


class MovimientoMixin:
    anulado = db.Column(db.Boolean, nullable=False, default=False, index=True)
    anulado_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    @declared_attr
    def anulado_por_id(cls):
        return db.Column(db.Integer, db.ForeignKey('users.id'))

    @declared_attr
    def created_by_id(cls):
        return db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    @declared_attr
    def updated_by_id(cls):
        return db.Column(db.Integer, db.ForeignKey('users.id'))


class MetodoPago(db.Model):
    __tablename__ = 'metodos_pago'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class GastoConcepto(db.Model):
    __tablename__ = 'gastos_conceptos'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False, unique=True)
    tipo_default = db.Column(db.String(20), nullable=False, default='fijo')
    activo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    __table_args__ = (
        db.CheckConstraint(
            "tipo_default IN ('fijo', 'variable')",
            name='ck_gasto_concepto_tipo',
        ),
    )


class Ingreso(MovimientoMixin, db.Model):
    __tablename__ = 'ingresos'

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False)
    cita_id = db.Column(db.Integer, db.ForeignKey('citas.id'))
    paciente_id = db.Column(db.Integer, db.ForeignKey('pacientes.id'))
    dentista_id = db.Column(db.Integer, db.ForeignKey('dentistas.id'))
    tipo_cita_id = db.Column(db.Integer, db.ForeignKey('tipos_cita.id'))
    metodo_pago_id = db.Column(
        db.Integer,
        db.ForeignKey('metodos_pago.id'),
        nullable=False,
    )
    paciente_nombre = db.Column(db.String(200), nullable=False)
    nombre_tratamiento = db.Column(db.String(200), nullable=False)
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    comision_bancaria = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    comision_doctor = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    descuento_pct = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    factura = db.Column(db.Boolean, nullable=False, default=False)
    tipo_servicio = db.Column(db.String(20), nullable=False, default='clinico')
    comentarios = db.Column(db.Text)

    cita = db.relationship('Cita')
    paciente = db.relationship('Paciente')
    dentista = db.relationship('Dentista')
    tipo_cita = db.relationship('TipoCita')
    metodo_pago = db.relationship('MetodoPago')
    __table_args__ = (
        db.Index('ix_ingresos_fecha_anulado', 'fecha', 'anulado'),
        db.CheckConstraint(
            "tipo_servicio IN ('clinico', 'estetico')",
            name='ck_ingreso_tipo_servicio',
        ),
    )


class GastoOperativo(MovimientoMixin, db.Model):
    __tablename__ = 'gastos_operativos'

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False)
    concepto_id = db.Column(db.Integer, db.ForeignKey('gastos_conceptos.id'))
    concepto_nombre = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(20), nullable=False, default='fijo')
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    comentarios = db.Column(db.Text)

    concepto_catalogo = db.relationship('GastoConcepto')
    __table_args__ = (
        db.Index('ix_gastos_fecha_anulado', 'fecha', 'anulado'),
        db.CheckConstraint("tipo IN ('fijo', 'variable')", name='ck_gasto_tipo'),
    )


class PagoDoctor(MovimientoMixin, db.Model):
    __tablename__ = 'pagos_doctores'

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.Date, nullable=False)
    dentista_id = db.Column(
        db.Integer,
        db.ForeignKey('dentistas.id'),
        nullable=False,
    )
    concepto = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    descuento_saldo = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    dentista = db.relationship('Dentista')
    __table_args__ = (
        db.Index('ix_pagos_doctores_fecha_anulado', 'fecha', 'anulado'),
        db.CheckConstraint(
            "tipo IN ('comision', 'salario', 'otro')",
            name='ck_pago_doctor_tipo',
        ),
    )


class PagoComisionIngreso(db.Model):
    __tablename__ = 'pago_comision_ingreso'

    id = db.Column(db.Integer, primary_key=True)
    pago_id = db.Column(
        db.Integer,
        db.ForeignKey('pagos_doctores.id'),
        nullable=False,
    )
    ingreso_id = db.Column(
        db.Integer,
        db.ForeignKey('ingresos.id'),
        nullable=False,
    )
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    pago = db.relationship(
        'PagoDoctor',
        backref=db.backref('comisiones_liquidadas', cascade='all, delete-orphan'),
    )
    ingreso = db.relationship('Ingreso', backref='comision_liquidacion')
    __table_args__ = (
        db.UniqueConstraint('ingreso_id', name='uq_pago_comision_ingreso'),
    )
