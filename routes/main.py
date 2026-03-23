from flask import Blueprint, render_template, flash, redirect, url_for
from flask_login import login_required, current_user
from extensions import permiso_requerido
from models import Dentista, Consultorio, TipoCita, ConfiguracionConsultorio, Paciente, OrigenPaciente

main_bp = Blueprint('main', __name__)

PERMISO_RUTAS = [
    ('calendario', 'main.dashboard'),
    ('pacientes', 'main.pacientes'),
    ('crm', 'main.crm'),
    ('bot', 'main.bot_monitor'),
]


def _primera_ruta_permitida():
    """Return the first route the current user has permission to access."""
    for permiso, endpoint in PERMISO_RUTAS:
        if current_user.tiene_permiso(permiso):
            return url_for(endpoint)
    return None


@main_bp.route('/')
@login_required
def dashboard():
    if not current_user.tiene_permiso('calendario'):
        ruta = _primera_ruta_permitida()
        if ruta:
            return redirect(ruta)
        flash('No tienes permisos asignados. Contacta al administrador.', 'danger')
        return redirect(url_for('auth.logout'))
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
@permiso_requerido('pacientes')
def pacientes():
    return render_template('pacientes.html')


@main_bp.route('/crm')
@login_required
@permiso_requerido('crm')
def crm():
    return render_template('crm.html')


@main_bp.route('/bot')
@login_required
@permiso_requerido('bot')
def bot_monitor():
    return render_template('bot_conversaciones.html')


@main_bp.route('/configuracion')
@login_required
def configuracion():
    if not current_user.is_admin():
        flash('Solo administradores pueden acceder a configuracion.', 'danger')
        return redirect(url_for('main.dashboard'))
    config = ConfiguracionConsultorio.query.first()
    dentistas = Dentista.query.order_by(Dentista.nombre).all()
    tipos = TipoCita.query.order_by(TipoCita.nombre).all()
    from models import PlantillaMensaje
    plantillas = PlantillaMensaje.query.filter_by(activo=True).all()
    origenes = OrigenPaciente.query.filter_by(activo=True).order_by(OrigenPaciente.nombre).all()
    return render_template('configuracion.html',
                           config=config,
                           dentistas=dentistas,
                           tipos=tipos,
                           plantillas=plantillas,
                           origenes=origenes)
