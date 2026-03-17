from flask import Blueprint, jsonify, request
from flask_login import login_required
from extensions import db
from models import Paciente, GrupoFamiliar, EstatusCRM
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

    pacientes = Paciente.query.filter(
        db.or_(
            Paciente.whatsapp == numero,
            Paciente.whatsapp == numero_con_plus,
        ),
        Paciente.eliminado == False
    ).all()

    if pacientes:
        grupo = pacientes[0].grupo_familiar
        return jsonify(
            encontrado=True,
            paciente=pacientes[0].to_dict(),
            pacientes=[p.to_dict() for p in pacientes],
            grupo_familiar=grupo.to_dict() if grupo else None,
        )
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
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400
    if not data.get('nombre'):
        return jsonify(error='El nombre es requerido'), 400

    # Verificar duplicado por whatsapp — ofrecer grupo familiar
    whatsapp = _normalizar_numero(data.get('whatsapp', ''))
    grupo_familiar_id = data.get('grupo_familiar_id')

    if whatsapp and not grupo_familiar_id and not data.get('crear_grupo_familiar'):
        existentes = Paciente.query.filter_by(whatsapp=whatsapp, eliminado=False).all()
        if existentes:
            grupo = existentes[0].grupo_familiar
            return jsonify(
                error='duplicate_whatsapp',
                mensaje='Ya existe un paciente con ese numero de WhatsApp',
                pacientes_existentes=[p.to_dict() for p in existentes],
                grupo_familiar=grupo.to_dict() if grupo else None,
            ), 409

    fecha_nac = None
    if data.get('fecha_nacimiento'):
        try:
            fecha_nac = datetime.strptime(data['fecha_nacimiento'], '%Y-%m-%d').date()
        except ValueError:
            pass

    # Crear/asignar grupo familiar si se solicita
    if data.get('crear_grupo_familiar') and whatsapp:
        apellido = data['nombre'].split()[-1] if data['nombre'] else 'Sin nombre'
        grupo = GrupoFamiliar(nombre=f'Familia {apellido}', telefono_principal=whatsapp)
        db.session.add(grupo)
        db.session.flush()
        grupo_familiar_id = grupo.id
        # Asignar pacientes existentes con este numero al grupo
        for existente in Paciente.query.filter_by(whatsapp=whatsapp, eliminado=False).all():
            if not existente.grupo_familiar_id:
                existente.grupo_familiar_id = grupo.id

    p = Paciente(
        nombre=data['nombre'],
        fecha_nacimiento=fecha_nac,
        telefono=data.get('telefono', ''),
        whatsapp=whatsapp or data.get('whatsapp', ''),
        email=data.get('email', ''),
        nombre_tutor=data.get('nombre_tutor', ''),
        telefono_tutor=data.get('telefono_tutor', ''),
        origen_paciente_id=data.get('origen_paciente_id') or None,
        notas=data.get('notas', ''),
        estatus_crm=EstatusCRM[data.get('estatus_crm', 'prospecto')],
        doctor_id=data.get('doctor_id'),
        tutor_id=data.get('tutor_id') or None,
        grupo_familiar_id=grupo_familiar_id,
    )
    if data.get('proximo_recordatorio_fecha'):
        try:
            p.proximo_recordatorio_fecha = datetime.strptime(
                data['proximo_recordatorio_fecha'], '%Y-%m-%d'
            ).date()
        except ValueError:
            pass
    db.session.add(p)
    db.session.commit()
    return jsonify(p.to_dict()), 201


@pacientes_bp.route('/<int:paciente_id>', methods=['PUT'])
@login_required
def actualizar(paciente_id):
    p = Paciente.query.filter_by(id=paciente_id, eliminado=False).first_or_404()
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400

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
        nuevo_whatsapp = _normalizar_numero(data['whatsapp'])
        if nuevo_whatsapp and nuevo_whatsapp != p.whatsapp:
            existentes = Paciente.query.filter_by(whatsapp=nuevo_whatsapp, eliminado=False).all()
            existentes = [e for e in existentes if e.id != p.id]
            if existentes and not data.get('grupo_familiar_id') and not p.grupo_familiar_id and not data.get('crear_grupo_familiar'):
                grupo = existentes[0].grupo_familiar
                return jsonify(
                    error='duplicate_whatsapp',
                    mensaje='Ya existe un paciente con ese numero de WhatsApp',
                    pacientes_existentes=[e.to_dict() for e in existentes],
                    grupo_familiar=grupo.to_dict() if grupo else None,
                ), 409
            # Crear grupo familiar si se confirmo desde el frontend
            if existentes and data.get('crear_grupo_familiar'):
                apellido = p.nombre.split()[-1] if p.nombre else 'Sin nombre'
                grupo = GrupoFamiliar(nombre=f'Familia {apellido}', telefono_principal=nuevo_whatsapp)
                db.session.add(grupo)
                db.session.flush()
                p.grupo_familiar_id = grupo.id
                for e in existentes:
                    if not e.grupo_familiar_id:
                        e.grupo_familiar_id = grupo.id
            elif data.get('grupo_familiar_id'):
                p.grupo_familiar_id = data['grupo_familiar_id']
        p.whatsapp = nuevo_whatsapp
    if 'email' in data:
        p.email = data['email']
    if 'nombre_tutor' in data:
        p.nombre_tutor = data['nombre_tutor']
    if 'telefono_tutor' in data:
        p.telefono_tutor = data['telefono_tutor']
    if 'origen_paciente_id' in data:
        p.origen_paciente_id = data['origen_paciente_id'] or None
    if 'notas' in data:
        p.notas = data['notas']
    if 'es_problematico' in data:
        p.es_problematico = bool(data['es_problematico'])
        if p.es_problematico:
            p.estatus_crm = EstatusCRM.baja
    if 'estatus_crm' in data:
        try:
            p.estatus_crm = EstatusCRM[data['estatus_crm']]
        except KeyError:
            pass
    if 'doctor_id' in data:
        p.doctor_id = data['doctor_id']
    if 'tutor_id' in data:
        p.tutor_id = data['tutor_id'] if data['tutor_id'] else None
    if 'grupo_familiar_id' in data:
        p.grupo_familiar_id = data['grupo_familiar_id'] if data['grupo_familiar_id'] else None
    if 'proximo_recordatorio_fecha' in data:
        if data['proximo_recordatorio_fecha']:
            try:
                p.proximo_recordatorio_fecha = datetime.strptime(
                    data['proximo_recordatorio_fecha'], '%Y-%m-%d'
                ).date()
            except ValueError:
                pass
        else:
            p.proximo_recordatorio_fecha = None

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


@pacientes_bp.route('/<int:paciente_id>/problematico', methods=['POST'])
@login_required
def toggle_problematico(paciente_id):
    p = Paciente.query.filter_by(id=paciente_id, eliminado=False).first_or_404()
    data = request.get_json(silent=True) or {}
    p.es_problematico = bool(data.get('es_problematico', not p.es_problematico))
    if p.es_problematico:
        p.estatus_crm = EstatusCRM.baja
    db.session.commit()
    return jsonify(p.to_dict())


@pacientes_bp.route('/grupos-familiares', methods=['GET'])
@login_required
def listar_grupos():
    grupos = GrupoFamiliar.query.order_by(GrupoFamiliar.nombre).all()
    return jsonify([g.to_dict() for g in grupos])


@pacientes_bp.route('/grupos-familiares/<int:grupo_id>', methods=['GET'])
@login_required
def detalle_grupo(grupo_id):
    grupo = GrupoFamiliar.query.get_or_404(grupo_id)
    return jsonify(grupo.to_dict())


@pacientes_bp.route('/grupos-familiares/<int:grupo_id>', methods=['PUT'])
@login_required
def actualizar_grupo(grupo_id):
    grupo = GrupoFamiliar.query.get_or_404(grupo_id)
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400
    if 'nombre' in data:
        grupo.nombre = data['nombre']
    db.session.commit()
    return jsonify(grupo.to_dict())


def _normalizar_numero(numero):
    if not numero:
        return numero
    numero = numero.replace('whatsapp:', '').replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    return numero
