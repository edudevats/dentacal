from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required
from models import db, Dentista, HorarioDentista, BloqueoDentista
from datetime import datetime
from extensions import cache

bp_doctores = Blueprint('doctores', __name__)


@bp_doctores.before_request
@login_required
def require_login():
    pass


@bp_doctores.route('/doctores')
def view_doctores():
    dentistas = Dentista.query.order_by(Dentista.nombre).all()
    return render_template('doctores.html', dentistas=dentistas)


# ── Dentistas CRUD ────────────────────────────────────────────────────────────

@bp_doctores.route('/api/doctores', methods=['GET'])
@cache.cached(timeout=600, key_prefix='lista_doctores')  # 10 min
def api_listar_doctores():
    dentistas = Dentista.query.order_by(Dentista.nombre).all()
    return jsonify([d.to_dict() for d in dentistas])


@bp_doctores.route('/api/doctores', methods=['POST'])
def api_crear_doctor():
    data = request.json
    if not data.get('nombre'):
        return jsonify({'error': 'Nombre requerido'}), 400
    d = Dentista(
        nombre=data['nombre'],
        color=data.get('color', '#3788d8'),
        especialidad=data.get('especialidad', ''),
        telefono=data.get('telefono', ''),
        activo=data.get('activo', True),
    )
    db.session.add(d)
    db.session.commit()
    cache.delete('lista_doctores')
    return jsonify(d.to_dict()), 201


@bp_doctores.route('/api/doctores/<int:doc_id>', methods=['GET'])
def api_obtener_doctor(doc_id):
    d = Dentista.query.get_or_404(doc_id)
    data = d.to_dict()
    data['horarios'] = [h.to_dict() for h in d.horarios]
    data['bloqueos'] = [b.to_dict() for b in d.bloqueos]
    return jsonify(data)


@bp_doctores.route('/api/doctores/<int:doc_id>', methods=['PUT'])
def api_actualizar_doctor(doc_id):
    d = Dentista.query.get_or_404(doc_id)
    data = request.json
    for campo in ('nombre', 'color', 'especialidad', 'telefono', 'activo'):
        if campo in data:
            setattr(d, campo, data[campo])
    db.session.commit()
    cache.delete('lista_doctores')
    return jsonify(d.to_dict())


@bp_doctores.route('/api/doctores/<int:doc_id>', methods=['DELETE'])
def api_eliminar_doctor(doc_id):
    d = Dentista.query.get_or_404(doc_id)
    d.activo = False
    db.session.commit()
    cache.delete('lista_doctores')
    return jsonify({'ok': True})


# ── Horarios ──────────────────────────────────────────────────────────────────

@bp_doctores.route('/api/doctores/<int:doc_id>/horarios', methods=['GET'])
def api_horarios(doc_id):
    d = Dentista.query.get_or_404(doc_id)
    return jsonify([h.to_dict() for h in d.horarios])


@bp_doctores.route('/api/doctores/<int:doc_id>/horarios', methods=['POST'])
def api_agregar_horario(doc_id):
    Dentista.query.get_or_404(doc_id)
    data = request.json
    h = HorarioDentista(
        dentista_id=doc_id,
        dia_semana=int(data['dia_semana']),
        hora_inicio=data['hora_inicio'],
        hora_fin=data['hora_fin'],
    )
    db.session.add(h)
    db.session.commit()
    return jsonify(h.to_dict()), 201


@bp_doctores.route('/api/horarios/<int:horario_id>', methods=['DELETE'])
def api_eliminar_horario(horario_id):
    h = HorarioDentista.query.get_or_404(horario_id)
    db.session.delete(h)
    db.session.commit()
    return jsonify({'ok': True})


# ── Bloqueos ──────────────────────────────────────────────────────────────────

@bp_doctores.route('/api/doctores/<int:doc_id>/bloqueos', methods=['GET'])
def api_bloqueos(doc_id):
    d = Dentista.query.get_or_404(doc_id)
    return jsonify([b.to_dict() for b in d.bloqueos])


@bp_doctores.route('/api/doctores/<int:doc_id>/bloqueos', methods=['POST'])
def api_agregar_bloqueo(doc_id):
    Dentista.query.get_or_404(doc_id)
    data = request.json
    try:
        fi = datetime.strptime(data['fecha_inicio'], '%Y-%m-%d').date()
        ff = datetime.strptime(data['fecha_fin'], '%Y-%m-%d').date()
    except (KeyError, ValueError) as e:
        return jsonify({'error': f'Fechas inválidas: {e}'}), 400
    b = BloqueoDentista(
        dentista_id=doc_id,
        fecha_inicio=fi,
        fecha_fin=ff,
        motivo=data.get('motivo', ''),
    )
    db.session.add(b)
    db.session.commit()
    return jsonify(b.to_dict()), 201


@bp_doctores.route('/api/bloqueos/<int:bloqueo_id>', methods=['DELETE'])
def api_eliminar_bloqueo(bloqueo_id):
    b = BloqueoDentista.query.get_or_404(bloqueo_id)
    db.session.delete(b)
    db.session.commit()
    return jsonify({'ok': True})
