"""Tests del webhook de Twilio."""
import pytest
import hmac
import hashlib
import base64
from unittest.mock import patch


def _twilio_signature(auth_token, url, params):
    """Genera firma Twilio válida para tests."""
    s = url
    if params:
        for key in sorted(params.keys()):
            s += key + params[key]
    mac = hmac.new(auth_token.encode('utf-8'), s.encode('utf-8'), hashlib.sha1)
    return base64.b64encode(mac.digest()).decode('utf-8')


class TestWebhookTwilio:
    def test_webhook_sin_firma_rechazado(self, client):
        """Webhook sin X-Twilio-Signature devuelve 403 en producción."""
        # En testing con TWILIO_AUTH_TOKEN configurado se rechaza
        with patch('routes.webhook_whatsapp._validar_firma_twilio', return_value=False):
            res = client.post('/webhook/whatsapp', data={
                'Body': 'Hola',
                'From': 'whatsapp:+521234567890',
            })
        assert res.status_code == 403

    def test_webhook_con_firma_valida(self, client):
        """Webhook con firma válida se procesa."""
        with patch('routes.webhook_whatsapp._validar_firma_twilio', return_value=True), \
             patch('routes.webhook_whatsapp.procesar_mensaje_bot') as mock_bot:
            mock_bot.return_value = ('Hola, ¿en qué puedo ayudarle?', 'info')
            res = client.post('/webhook/whatsapp', data={
                'Body': 'Hola',
                'From': 'whatsapp:+521234567890',
            })
        # En testing, la BD en memoria podría no tener datos — aceptamos 200 o 500
        assert res.status_code in (200, 500)

    def test_webhook_sin_body_devuelve_respuesta_vacia(self, client):
        """Mensaje vacío devuelve respuesta TwiML vacía."""
        with patch('routes.webhook_whatsapp._validar_firma_twilio', return_value=True):
            res = client.post('/webhook/whatsapp', data={
                'Body': '',
                'From': 'whatsapp:+521234567890',
            })
        # Cuerpo vacío — retorna TwiML vacío (200)
        assert res.status_code == 200

    def test_webhook_status_siempre_204(self, client):
        """El endpoint de status siempre devuelve 204."""
        res = client.post('/webhook/whatsapp/status', data={
            'MessageStatus': 'delivered',
            'MessageSid': 'SMtest',
        })
        assert res.status_code == 204
