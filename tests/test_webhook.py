import pytest


def test_webhook_returns_xml(app):
    """El webhook debe responder con TwiML XML o 200."""
    with app.test_client() as client:
        resp = client.post('/webhook/whatsapp', data={
            'Body': 'Hola',
            'From': 'whatsapp:+5215512345678',
        })
        assert resp.status_code == 200


def test_webhook_empty_body(app):
    """Webhook con body vacio debe responder 200 sin crash."""
    with app.test_client() as client:
        resp = client.post('/webhook/whatsapp', data={
            'Body': '',
            'From': 'whatsapp:+5215512345678',
        })
        assert resp.status_code == 200
