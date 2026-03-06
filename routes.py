from flask import Blueprint, render_template, jsonify, request
from models import db, Doctor
from calendar_service import get_calendar_service, obtener_disponibilidad, agendar_cita, calcular_slots_disponibles
from datetime import datetime, timedelta, date as date_type
import dateutil.parser
import os
import json
main = Blueprint('main', __name__)

@main.context_processor
def inject_settings():
    from models import SystemSettings
    settings = SystemSettings.query.first()
    return dict(app_settings=settings)

@main.route('/')
def dashboard():
    doctors = Doctor.query.all()
    return render_template('dashboard.html', doctors=doctors)

@main.route('/doctor/<int:doctor_id>')
def doctor_view(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)
    return render_template('doctor_view.html', doctor=doctor)

@main.route('/doctor/add', methods=['GET', 'POST'])
def add_doctor():
    success = False
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        email = request.form.get('email')
        google_calendar_id = request.form.get('google_calendar_id')
        hora_inicio_str = request.form.get('hora_inicio')
        hora_fin_str = request.form.get('hora_fin')
        
        if nombre and email and google_calendar_id and hora_inicio_str and hora_fin_str:
            hora_inicio = datetime.strptime(hora_inicio_str, '%H:%M').time()
            hora_fin = datetime.strptime(hora_fin_str, '%H:%M').time()
            
            new_doc = Doctor(
                nombre=nombre,
                email=email,
                google_calendar_id=google_calendar_id,
                hora_inicio_trabajo=hora_inicio,
                hora_fin_trabajo=hora_fin
            )
            db.session.add(new_doc)
            db.session.commit()
            success = True
            
    return render_template('add_doctor.html', success=success)


@main.route('/doctor/edit/<int:doctor_id>', methods=['GET', 'POST'])
def edit_doctor(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)
    success = False
    
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        email = request.form.get('email')
        google_calendar_id = request.form.get('google_calendar_id')
        hora_inicio_str = request.form.get('hora_inicio')
        hora_fin_str = request.form.get('hora_fin')
        
        if nombre and email and google_calendar_id and hora_inicio_str and hora_fin_str:
            hora_inicio = datetime.strptime(hora_inicio_str, '%H:%M').time()
            hora_fin = datetime.strptime(hora_fin_str, '%H:%M').time()
            
            doctor.nombre = nombre
            doctor.email = email
            doctor.google_calendar_id = google_calendar_id
            doctor.hora_inicio_trabajo = hora_inicio
            doctor.hora_fin_trabajo = hora_fin
            
            db.session.commit()
            success = True
            
    return render_template('edit_doctor.html', doctor=doctor, success=success)


@main.route('/doctor/delete/<int:doctor_id>', methods=['POST'])
def delete_doctor(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)
    db.session.delete(doctor)
    db.session.commit()
    # To keep things simple, redirect to dashboard.
    from flask import redirect, url_for
    return redirect(url_for('main.dashboard'))

@main.route('/api/eventos_doctor/<int:doctor_id>')
def api_eventos_doctor(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)
    
    start = request.args.get('start')
    end = request.args.get('end')
    
    if not start or not end:
        return jsonify({"error": "Missing start or end params"}), 400
        
    try:
        tiempo_inicio = dateutil.parser.isoparse(start)
        tiempo_fin = dateutil.parser.isoparse(end)
    except Exception as e:
        return jsonify({"error": "Invalid date format"}), 400
    
    servicio_google = get_calendar_service()
    if not servicio_google:
        # Instead of returning a mock example, return empty if not connected.
        return jsonify([])
    ocupado = obtener_disponibilidad(
        servicio_google, doctor.google_calendar_id, tiempo_inicio, tiempo_fin
    )
    
    eventos = []
    for bloque in ocupado:
        eventos.append({
            "title": "Ocupado",
            "start": bloque['start'],
            "end": bloque['end'],
            "color": "#e74c3c"
        })
        
    return jsonify(eventos)

@main.route('/api/horarios_disponibles/<int:doctor_id>')
def api_horarios_disponibles(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)

    fecha_str = request.args.get('fecha')
    if not fecha_str:
        return jsonify({"error": "Falta el parámetro 'fecha'"}), 400

    try:
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido, usa YYYY-MM-DD"}), 400

    try:
        duracion = int(request.args.get('duracion', 30))
    except ValueError:
        return jsonify({"error": "Duración inválida"}), 400

    if duracion not in [15, 30, 45, 60, 90, 120]:
        return jsonify({"error": "Duración debe ser 15, 30, 45, 60, 90 o 120"}), 400

    tiempo_inicio = datetime(fecha_obj.year, fecha_obj.month, fecha_obj.day, 0, 0, 0)
    tiempo_fin = datetime(fecha_obj.year, fecha_obj.month, fecha_obj.day, 23, 59, 59)

    servicio_google = get_calendar_service()
    if not servicio_google:
        slots = calcular_slots_disponibles([], doctor.hora_inicio_trabajo, doctor.hora_fin_trabajo, fecha_obj, duracion)
        return jsonify({"slots": slots, "fecha": fecha_str, "duracion": duracion})

    ocupado = obtener_disponibilidad(servicio_google, doctor.google_calendar_id, tiempo_inicio, tiempo_fin)
    slots = calcular_slots_disponibles(ocupado, doctor.hora_inicio_trabajo, doctor.hora_fin_trabajo, fecha_obj, duracion)

    return jsonify({"slots": slots, "fecha": fecha_str, "duracion": duracion})


@main.route('/api/proxima_disponibilidad/<int:doctor_id>')
def api_proxima_disponibilidad(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)

    try:
        duracion = int(request.args.get('duracion', 30))
    except ValueError:
        duracion = 30

    if duracion not in [15, 30, 45, 60, 90, 120]:
        duracion = 30

    try:
        dias_a_buscar = min(int(request.args.get('dias', 7)), 14)
    except ValueError:
        dias_a_buscar = 7

    servicio_google = get_calendar_service()
    hoy = datetime.now().date()

    for i in range(dias_a_buscar):
        dia = hoy + timedelta(days=i)
        if dia.weekday() >= 5:  # Sábado=5, Domingo=6
            continue

        tiempo_inicio = datetime(dia.year, dia.month, dia.day, 0, 0, 0)
        tiempo_fin = datetime(dia.year, dia.month, dia.day, 23, 59, 59)

        if servicio_google:
            ocupado = obtener_disponibilidad(servicio_google, doctor.google_calendar_id, tiempo_inicio, tiempo_fin)
        else:
            ocupado = []

        slots = calcular_slots_disponibles(ocupado, doctor.hora_inicio_trabajo, doctor.hora_fin_trabajo, dia, duracion)
        disponibles = [s for s in slots if s['disponible']]

        if disponibles:
            return jsonify({
                "encontrado": True,
                "fecha": dia.isoformat(),
                "primer_slot": disponibles[0],
                "total_disponibles": len(disponibles)
            })

    return jsonify({"encontrado": False})


@main.route('/api/agendar', methods=['POST'])
def api_agendar():
    data = request.json
    doctor_id = data.get('doctor_id')
    paciente_info = data.get('paciente_info')
    inicio_str = data.get('inicio')
    fin_str = data.get('fin')
    
    if not all([doctor_id, paciente_info, inicio_str, fin_str]):
        return jsonify({"error": "Missing fields"}), 400

    tipo_consulta = data.get('tipo_consulta', 'primera_vez')
    telefono = data.get('telefono')
    notas = data.get('notas')

    doctor = Doctor.query.get_or_404(doctor_id)
    inicio = dateutil.parser.isoparse(inicio_str)
    fin = dateutil.parser.isoparse(fin_str)

    servicio_google = get_calendar_service()
    if not servicio_google:
        return jsonify({"success": True, "link": "#", "message": "Example created (No Google integration present yet)"})

    from models import SystemSettings
    settings = SystemSettings.query.first()
    admin_cal_id = settings.admin_calendar_id if settings else 'primary'

    link = agendar_cita(
        servicio_google,
        admin_cal_id,
        doctor.email,
        paciente_info,
        inicio,
        fin,
        tipo_consulta=tipo_consulta,
        telefono=telefono,
        notas=notas
    )
    
    if link:
        return jsonify({"success": True, "link": link})
    else:
        return jsonify({"success": False, "error": "Failed to create event"}), 500

@main.route('/settings', methods=['GET', 'POST'])
def settings():
    from models import SystemSettings
    settings = SystemSettings.query.first()
    if not settings:
        settings = SystemSettings(clinic_name="MediCal", admin_calendar_id="primary")
        db.session.add(settings)
        db.session.commit()
        
    # Use absolute path resolving in the same directory as this file or base directory
    creds_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'credentials.json')
    success = False
    
    if request.method == 'POST':
        # Update General Settings
        clinic_name = request.form.get('clinic_name')
        admin_calendar_id = request.form.get('admin_calendar_id')
        
        if clinic_name:
            settings.clinic_name = clinic_name
        if admin_calendar_id:
            settings.admin_calendar_id = admin_calendar_id
            
        db.session.commit()
        
        # Update Credentials
        creds_content = request.form.get('credentials_json')
        if creds_content and creds_content.strip():
            try:
                json.loads(creds_content)
                with open(creds_path, 'w', encoding='utf-8') as f:
                    f.write(creds_content)
            except json.JSONDecodeError:
                pass # Manage JSON error here if needed
                
        success = True
    
    current_creds = ""
    if os.path.exists(creds_path):
        with open(creds_path, 'r', encoding='utf-8') as f:
            current_creds = f.read()
            
    return render_template('settings.html', current_creds=current_creds, success=success, settings=settings)
