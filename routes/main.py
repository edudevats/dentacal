from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models import Dentista, Consultorio, TipoCita, ConfiguracionConsultorio, Paciente

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
@login_required
def dashboard():
    dentistas = Dentista.query.filter_by(activo=True).order_by(Dentista.nombre).all()
    consultorios = Consultorio.query.filter_by(activo=True).order_by(Consultorio.id).all()
    tipos_cita = TipoCita.query.filter_by(activo=True).all()
    return render_template('dashboard.html',
                           dentistas=dentistas,
                           consultorios=consultorios,
                           tipos_cita=tipos_cita,
                           consultorios_json=[c.to_dict() for c in consultorios],
                           dentistas_json=[d.to_dict() for d in dentistas])


@main_bp.route('/pacientes')
@login_required
def pacientes():
    return render_template('pacientes.html')


@main_bp.route('/crm')
@login_required
def crm():
    return render_template('crm.html')


@main_bp.route('/configuracion')
@login_required
def configuracion():
    if not current_user.is_admin():
        from flask import flash, redirect, url_for
        flash('Solo administradores pueden acceder a configuracion.', 'danger')
        return redirect(url_for('main.dashboard'))
    config = ConfiguracionConsultorio.query.first()
    dentistas = Dentista.query.order_by(Dentista.nombre).all()
    tipos = TipoCita.query.order_by(TipoCita.nombre).all()
    from models import PlantillaMensaje
    plantillas = PlantillaMensaje.query.filter_by(activo=True).all()
    return render_template('configuracion.html',
                           config=config,
                           dentistas=dentistas,
                           tipos=tipos,
                           plantillas=plantillas)
