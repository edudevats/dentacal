"""
Traduccion de los codigos de error de entrega de Twilio/WhatsApp.

El Status Callback entrega un numero suelto. Recepcion necesita leer el motivo
y saber si puede hacer algo al respecto, asi que cada codigo se traduce a una
frase corta en español.

Referencia: https://www.twilio.com/docs/api/errors
"""

# Orden de avance de los estados de entrega. Twilio no garantiza el orden de
# llegada de los callbacks: manda 'sent' y 'undelivered' con medio segundo de
# diferencia y pueden cruzarse. Un estado nunca retrocede de rango.
RANGO_ESTADO = {
    'accepted': 1,
    'scheduled': 1,
    'queued': 2,
    'sending': 3,
    'sent': 4,
    'delivered': 5,
    'read': 6,
    # Terminales: ganan siempre.
    'failed': 9,
    'undelivered': 9,
}

ESTADOS_NO_ENTREGADO = ('failed', 'undelivered')

DESCRIPCIONES = {
    '63016': ('WhatsApp exige plantilla aprobada fuera de la ventana de 24 h '
              '(el paciente no ha escrito recientemente)'),
    '63015': 'El canal de WhatsApp no admite este tipo de mensaje',
    '63003': 'No se encontro el destinatario de WhatsApp',
    '63005': 'WhatsApp bloqueo el mensaje por politica de contenido',
    '63007': 'El numero del consultorio no tiene un perfil de WhatsApp valido',
    '63024': 'Parametros invalidos en la plantilla de WhatsApp',
    '63018': 'Limite de mensajes de WhatsApp excedido por ahora',
    '63021': 'El paciente bloqueo al consultorio en WhatsApp',
    '63032': 'El paciente aun no acepta recibir mensajes del consultorio',
    '21211': 'El numero de destino no es valido',
    '21610': 'El paciente pidio dejar de recibir mensajes (respondio STOP)',
    '21614': 'El numero no puede recibir mensajes',
    '30003': 'El telefono del destinatario esta apagado o inalcanzable',
    '30005': 'El numero de destino no existe',
    '30006': 'El numero es fijo o no admite mensajes',
    '30007': 'La operadora marco el mensaje como spam',
}


def avanza(estado_actual, estado_nuevo):
    """
    True si ``estado_nuevo`` debe reemplazar a ``estado_actual``.

    Un callback que llega tarde no puede borrar un rechazo ya registrado.
    """
    if not estado_nuevo:
        return False
    if not estado_actual:
        return True
    return RANGO_ESTADO.get(estado_nuevo, 0) >= RANGO_ESTADO.get(estado_actual, 0)


def es_no_entregado(estado):
    return estado in ESTADOS_NO_ENTREGADO


def descripcion(codigo, respaldo=''):
    """Motivo legible del codigo, o ``respaldo`` si el codigo es desconocido."""
    if not codigo:
        return respaldo or ''
    texto = DESCRIPCIONES.get(str(codigo).strip())
    if texto:
        return texto
    return respaldo or f'Error {codigo} de Twilio'
