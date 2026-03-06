import pytest
import os
os.environ['FLASK_ENV'] = 'testing'

from app import create_app
from extensions import db as _db
from models import User, RolUsuario


@pytest.fixture(scope='session')
def app():
    app = create_app('testing')
    with app.app_context():
        _db.create_all()
        yield app
        _db.drop_all()


@pytest.fixture(scope='session')
def db(app):
    return _db


@pytest.fixture(scope='function')
def client(app):
    return app.test_client()


@pytest.fixture(scope='function')
def admin_client(app, client):
    """Client autenticado como admin."""
    with app.app_context():
        user = User.query.filter_by(username='test_admin').first()
        if not user:
            user = User(username='test_admin', email='admin@test.com', rol=RolUsuario.admin)
            user.set_password('Test1234!')
            _db.session.add(user)
            _db.session.commit()

    client.post('/login', data={
        'username': 'test_admin',
        'password': 'Test1234!',
        'csrf_token': _get_csrf(client),
    })
    return client


def _get_csrf(client):
    resp = client.get('/login')
    from flask_wtf.csrf import generate_csrf
    with client.application.test_request_context():
        return generate_csrf()
