from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
from functools import wraps

from models import db, User, AuditLog
from extensions import limiter
from services.mail_service import (
    generar_token_reset, verificar_token_reset, enviar_reset_password,
)

bp_auth = Blueprint('auth', __name__)


def admin_required(f):
    """Decorador: solo usuarios con rol 'admin'."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.is_admin():
            flash('Acceso restringido. Se requiere rol de administrador.', 'danger')
            return redirect(url_for('calendario.view_calendario'))
        return f(*args, **kwargs)
    return decorated


# ── Login ─────────────────────────────────────────────────────────────────────

@bp_auth.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('calendario.view_calendario'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()

        if user and user.activo and user.check_password(password):
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            AuditLog.registrar(
                user_id=user.id,
                accion='login',
                ip=request.remote_addr,
            )
            db.session.commit()

            next_page = request.args.get('next')
            return redirect(next_page or url_for('calendario.view_calendario'))

        flash('Usuario o contraseña incorrectos.', 'danger')

    return render_template('auth/login.html')


# ── Logout ────────────────────────────────────────────────────────────────────

@bp_auth.route('/logout', methods=['POST'])
@login_required
def logout():
    AuditLog.registrar(
        user_id=current_user.id,
        accion='logout',
        ip=request.remote_addr,
    )
    db.session.commit()
    logout_user()
    flash('Sesión cerrada correctamente.', 'success')
    return redirect(url_for('auth.login'))


# ── Cambiar contraseña ────────────────────────────────────────────────────────

@bp_auth.route('/cambiar-password', methods=['GET', 'POST'])
@login_required
def cambiar_password():
    if request.method == 'POST':
        actual = request.form.get('password_actual', '')
        nueva = request.form.get('password_nueva', '')
        confirmar = request.form.get('password_confirmar', '')

        if not current_user.check_password(actual):
            flash('La contraseña actual es incorrecta.', 'danger')
        elif len(nueva) < 8:
            flash('La nueva contraseña debe tener al menos 8 caracteres.', 'danger')
        elif nueva != confirmar:
            flash('Las contraseñas nuevas no coinciden.', 'danger')
        else:
            current_user.set_password(nueva)
            AuditLog.registrar(
                user_id=current_user.id,
                accion='cambio_password',
                ip=request.remote_addr,
            )
            db.session.commit()
            flash('Contraseña actualizada correctamente.', 'success')
            return redirect(url_for('calendario.view_calendario'))

    return render_template('auth/change_password.html')


# ── Admin: gestión de usuarios ────────────────────────────────────────────────

@bp_auth.route('/admin/usuarios', methods=['GET'])
@login_required
@admin_required
def admin_usuarios():
    usuarios = User.query.order_by(User.created_at.desc()).all()
    return render_template('auth/usuarios.html', usuarios=usuarios)


@bp_auth.route('/admin/usuarios', methods=['POST'])
@login_required
@admin_required
def admin_crear_usuario():
    data = request.get_json() or request.form
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'recepcionista')

    if not username or not email or not password:
        return jsonify(error='username, email y password son requeridos'), 400
    if role not in ('admin', 'recepcionista'):
        return jsonify(error='Rol inválido'), 400
    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify(error='El usuario o email ya existe'), 409

    user = User(username=username, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    AuditLog.registrar(
        user_id=current_user.id,
        accion='crear_usuario',
        recurso='user',
        detalle={'username': username, 'role': role},
        ip=request.remote_addr,
    )
    db.session.commit()
    return jsonify(user.to_dict()), 201


@bp_auth.route('/admin/usuarios/<int:user_id>', methods=['PUT'])
@login_required
@admin_required
def admin_editar_usuario(user_id):
    user = db.get_or_404(User, user_id)
    data = request.get_json() or {}

    if 'role' in data and data['role'] in ('admin', 'recepcionista'):
        user.role = data['role']
    if 'activo' in data:
        user.activo = bool(data['activo'])
    if 'password' in data and data['password']:
        user.set_password(data['password'])

    AuditLog.registrar(
        user_id=current_user.id,
        accion='editar_usuario',
        recurso='user',
        recurso_id=user_id,
        detalle=data,
        ip=request.remote_addr,
    )
    db.session.commit()
    return jsonify(user.to_dict())


# ── Password reset (Flask-Mail + itsdangerous) ────────────────────────────────

@bp_auth.route('/olvidar-password', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('calendario.view_calendario'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()
        # Siempre mostrar el mismo mensaje para no revelar si el email existe
        if user and user.activo:
            token = generar_token_reset(user.email)
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            enviar_reset_password(user, reset_url)
        flash('Si el email existe en el sistema, recibirás un enlace de restablecimiento.', 'info')
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@bp_auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('calendario.view_calendario'))

    email = verificar_token_reset(token, expiration=3600)
    if not email:
        flash('El enlace es inválido o ha expirado.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Usuario no encontrado.', 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        nueva = request.form.get('password_nueva', '')
        confirmar = request.form.get('password_confirmar', '')
        if len(nueva) < 8:
            flash('La contraseña debe tener al menos 8 caracteres.', 'danger')
        elif nueva != confirmar:
            flash('Las contraseñas no coinciden.', 'danger')
        else:
            user.set_password(nueva)
            AuditLog.registrar(user_id=user.id, accion='reset_password', ip=request.remote_addr)
            db.session.commit()
            flash('Contraseña restablecida. Inicia sesión.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)


# ── API token (PyJWT) ─────────────────────────────────────────────────────────

@bp_auth.route('/api/token', methods=['POST'])
@limiter.limit('10 per minute')
def api_get_token():
    """
    Genera un JWT para acceso programático a la API.
    Body JSON: { "username": "...", "password": "..." }
    Response:  { "token": "...", "expires_in": 3600 }
    """
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    user = User.query.filter(
        (User.username == username) | (User.email == username)
    ).first()

    if not user or not user.activo or not user.check_password(password):
        return jsonify(error='Credenciales incorrectas'), 401

    expires_in = current_app.config.get('JWT_EXPIRATION_SECONDS', 3600)
    token = user.generate_api_token(current_app.config['SECRET_KEY'], expires_in=expires_in)

    AuditLog.registrar(user_id=user.id, accion='api_token_generado', ip=request.remote_addr)
    db.session.commit()

    return jsonify(token=token, expires_in=expires_in, role=user.role)
