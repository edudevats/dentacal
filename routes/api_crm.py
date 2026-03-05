from flask import Blueprint, request, jsonify, render_template, current_app
from flask_login import login_required
from models import db, Paciente, Cita, SeguimientoCRM
from datetime import datetime
from services.whatsapp_service import enviar_mensaje
from services.crm_service import obtener_plantilla_mensaje

bp_crm = Blueprint('crm', __name__)


@bp_crm.before_request
@login_required
def require_login():
    pass

ESTADOS_CRM = ['nuevo', 'activo', 'seguimiento_1', 'seguimiento_2', 'llamada_pendiente', 'perdido']

ESTADO_COLORES = {
    'nuevo': '#6c757d',
    'activo': '#28a745',
    'seguimiento_1': '#ffc107',
    'seguimiento_2': '#e83e8c',
    'llamada_pendiente': '#6f42c1',
    'perdido': '#dc3545',
}


@bp_crm.route('/crm')
def view_crm():
    pacientes = Paciente.query.order_by(Paciente.nombre).all()
    return render_template('crm.html',
                           pacientes=pacientes,
                           estados=ESTADOS_CRM,
                           estado_colores=ESTADO_COLORES)


@bp_crm.route('/api/crm/pacientes', methods=['GET'])
def api_crm_pacientes():
    estado = request.args.get('estado')
    q_text = request.args.get('q', '').strip()

    q = Paciente.query
    if estado:
        q = q.filter_by(estado_crm=estado)
    if q_text:
        like = f'%{q_text}%'
        q = q.filter(db.or_(Paciente.nombre.ilike(like), Paciente.telefono.ilike(like)))

    pacientes = q.order_by(Paciente.nombre).all()
    result = []
    for p in pacientes:
        d = p.to_dict()
        d['total_citas'] = len(p.citas)
        result.append(d)
    return jsonify(result)


@bp_crm.route('/api/crm/pacientes/<int:paciente_id>/estado', methods=['PUT'])
def api_cambiar_estado(paciente_id):
    p = Paciente.query.get_or_404(paciente_id)
    data = request.json
    nuevo_estado = data.get('estado_crm')
    if nuevo_estado not in ESTADOS_CRM:
        return jsonify({'error': 'Estado inválido'}), 400
    p.estado_crm = nuevo_estado
    db.session.commit()
    return jsonify(p.to_dict())


@bp_crm.route('/api/crm/enviar_wa', methods=['POST'])
def api_enviar_wa_manual():
    """Enviar WhatsApp manual a un paciente."""
    data = request.json
    paciente_id = data.get('paciente_id')
    tipo = data.get('tipo', 'sonrisas_magicas')
    mensaje_custom = data.get('mensaje')

    p = Paciente.query.get_or_404(paciente_id)

    if mensaje_custom:
        mensaje = mensaje_custom
    else:
        mensaje = obtener_plantilla_mensaje(tipo, {'paciente': p.nombre})

    numero = p.telefono
    if not numero.startswith('whatsapp:'):
        numero = f'whatsapp:{numero}'

    try:
        enviar_mensaje(numero, mensaje)
        # Registrar seguimiento
        seg = SeguimientoCRM(
            paciente_id=p.id,
            tipo=tipo,
            fecha_programada=datetime.utcnow(),
            fecha_enviado=datetime.utcnow(),
        )
        db.session.add(seg)
        db.session.commit()
        return jsonify({'ok': True, 'mensaje': mensaje})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp_crm.route('/api/crm/export')
def api_export_excel():
    """Exporta pacientes a Excel."""
    import openpyxl
    from io import BytesIO
    from flask import send_file

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Pacientes CRM'

    headers = ['ID', 'Nombre', 'Teléfono', 'Email', 'Estado CRM', 'Última Cita', 'Notas']
    ws.append(headers)

    for p in Paciente.query.order_by(Paciente.nombre).all():
        ws.append([
            p.id,
            p.nombre,
            p.telefono,
            p.email or '',
            p.estado_crm,
            p.fecha_ultima_cita.strftime('%Y-%m-%d %H:%M') if p.fecha_ultima_cita else '',
            p.notas or '',
        ])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='pacientes_crm.xlsx',
    )
