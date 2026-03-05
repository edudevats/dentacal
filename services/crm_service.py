"""Lógica de estados CRM y plantillas de mensajes."""
from models import PlantillaMensaje


def obtener_plantilla_mensaje(tipo: str, variables: dict = None) -> str:
    """Obtiene el contenido de una plantilla y reemplaza {variables}."""
    plantilla = PlantillaMensaje.query.filter_by(tipo=tipo, activo=True).first()
    if not plantilla:
        return f'[Plantilla "{tipo}" no encontrada]'
    texto = plantilla.contenido
    if variables:
        for k, v in variables.items():
            texto = texto.replace(f'{{{k}}}', str(v) if v else '')
    return texto


TRANSICIONES_CRM = {
    # (estado_actual, dias_sin_respuesta) -> nuevo_estado
    'activo': None,  # Requiere lógica especial (días sin cita)
    'seguimiento_1': ('seguimiento_2', 15),
    'seguimiento_2': ('llamada_pendiente', 15),
    'llamada_pendiente': ('perdido', 45),
}
