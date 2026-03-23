from flask import Blueprint, jsonify, request, make_response
from flask_login import login_required, current_user
from extensions import db, permiso_requerido
from models import Justificante, Paciente, Cita
from datetime import date

justificantes_bp = Blueprint('justificantes', __name__, url_prefix='/api/justificantes')


@justificantes_bp.before_request
@login_required
@permiso_requerido('calendario')
def _check_permiso():
    pass


@justificantes_bp.route('', methods=['POST'])
@login_required
def crear():
    data = request.get_json(silent=True)
    if not data:
        return jsonify(error='JSON inválido'), 400

    paciente_id = data.get('paciente_id')
    if not paciente_id:
        return jsonify(error='paciente_id requerido'), 400

    p = Paciente.query.filter_by(id=paciente_id, eliminado=False).first_or_404()

    cita_id = data.get('cita_id')
    escuela = data.get('escuela') or ''
    tratamiento = data.get('tratamiento_realizado', '')
    doctor = data.get('doctor_firmante', 'C.D.E.O. Paulina Mendoza Ordonez')

    if not tratamiento:
        return jsonify(error='tratamiento_realizado es requerido'), 400

    j = Justificante(
        paciente_id=paciente_id,
        cita_id=cita_id,
        escuela=escuela,
        tratamiento_realizado=tratamiento,
        doctor_firmante=doctor,
        fecha_emision=date.today(),
        created_by=current_user.id,
    )
    db.session.add(j)
    db.session.commit()
    return jsonify(id=j.id, ok=True), 201


@justificantes_bp.route('/<int:justificante_id>/pdf', methods=['GET'])
@login_required
def descargar_pdf(justificante_id):
    j = Justificante.query.get_or_404(justificante_id)
    try:
        from services.pdf_service import generar_justificante_pdf
        pdf_bytes = generar_justificante_pdf(j)
        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        nombre_archivo = f'justificante_{j.paciente.nombre_completo.replace(" ", "_")}_{j.fecha_emision}.pdf'
        response.headers['Content-Disposition'] = f'attachment; filename="{nombre_archivo}"'
        return response
    except Exception as e:
        return jsonify(error=f'Error generando PDF: {str(e)}'), 500


@justificantes_bp.route('/paciente/<int:paciente_id>', methods=['GET'])
@login_required
def listar_por_paciente(paciente_id):
    justificantes = Justificante.query.filter_by(paciente_id=paciente_id)\
        .order_by(Justificante.created_at.desc()).all()
    return jsonify([{
        'id': j.id,
        'fecha_emision': j.fecha_emision.isoformat(),
        'escuela': j.escuela,
        'tratamiento_realizado': j.tratamiento_realizado,
        'doctor_firmante': j.doctor_firmante,
    } for j in justificantes])
