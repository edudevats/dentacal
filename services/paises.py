"""
Catalogo de paises soportados para el numero telefonico de los doctores
y helper para formatear a E.164 (formato que Twilio/WhatsApp requiere).
"""
import re

PAISES = {
    'MX': {'prefijo': '52',  'nombre': 'México'},
    'US': {'prefijo': '1',   'nombre': 'Estados Unidos'},
    'ES': {'prefijo': '34',  'nombre': 'España'},
    'CO': {'prefijo': '57',  'nombre': 'Colombia'},
    'AR': {'prefijo': '54',  'nombre': 'Argentina'},
    'GT': {'prefijo': '502', 'nombre': 'Guatemala'},
    'PE': {'prefijo': '51',  'nombre': 'Perú'},
    'CL': {'prefijo': '56',  'nombre': 'Chile'},
}

PAIS_DEFAULT = 'MX'


def formatear_numero_e164(telefono, pais='MX'):
    """
    Construye un numero E.164 (+<codigo><numero>) a partir del numero local
    y el pais del doctor. Retorna None si no hay numero utilizable.

    Mexico es especial: WhatsApp/Twilio exige el '1' de movil -> +521XXXXXXXXXX.
    """
    if not telefono or not telefono.strip():
        return None

    pais = (pais or PAIS_DEFAULT).upper()
    info = PAISES.get(pais, PAISES[PAIS_DEFAULT])
    prefijo = info['prefijo']

    tiene_plus = telefono.strip().startswith('+')
    digitos = re.sub(r'\D', '', telefono)
    if not digitos:
        return None

    if pais == 'MX' or info is PAISES['MX']:
        if digitos.startswith('521') and len(digitos) == 13:
            local = digitos[3:]
        elif digitos.startswith('52') and len(digitos) == 12:
            local = digitos[2:]
        elif len(digitos) == 10:
            local = digitos
        else:
            local = digitos[-10:]
        return f'+521{local}'

    # NOTA: solo Mexico tiene manejo especial del prefijo movil (+521). Otros
    # paises con "trunk" movil (p.ej. Argentina +549) se formatean como +54...;
    # si se onboardan doctores de esos paises, agregar su caso aqui.
    if tiene_plus or digitos.startswith(prefijo):
        return f'+{digitos}'
    return f'+{prefijo}{digitos}'


# ── Normalizacion del WhatsApp de pacientes ─────────────────────────────────
#
# La BD trae tres formas conviviendo (conteo sobre 1642 fichas con numero):
#   1071  +521XXXXXXXXXX   <- la forma canonica, la misma que Twilio usa al
#                              entregar los mensajes entrantes
#    560  +52XXXXXXXXXX    <- entrega bien tambien; NO se toca
#      ~7  basura (9 digitos, 20 digitos, vacio con espacios...)
#
# `normalizar_whatsapp` solo arregla lo que le falta el codigo de pais. Un
# numero que ya es E.164 valido se deja intacto: reescribir 560 destinos que
# hoy funcionan es un riesgo que no compra nada. Y un numero que no se puede
# salvar con certeza se devuelve como esta, para que Twilio lo rechace de
# forma visible (21211) en vez de que adivinemos y le mandemos los datos de
# una cita a un desconocido.

def _solo_digitos(numero):
    return re.sub(r'\D', '', numero or '')


def es_e164_valido(numero):
    """True si el numero ya viene en E.164 utilizable por Twilio."""
    if not numero or not numero.strip().startswith('+'):
        return False
    return 11 <= len(_solo_digitos(numero)) <= 15


def normalizar_whatsapp(numero):
    """
    Deja el numero de WhatsApp listo para Twilio sin adivinar.

    - Ya es E.164 valido      -> se devuelve limpio, sin cambios de fondo.
    - 10 digitos pelones      -> movil mexicano: +521XXXXXXXXXX.
    - 52/521 sin el '+'       -> se le pone el '+'.
    - Cualquier otra cosa     -> se devuelve limpio y sin tocar.

    Devuelve el valor original si viene vacio o None.
    """
    if not numero or not numero.strip():
        return numero

    limpio = (numero.replace('whatsapp:', '')
                    .replace(' ', '').replace('-', '')
                    .replace('(', '').replace(')', '')
                    .strip())

    if es_e164_valido(limpio):
        return limpio

    digitos = _solo_digitos(limpio)

    # Si ya trae '+' pero no es E.164 valido, esta roto de origen y no hay
    # nada que deducir: '+5212345678' no es "10 digitos mexicanos", es un
    # numero mal capturado. Anteponerle otro '+521' inventaria un destino.
    if limpio.startswith('+'):
        return limpio

    # El caso que se vio en produccion: "5549527650" salio a Twilio pelon.
    if len(digitos) == 10:
        return f'+521{digitos}'

    if len(digitos) == 13 and digitos.startswith('521'):
        return f'+{digitos}'

    if len(digitos) == 12 and digitos.startswith('52'):
        return f'+{digitos}'

    # No hay forma de saber que quiso decir. Que falle a la vista.
    return limpio
