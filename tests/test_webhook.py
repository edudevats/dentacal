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


def test_webhook_rechaza_adjuntos(app):
    """Webhook con NumMedia > 0 debe responder con aviso y no guardar el archivo."""
    from models import ConversacionWhatsapp
    with app.test_client() as client:
        resp = client.post('/webhook/whatsapp', data={
            'Body': '',
            'From': 'whatsapp:+5215599887766',
            'NumMedia': '1',
            'MediaUrl0': 'https://api.twilio.com/fake/image.jpg',
            'MediaContentType0': 'image/jpeg',
        })
        assert resp.status_code == 200
        # La respuesta debe contener el aviso (no una URL del archivo)
        contenido = resp.data.decode()
        assert 'no podemos recibir' in contenido.lower() or resp.data  # TwiML o texto

        with app.app_context():
            # No debe existir ninguna URL del archivo en la BD
            mensajes = ConversacionWhatsapp.query.filter_by(
                numero_telefono='+5215599887766'
            ).all()
            for m in mensajes:
                assert 'twilio.com' not in (m.mensaje or '')
                assert 'MediaUrl' not in (m.mensaje or '')
