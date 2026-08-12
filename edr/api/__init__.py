from flask import Blueprint, current_app, jsonify
from flask_login import current_user

from edr.schemas import ValidationError


edr_api_bp = Blueprint('edr_api', __name__, url_prefix='/api/edr')


@edr_api_bp.before_request
def require_edr_api_admin():
    if not current_user.is_authenticated:
        return current_app.login_manager.unauthorized()
    if not current_user.is_admin():
        return jsonify(error='Sin permisos'), 403


@edr_api_bp.errorhandler(ValidationError)
def validation_error(error):
    return jsonify(
        error='validation_error',
        mensaje='Revisa los datos enviados.',
        fields=error.fields,
    ), 400


from edr.api import catalogos, gastos, ingresos, pagos, resumen  # noqa: E402, F401


__all__ = ['edr_api_bp']
