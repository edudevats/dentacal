"""
Servicio de correo electrónico usando Flask-Mail.
Funciones:
  - Confirmación de cita
  - Restablecimiento de contraseña
  - Recordatorio de cita
"""
from flask import current_app, render_template_string
from flask_mail import Message
from extensions import mail
from itsdangerous import URLSafeTimedSerializer


# ── Generación de tokens seguros ──────────────────────────────────────────────

def _get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def generar_token_reset(email):
    """Genera un token firmado para restablecer contraseña."""
    s = _get_serializer()
    return s.dumps(email, salt='password-reset')


def verificar_token_reset(token, expiration=3600):
    """Verifica el token de reset. Retorna email o None si inválido/expirado."""
    s = _get_serializer()
    try:
        email = s.loads(token, salt='password-reset', max_age=expiration)
        return email
    except Exception:
        return None


# ── Envío de emails ───────────────────────────────────────────────────────────

def _send(subject, recipients, html_body, text_body=None):
    """Envía un email. Silencia errores para no romper el flujo principal."""
    if not isinstance(recipients, list):
        recipients = [recipients]
    msg = Message(
        subject=subject,
        recipients=recipients,
        html=html_body,
        body=text_body or '',
    )
    try:
        mail.send(msg)
        current_app.logger.info(f'[Mail] Enviado: "{subject}" → {recipients}')
        return True
    except Exception as e:
        current_app.logger.error(f'[Mail] Error al enviar "{subject}": {e}')
        return False


def enviar_reset_password(user, reset_url):
    """Email de restablecimiento de contraseña."""
    html = render_template_string(
        TMPL_RESET_PASSWORD,
        nombre=user.username,
        reset_url=reset_url,
        consultorio=current_app.config.get('CONSULTORIO_NOMBRE', 'La Casa del Sr. Pérez'),
    )
    return _send(
        subject='Restablece tu contraseña — La Casa del Sr. Pérez',
        recipients=user.email,
        html_body=html,
    )


def enviar_confirmacion_cita(cita, email_destino):
    """Email de confirmación de cita al paciente."""
    from services.timezone_utils import format_mexico
    html = render_template_string(
        TMPL_CONFIRMACION_CITA,
        paciente=cita.paciente.nombre if cita.paciente else 'Paciente',
        dentista=cita.dentista.nombre if cita.dentista else '',
        consultorio_nombre=cita.consultorio.nombre if cita.consultorio else '',
        tipo_cita=cita.tipo_cita.nombre if cita.tipo_cita else '',
        fecha_hora=format_mexico(cita.fecha_inicio, '%A %d de %B de %Y a las %H:%M'),
        nombre_consultorio=current_app.config.get('CONSULTORIO_NOMBRE', 'La Casa del Sr. Pérez'),
        telefono=current_app.config.get('CONSULTORIO_TELEFONO', ''),
    )
    return _send(
        subject='Confirmación de cita dental',
        recipients=email_destino,
        html_body=html,
    )


def enviar_recordatorio_cita(cita, email_destino):
    """Email de recordatorio 24h antes de la cita."""
    from services.timezone_utils import format_mexico
    html = render_template_string(
        TMPL_RECORDATORIO,
        paciente=cita.paciente.nombre if cita.paciente else 'Paciente',
        dentista=cita.dentista.nombre if cita.dentista else '',
        fecha_hora=format_mexico(cita.fecha_inicio, '%A %d de %B a las %H:%M'),
        nombre_consultorio=current_app.config.get('CONSULTORIO_NOMBRE', 'La Casa del Sr. Pérez'),
        telefono=current_app.config.get('CONSULTORIO_TELEFONO', ''),
    )
    return _send(
        subject='Recordatorio: tu cita es mañana',
        recipients=email_destino,
        html_body=html,
    )


# ── Plantillas inline HTML ────────────────────────────────────────────────────

TMPL_RESET_PASSWORD = """
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px;color:#333;">
  <div style="text-align:center;margin-bottom:20px;">
    <span style="font-size:2.5rem;">🦷</span>
    <h2 style="color:#0d6efd;margin:8px 0;">{{ consultorio }}</h2>
  </div>
  <h3>Hola, {{ nombre }}</h3>
  <p>Recibimos una solicitud para restablecer la contraseña de tu cuenta.</p>
  <p style="text-align:center;margin:30px 0;">
    <a href="{{ reset_url }}"
       style="background:#0d6efd;color:#fff;padding:12px 28px;border-radius:6px;
              text-decoration:none;font-weight:bold;display:inline-block;">
      Restablecer contraseña
    </a>
  </p>
  <p style="color:#666;font-size:0.9rem;">
    Este enlace expira en <strong>1 hora</strong>. Si no solicitaste este cambio, ignora este mensaje.
  </p>
  <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
  <p style="color:#999;font-size:0.8rem;text-align:center;">
    {{ consultorio }} · Sistema Recepcionista Virtual
  </p>
</body>
</html>
"""

TMPL_CONFIRMACION_CITA = """
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px;color:#333;">
  <div style="text-align:center;margin-bottom:20px;">
    <span style="font-size:2.5rem;">🦷</span>
    <h2 style="color:#0d6efd;margin:8px 0;">{{ nombre_consultorio }}</h2>
  </div>
  <h3>Confirmación de cita</h3>
  <p>Hola <strong>{{ paciente }}</strong>,</p>
  <p>Tu cita ha sido confirmada con los siguientes detalles:</p>
  <table style="width:100%;border-collapse:collapse;margin:16px 0;">
    <tr style="background:#f8f9fa;">
      <td style="padding:10px;border:1px solid #dee2e6;font-weight:bold;">Fecha y hora</td>
      <td style="padding:10px;border:1px solid #dee2e6;">{{ fecha_hora }}</td>
    </tr>
    <tr>
      <td style="padding:10px;border:1px solid #dee2e6;font-weight:bold;">Doctor/a</td>
      <td style="padding:10px;border:1px solid #dee2e6;">{{ dentista }}</td>
    </tr>
    <tr style="background:#f8f9fa;">
      <td style="padding:10px;border:1px solid #dee2e6;font-weight:bold;">Consultorio</td>
      <td style="padding:10px;border:1px solid #dee2e6;">{{ consultorio_nombre }}</td>
    </tr>
    <tr>
      <td style="padding:10px;border:1px solid #dee2e6;font-weight:bold;">Tipo de cita</td>
      <td style="padding:10px;border:1px solid #dee2e6;">{{ tipo_cita }}</td>
    </tr>
  </table>
  <p>Si necesitas reagendar o cancelar, contáctanos al <strong>{{ telefono }}</strong>.</p>
  <p>¡Hasta pronto! 😊</p>
  <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
  <p style="color:#999;font-size:0.8rem;text-align:center;">{{ nombre_consultorio }}</p>
</body>
</html>
"""

TMPL_RECORDATORIO = """
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:20px;color:#333;">
  <div style="text-align:center;margin-bottom:20px;">
    <span style="font-size:2.5rem;">🦷</span>
    <h2 style="color:#0d6efd;margin:8px 0;">{{ nombre_consultorio }}</h2>
  </div>
  <h3>Recordatorio de cita 🗓️</h3>
  <p>Hola <strong>{{ paciente }}</strong>,</p>
  <p>Te recordamos que mañana tienes cita con <strong>{{ dentista }}</strong>.</p>
  <p style="font-size:1.1rem;font-weight:bold;color:#0d6efd;">📅 {{ fecha_hora }}</p>
  <p>Si necesitas cancelar o reagendar, por favor avísanos con anticipación al <strong>{{ telefono }}</strong>.</p>
  <p>¡Te esperamos! 😊</p>
  <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
  <p style="color:#999;font-size:0.8rem;text-align:center;">{{ nombre_consultorio }}</p>
</body>
</html>
"""
