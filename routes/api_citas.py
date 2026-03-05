from flask import Blueprint, request, jsonify, render_template, send_file
from flask_login import login_required
from models import db, Cita, Paciente, Dentista, Consultorio, TipoCita
from datetime import datetime, timedelta
from io import BytesIO

bp_citas = Blueprint('citas', __name__)


@bp_citas.before_request
@login_required
def require_login():
    pass


def _check_overlap(consultorio_id, fecha_inicio, fecha_fin, exclude_id=None):
    """Devuelve True si hay solapamiento en el consultorio."""
    q = Cita.query.filter(
        Cita.consultorio_id == consultorio_id,
        Cita.estado != 'cancelada',
        Cita.fecha_inicio < fecha_fin,
        Cita.fecha_fin > fecha_inicio,
    )
    if exclude_id:
        q = q.filter(Cita.id != exclude_id)
    return q.first() is not None


# ── Vistas HTML ───────────────────────────────────────────────────────────────

@bp_citas.route('/citas')
def view_citas():
    pacientes = Paciente.query.order_by(Paciente.nombre).all()
    dentistas = Dentista.query.filter_by(activo=True).order_by(Dentista.nombre).all()
    consultorios = Consultorio.query.filter_by(activo=True).all()
    tipos = TipoCita.query.filter_by(activo=True).all()
    return render_template('citas.html',
                           pacientes=pacientes,
                           dentistas=dentistas,
                           consultorios=consultorios,
                           tipos=tipos)


# ── API ───────────────────────────────────────────────────────────────────────

@bp_citas.route('/api/citas', methods=['GET'])
def api_listar_citas():
    inicio = request.args.get('start')
    fin = request.args.get('end')
    q = Cita.query
    if inicio:
        q = q.filter(Cita.fecha_inicio >= datetime.fromisoformat(inicio))
    if fin:
        q = q.filter(Cita.fecha_fin <= datetime.fromisoformat(fin))
    citas = q.order_by(Cita.fecha_inicio).all()
    return jsonify([c.to_dict() for c in citas])


@bp_citas.route('/api/citas', methods=['POST'])
def api_crear_cita():
    data = request.json
    try:
        fecha_inicio = datetime.fromisoformat(data['fecha_inicio'])
        fecha_fin = datetime.fromisoformat(data['fecha_fin'])
    except (KeyError, ValueError) as e:
        return jsonify({'error': f'Fechas inválidas: {e}'}), 400

    if _check_overlap(data['consultorio_id'], fecha_inicio, fecha_fin):
        return jsonify({'error': 'El consultorio ya está ocupado en ese horario'}), 409

    cita = Cita(
        paciente_id=data['paciente_id'],
        dentista_id=data['dentista_id'],
        consultorio_id=data['consultorio_id'],
        tipo_cita_id=data.get('tipo_cita_id'),
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        estado=data.get('estado', 'pendiente'),
        notas=data.get('notas', ''),
        creado_por=data.get('creado_por', 'recepcionista'),
    )
    db.session.add(cita)

    # Actualizar fecha_ultima_cita del paciente
    paciente = Paciente.query.get(data['paciente_id'])
    if paciente:
        if not paciente.fecha_ultima_cita or fecha_inicio > paciente.fecha_ultima_cita:
            paciente.fecha_ultima_cita = fecha_inicio
        if paciente.estado_crm in ('nuevo', 'perdido', 'seguimiento_1', 'seguimiento_2'):
            paciente.estado_crm = 'activo'

    db.session.commit()
    return jsonify(cita.to_dict()), 201


@bp_citas.route('/api/citas/<int:cita_id>', methods=['GET'])
def api_obtener_cita(cita_id):
    cita = Cita.query.get_or_404(cita_id)
    return jsonify(cita.to_dict())


@bp_citas.route('/api/citas/<int:cita_id>', methods=['PUT'])
def api_actualizar_cita(cita_id):
    cita = Cita.query.get_or_404(cita_id)
    data = request.json

    if 'fecha_inicio' in data and 'fecha_fin' in data:
        nueva_inicio = datetime.fromisoformat(data['fecha_inicio'])
        nueva_fin = datetime.fromisoformat(data['fecha_fin'])
        nuevo_consultorio = data.get('consultorio_id', cita.consultorio_id)
        if _check_overlap(nuevo_consultorio, nueva_inicio, nueva_fin, exclude_id=cita_id):
            return jsonify({'error': 'El consultorio ya está ocupado en ese horario'}), 409
        cita.fecha_inicio = nueva_inicio
        cita.fecha_fin = nueva_fin
        cita.consultorio_id = nuevo_consultorio

    for campo in ('estado', 'notas', 'dentista_id', 'tipo_cita_id',
                  'anticipo_registrado', 'anticipo_monto'):
        if campo in data:
            setattr(cita, campo, data[campo])

    db.session.commit()

    # Si se confirma asistencia, actualizar CRM
    if data.get('estado') == 'confirmada':
        paciente = cita.paciente
        if paciente:
            paciente.estado_crm = 'activo'
            paciente.fecha_ultima_cita = cita.fecha_inicio
            paciente.pin_cumpleanero_usado = False

    db.session.commit()
    return jsonify(cita.to_dict())


@bp_citas.route('/api/citas/<int:cita_id>', methods=['DELETE'])
def api_cancelar_cita(cita_id):
    cita = Cita.query.get_or_404(cita_id)
    cita.estado = 'cancelada'
    db.session.commit()
    return jsonify({'ok': True})


@bp_citas.route('/api/disponibilidad', methods=['GET'])
def api_disponibilidad():
    """Devuelve slots libres para un tipo de cita y doctor."""
    dentista_id = request.args.get('dentista_id', type=int)
    tipo_id = request.args.get('tipo_cita_id', type=int)
    fecha_str = request.args.get('fecha')  # YYYY-MM-DD

    if not (dentista_id and tipo_id and fecha_str):
        return jsonify({'error': 'Faltan parámetros'}), 400

    tipo = TipoCita.query.get_or_404(tipo_id)
    dentista = Dentista.query.get_or_404(dentista_id)
    fecha = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    dia_semana = fecha.weekday()  # 0=Mon

    horario = next((h for h in dentista.horarios if h.dia_semana == dia_semana), None)
    if not horario:
        return jsonify({'slots': [], 'mensaje': 'El doctor no tiene horario ese día'})

    # Verificar bloqueos
    for b in dentista.bloqueos:
        if b.fecha_inicio <= fecha <= b.fecha_fin:
            return jsonify({'slots': [], 'mensaje': 'El doctor tiene bloqueo ese día'})

    # Generar slots
    h_ini = datetime.strptime(f'{fecha_str} {horario.hora_inicio}', '%Y-%m-%d %H:%M')
    h_fin = datetime.strptime(f'{fecha_str} {horario.hora_fin}', '%Y-%m-%d %H:%M')
    slots = []
    current = h_ini
    while current + timedelta(minutes=tipo.duracion_mins) <= h_fin:
        slot_fin = current + timedelta(minutes=tipo.duracion_mins)
        # Verificar que al menos un consultorio esté libre
        consultorios_libres = []
        for c in Consultorio.query.filter_by(activo=True).all():
            if not _check_overlap(c.id, current, slot_fin):
                consultorios_libres.append(c.id)
        if consultorios_libres:
            slots.append({
                'inicio': current.isoformat(),
                'fin': slot_fin.isoformat(),
                'consultorios_disponibles': consultorios_libres,
            })
        current += timedelta(minutes=30)

    return jsonify({'slots': slots})


@bp_citas.route('/api/citas/<int:cita_id>/justificante', methods=['POST'])
def api_generar_justificante(cita_id):
    from services.pdf_service import generar_justificante
    data = request.json or {}
    try:
        result = generar_justificante(
            cita_id=cita_id,
            tratamiento=data.get('tratamiento'),
            escuela=data.get('escuela'),
        )
        return send_file(
            BytesIO(result['pdf_bytes']),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"justificante_{result['numero']}.pdf",
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
