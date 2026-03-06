from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db, limiter
from models import User, RolUsuario, AuditLog

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        user = User.query.filter_by(username=username, activo=True).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            _audit(user.id, 'login', ip=request.remote_addr)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.dashboard'))
        else:
            error = 'Usuario o contrasena incorrectos.'

    return render_template('auth/login.html', error=error)


@auth_bp.route('/logout')
@login_required
def logout():
    _audit(current_user.id, 'logout', ip=request.remote_addr)
    logout_user()
    flash('Sesion cerrada correctamente.', 'success')
    return redirect(url_for('auth.login'))


@auth_bp.route('/cambiar-password', methods=['GET', 'POST'])
@login_required
def cambiar_password():
    error = None
    success = False
    if request.method == 'POST':
        actual = request.form.get('password_actual', '')
        nueva = request.form.get('password_nueva', '')
        confirmar = request.form.get('confirmar', '')

        if not current_user.check_password(actual):
            error = 'La contrasena actual es incorrecta.'
        elif len(nueva) < 8:
            error = 'La nueva contrasena debe tener al menos 8 caracteres.'
        elif nueva != confirmar:
            error = 'Las contrasenas no coinciden.'
        else:
            current_user.set_password(nueva)
            db.session.commit()
            _audit(current_user.id, 'cambiar_password', ip=request.remote_addr)
            success = True

    return render_template('auth/change_password.html', error=error, success=success)


@auth_bp.route('/admin/usuarios')
@login_required
def admin_usuarios():
    if not current_user.is_admin():
        flash('No tienes permisos para esta seccion.', 'danger')
        return redirect(url_for('main.dashboard'))
    usuarios = User.query.order_by(User.created_at.desc()).all()
    return render_template('auth/usuarios.html', usuarios=usuarios)


@auth_bp.route('/admin/usuarios/crear', methods=['POST'])
@login_required
def crear_usuario():
    if not current_user.is_admin():
        from flask import jsonify
        return jsonify(error='Sin permisos'), 403

    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    rol = request.form.get('rol', 'recepcionista')

    if not all([username, email, password]):
        flash('Todos los campos son requeridos.', 'danger')
        return redirect(url_for('auth.admin_usuarios'))

    if User.query.filter_by(username=username).first():
        flash(f'El usuario {username} ya existe.', 'danger')
        return redirect(url_for('auth.admin_usuarios'))

    try:
        rol_enum = RolUsuario[rol]
    except KeyError:
        rol_enum = RolUsuario.recepcionista

    user = User(username=username, email=email, rol=rol_enum)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    _audit(current_user.id, 'crear_usuario', tabla='users', registro_id=user.id)
    flash(f'Usuario {username} creado correctamente.', 'success')
    return redirect(url_for('auth.admin_usuarios'))


@auth_bp.route('/admin/usuarios/<int:user_id>/toggle', methods=['POST'])
@login_required
def toggle_usuario(user_id):
    if not current_user.is_admin():
        from flask import jsonify
        return jsonify(error='Sin permisos'), 403
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('No puedes desactivarte a ti mismo.', 'danger')
        return redirect(url_for('auth.admin_usuarios'))
    user.activo = not user.activo
    db.session.commit()
    estado = 'activado' if user.activo else 'desactivado'
    flash(f'Usuario {user.username} {estado}.', 'success')
    return redirect(url_for('auth.admin_usuarios'))


def _audit(user_id, accion, tabla=None, registro_id=None, ip=None):
    try:
        log = AuditLog(user_id=user_id, accion=accion,
                       tabla=tabla, registro_id=registro_id,
                       ip_address=ip)
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()
