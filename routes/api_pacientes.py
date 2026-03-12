from flask import Blueprint, jsonify, request
from flask_login import login_required
from extensions import db
from models import Paciente, EstatusCRM
from datetime import datetime, date

pacientes_bp = Blueprint('pacientes', __name__, url_prefix='/api/pacientes')


@pacientes_bp.route('', methods=['GET'])
@login_required
def listar():
    q = Paciente.query.filter_by(eliminado=False)

    # Busqueda
    search = request.args.get('q', '').strip()
    if search:
        like = f'%{search}%'
        q = q.filter(
            db.or_(
                Paciente.nombre.ilike(like),
                Paciente.whatsapp.ilike(like),
                Paciente.telefono.ilike(like),
            )
        )

    estatus = request.args.get('estatus')
    if estatus:
        try:
            q = q.filter_by(estatus_crm=EstatusCRM[estatus])
        except KeyError:
            pass

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(per_page, 200)

    pagination = q.order_by(Paciente.nombre).paginate(
        page=page, per_page=per_page, error_out=False)

    return jsonify({
        'pacientes': [p.to_dict() for p in pagination.items],
        'total': pagination.total,
        'page': page,
        'pages': pagination.pages,
    })


@pacientes_bp.route('/buscar-whatsapp', methods=['GET'])
@login_required
def buscar_por_whatsapp():
    numero = request.args.get('numero', '').strip()
    if not numero:
        return jsonify(error='Numero requerido'), 400
    # Normalizar: remover whatsapp: prefix y espacios
    numero = numero.replace('whatsapp:', '').replace(' ', '').replace('-', '')
    if not numero.startswith('+'):
        numero_con_plus = '+' + numero
    else:
        numero_con_plus = numero

    paciente = Paciente.query.filter(
        db.or_(
            Paciente.whatsapp == numero,
            Paciente.whatsapp == numero_con_plus,
        ),
        Paciente.eliminado == False
    ).first()

    if paciente:
        return jsonify(encontrado=True, paciente=paciente.to_dict())
    return jsonify(encontrado=False)


@pacientes_bp.route('/<int:paciente_id>', methods=['GET'])
@login_required
def detalle(paciente_id):
    p = Paciente.query.filter_by(id=paciente_id, eliminado=False).first_or_404()
    data = p.to_dict()
    # Ultimas 5 citas
    from models import Cita
    citas = Cita.query.filter_by(paciente_id=paciente_id)\
        .order_by(Cita.fecha_inicio.desc()).limit(5).all()
    data['citas_recientes'] = [c.to_dict() for c in citas]
    return jsonify(data)


@pacientes_bp.route('', methods=['POST'])
@login_required
def crear():
    data = request.get_json(force=True)
    if not data.get('nombre'):
        return jsonify(error='El nombre es requerido'), 400

    # Verificar duplicado por whatsapp
    whatsapp = _normalizar_numero(data.get('whatsapp', ''))
    if whatsapp and Paciente.query.filter_by(whatsapp=whatsapp, eliminado=False).first():
        return jsonify(error='Ya existe un paciente con ese numero de WhatsApp'), 409

    fecha_nac = None
    if data.get('fecha_nacimiento'):
        try:
            fecha_nac = datetime.strptime(data['fecha_nacimiento'], '%Y-%m-%d').date()
        except ValueError:
            pass

    p = Paciente(
        nombre=data['nombre'],

        fecha_nacimiento=fecha_nac,
        telefono=data.get('telefono', ''),
        whatsapp=whatsapp or data.get('whatsapp', ''),
        email=data.get('email', ''),
        nombre_tutor=data.get('nombre_tutor', ''),
        telefono_tutor=data.get('telefono_tutor', ''),
        escuela=data.get('escuela', ''),
        notas=data.get('notas', ''),
        estatus_crm=EstatusCRM[data.get('estatus_crm', 'prospecto')],
        doctor_id=data.get('doctor_id'),
        tutor_id=data.get('tutor_id') or None,
    )
    db.session.add(p)
    db.session.commit()
    return jsonify(p.to_dict()), 201


@pacientes_bp.route('/<int:paciente_id>', methods=['PUT'])
@login_required
def actualizar(paciente_id):
    p = Paciente.query.filter_by(id=paciente_id, eliminado=False).first_or_404()
    data = request.get_json(force=True)

    if 'nombre' in data:
        p.nombre = data['nombre']
    if 'fecha_nacimiento' in data and data['fecha_nacimiento']:
        try:
            p.fecha_nacimiento = datetime.strptime(data['fecha_nacimiento'], '%Y-%m-%d').date()
        except ValueError:
            pass
    if 'telefono' in data:
        p.telefono = data['telefono']
    if 'whatsapp' in data:
        p.whatsapp = _normalizar_numero(data['whatsapp'])
    if 'email' in data:
        p.email = data['email']
    if 'nombre_tutor' in data:
        p.nombre_tutor = data['nombre_tutor']
    if 'telefono_tutor' in data:
        p.telefono_tutor = data['telefono_tutor']
    if 'escuela' in data:
        p.escuela = data['escuela']
    if 'notas' in data:
        p.notas = data['notas']
    if 'estatus_crm' in data:
        try:
            p.estatus_crm = EstatusCRM[data['estatus_crm']]
        except KeyError:
            pass
    if 'doctor_id' in data:
        p.doctor_id = data['doctor_id']
    if 'tutor_id' in data:
        p.tutor_id = data['tutor_id'] if data['tutor_id'] else None

    db.session.commit()
    return jsonify(p.to_dict())


@pacientes_bp.route('/adultos', methods=['GET'])
@login_required
def buscar_adultos():
    """Busca pacientes adultos (18+) para vincular como tutor."""
    search = request.args.get('q', '').strip()
    if not search or len(search) < 2:
        return jsonify(pacientes=[])

    hoy = date.today()
    try:
        fecha_limite = date(hoy.year - 18, hoy.month, hoy.day)
    except ValueError:
        # Feb 29 edge case
        fecha_limite = date(hoy.year - 18, hoy.month, hoy.day - 1)

    like = f'%{search}%'
    q = Paciente.query.filter(
        Paciente.eliminado == False,
        db.or_(
            Paciente.fecha_nacimiento == None,  # sin fecha = asumido adulto
            Paciente.fecha_nacimiento <= fecha_limite,
        ),
        db.or_(
            Paciente.nombre.ilike(like),
            Paciente.whatsapp.ilike(like),
            Paciente.telefono.ilike(like),
        ),
    ).order_by(Paciente.nombre).limit(10).all()

    return jsonify(pacientes=[p.to_dict() for p in q])


@pacientes_bp.route('/<int:paciente_id>', methods=['DELETE'])
@login_required
def eliminar(paciente_id):
    p = Paciente.query.filter_by(id=paciente_id, eliminado=False).first_or_404()
    p.eliminado = True
    db.session.commit()
    return jsonify(ok=True)


def _normalizar_numero(numero):
    if not numero:
        return numero
    numero = numero.replace('whatsapp:', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    return numero
