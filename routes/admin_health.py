"""
Dashboard de salud del sistema — psutil.
Rutas:
  GET /admin/health        → Página HTML con métricas
  GET /api/admin/health    → JSON con métricas (para monitoreo externo)
"""
import os
import psutil
import requests
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, render_template, jsonify, current_app, request
from flask_login import login_required, current_user

from routes.auth import admin_required

bp_health = Blueprint('health', __name__)

_start_time = datetime.utcnow()


def _get_metrics():
    """Recopila métricas del sistema con psutil."""
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    uptime = datetime.utcnow() - _start_time

    return {
        'cpu_percent': cpu,
        'memoria': {
            'total_mb': round(mem.total / 1024 / 1024, 1),
            'usado_mb': round(mem.used / 1024 / 1024, 1),
            'disponible_mb': round(mem.available / 1024 / 1024, 1),
            'porcentaje': mem.percent,
        },
        'disco': {
            'total_gb': round(disk.total / 1024 / 1024 / 1024, 2),
            'usado_gb': round(disk.used / 1024 / 1024 / 1024, 2),
            'libre_gb': round(disk.free / 1024 / 1024 / 1024, 2),
            'porcentaje': disk.percent,
        },
        'uptime': str(uptime).split('.')[0],   # HH:MM:SS
        'uptime_segundos': int(uptime.total_seconds()),
        'timestamp': datetime.utcnow().isoformat(),
        'proceso_pid': os.getpid(),
    }


def _get_db_stats():
    """Estadísticas básicas de la BD."""
    from models import Paciente, Cita, User, Dentista
    try:
        return {
            'pacientes': Paciente.query.filter_by(eliminado=False).count(),
            'citas_hoy': Cita.query.filter(
                Cita.fecha_inicio >= datetime.utcnow().replace(hour=0, minute=0, second=0),
                Cita.fecha_inicio < datetime.utcnow().replace(hour=23, minute=59, second=59),
                Cita.estado != 'cancelada',
            ).count(),
            'usuarios_activos': User.query.filter_by(activo=True).count(),
            'dentistas_activos': Dentista.query.filter_by(activo=True).count(),
        }
    except Exception:
        return {}


# ── Rutas ─────────────────────────────────────────────────────────────────────

@bp_health.route('/admin/health')
@login_required
@admin_required
def health_dashboard():
    metrics = _get_metrics()
    db_stats = _get_db_stats()
    return render_template('admin/health.html', metrics=metrics, db_stats=db_stats)


@bp_health.route('/api/admin/health')
@login_required
@admin_required
def health_api():
    """Endpoint JSON para monitoreo externo o integraciones."""
    metrics = _get_metrics()
    db_stats = _get_db_stats()
    return jsonify(
        status='ok',
        sistema=metrics,
        base_de_datos=db_stats,
    )


@bp_health.route('/api/admin/check-external', methods=['POST'])
@login_required
@admin_required
def check_external():
    """
    Verifica conectividad con una URL externa usando requests.
    Body: { "url": "https://..." }
    """
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    if not url.startswith('https://'):
        return jsonify(error='Solo se permiten URLs HTTPS'), 400

    try:
        resp = requests.get(url, timeout=5, allow_redirects=True)
        return jsonify(
            url=url,
            status_code=resp.status_code,
            ok=resp.ok,
            latencia_ms=round(resp.elapsed.total_seconds() * 1000, 1),
        )
    except requests.Timeout:
        return jsonify(url=url, ok=False, error='Timeout'), 408
    except requests.RequestException as e:
        return jsonify(url=url, ok=False, error=str(e)), 503
