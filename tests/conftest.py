import pytest
from app import create_app, db
from app.models import User, Category, Task

@pytest.fixture
def app():
    app = create_app({
        'TESTING': True,
        'CSRF_ENABLED': False,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-secret-key-12345'
    })

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()

@pytest.fixture
def user_a(app):
    with app.app_context():
        user = User(
            username='usera',
            full_name='User Alpha',
            email='usera@example.com'
        )
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id

@pytest.fixture
def user_b(app):
    with app.app_context():
        user = User(
            username='userb',
            full_name='User Beta',
            email='userb@example.com'
        )
        user.set_password('password456')
        db.session.add(user)
        db.session.commit()
        return user.id

@pytest.fixture
def auth_client_a(client, user_a):
    client.post('/api/auth/login', json={
        'email': 'usera@example.com',
        'password': 'password123'
    })
    return client

@pytest.fixture
def auth_client_b(client, user_b):
    # Fresh client for user B
    client.post('/api/auth/login', json={
        'email': 'userb@example.com',
        'password': 'password456'
    })
    return client
