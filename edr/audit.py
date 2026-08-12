import json

from flask import request
from flask_login import current_user

from models import AuditLog


def record_audit(accion, tabla, registro_id, before, after):
    """Construye la fila de auditoría para añadirla a la transacción actual."""
    return AuditLog(
        user_id=current_user.id,
        accion=accion,
        tabla=tabla,
        registro_id=registro_id,
        datos_anteriores=json.dumps(
            before, ensure_ascii=False, default=str
        ),
        datos_nuevos=json.dumps(after, ensure_ascii=False, default=str),
        ip_address=request.remote_addr,
    )
