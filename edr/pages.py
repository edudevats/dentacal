"""Paginas HTML del Estado de Resultados para administradores."""

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required


edr_pages_bp = Blueprint('edr_pages', __name__)


@edr_pages_bp.before_request
@login_required
def require_edr_admin():
    """Mantiene el EDR accesible solo para administradores autenticados."""
    if not current_user.is_admin():
        flash('Solo administradores pueden acceder a Contabilidad.', 'danger')
        return redirect(url_for('main.dashboard'))


@edr_pages_bp.get('/contabilidad')
def resumen():
    return render_template('edr/resumen.html')


@edr_pages_bp.get('/contabilidad/ingresos')
def ingresos():
    return render_template('edr/ingresos.html')


@edr_pages_bp.get('/contabilidad/gastos')
def gastos():
    return render_template('edr/gastos.html')


@edr_pages_bp.get('/contabilidad/pagos-doctores')
def pagos_doctores():
    return render_template('edr/pagos_doctores.html')
