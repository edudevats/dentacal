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
    # 63024 es "Invalid message recipient": Meta no reconoce el numero de
    # destino como usuario de WhatsApp. NO tiene nada que ver con las
    # variables de la plantilla, aunque el nombre del codigo lo sugiera.
    '63024': ('El numero de destino no tiene WhatsApp activo (o no acepto los '
              'terminos de WhatsApp)'),
    '63018': 'Limite de mensajes de WhatsApp excedido por ahora',
    '63038': 'La cuenta de Twilio agoto su limite de mensajes del dia',
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


# Errores que Twilio devuelve al CREAR el mensaje (HTTP 4xx), antes de que
# WhatsApp llegue a verlo. Son otra familia distinta de los de entrega de
# arriba: aqui el mensaje ni siquiera salio.
ERRORES_ENVIO = {
    21656: ('La plantilla aprobada no coincide con lo que manda la app: '
            'revise cuantas variables ({{1}}, {{2}}...) tiene registrada en '
            'Twilio y el orden guardado en Configuracion > Plantillas'),
    21617: ('El mensaje es mas largo de lo que WhatsApp acepta '
            '(1024 caracteres en una plantilla)'),
    63016: ('WhatsApp exige plantilla aprobada fuera de la ventana de 24 h '
            '(el destinatario no ha escrito recientemente)'),
    20003: 'Twilio rechazo las credenciales del consultorio',
    21211: 'El numero de destino no es valido',
    63038: ('La cuenta de Twilio agoto su limite de mensajes del dia. No se '
            'puede enviar nada mas hasta que la cuota se reinicie. El tope se '
            'levanta desde la consola de Twilio, no desde la app'),
}

# 63038 es un tope DIARIO de la cuenta: reintentar en minutos no sirve de nada,
# hay que esperar a que la cuota se reinicie. Distinto de 63018, que es
# throttling momentaneo y si se beneficia del backoff normal.
CODIGOS_CUOTA = {63038}


def es_limite_de_cuota(error):
    """True si Twilio rechazo el envio por tope de mensajes, no por el mensaje."""
    codigo = getattr(error, 'code', None)
    if codigo in CODIGOS_CUOTA:
        return True
    return any(str(c) in str(error) for c in CODIGOS_CUOTA)


def motivo_envio(error):
    """
    Frase en español para una excepcion de Twilio al crear el mensaje.

    Recepcion ve este texto en la alerta del boton de envio, asi que tiene que
    decir que hacer, no repetir el ingles de Twilio.
    """
    codigo = getattr(error, 'code', None)
    texto = ERRORES_ENVIO.get(codigo)
    if texto:
        return f'{texto} (error {codigo} de Twilio)'
    if codigo:
        return f'{error} (error {codigo} de Twilio)'
    return str(error)


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
