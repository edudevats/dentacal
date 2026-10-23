from flask import Blueprint, jsonify
from flask_login import login_required

from extensions import db, permiso_requerido
from services.avisos_service import avisos_de_hoy, marcar_todos_leidos

avisos_bp = Blueprint('avisos', __name__, url_prefix='/api/avisos')


@avisos_bp.before_request
@login_required
@permiso_requerido('calendario')
def _check_permiso():
    pass


@avisos_bp.route('/hoy', methods=['GET'])
@login_required
def hoy():
    return jsonify(avisos_de_hoy())


@avisos_bp.route('/leidos', methods=['POST'])
@login_required
def leidos():
    marcados = marcar_todos_leidos()
    db.session.commit()
    return jsonify(ok=True, marcados=marcados)
