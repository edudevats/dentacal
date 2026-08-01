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
