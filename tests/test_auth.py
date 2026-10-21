import pytest
from werkzeug.security import check_password_hash

from app import create_app, db
from app.models import User


@pytest.fixture
def client():
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-secret-key',
        'SQLALCHEMY_DATABASE_URI': 'sqlite://',
    })
    with app.app_context():
        db.drop_all()
        db.create_all()

    with app.test_client() as test_client:
        yield test_client

    with app.app_context():
        db.session.remove()
        db.drop_all()


def register(client, username='sample-user', email='sample@example.com',
             password='safe-password'):
    return client.post('/api/auth/register', json={
        'username': username,
        'email': email,
        'password': password,
    })


def login(client, email='sample@example.com', password='safe-password'):
    return client.post('/api/auth/login', json={
        'email': email,
        'password': password,
    })


def test_signup_stores_a_password_hash(client):
    response = register(client)

    assert response.status_code == 201
    with client.application.app_context():
        user = User.query.filter_by(email='sample@example.com').one()
        assert user.password_hash != 'safe-password'
        assert check_password_hash(user.password_hash, 'safe-password')


def test_signup_validates_required_fields_and_duplicate_accounts(client):
    assert client.post('/api/auth/register', json={}).status_code == 400
    assert register(client).status_code == 201
    assert register(client, username='another-user').status_code == 409


def test_login_creates_session_and_current_user_endpoint(client):
    register(client)

    assert login(client).status_code == 200
    response = client.get('/api/auth/me')

    assert response.status_code == 200
    assert response.get_json() == {
        'id': 1,
        'username': 'sample-user',
        'email': 'sample@example.com',
    }
    assert 'password_hash' not in response.get_json()


def test_login_rejects_invalid_credentials(client):
    register(client)

    assert login(client, password='wrong-password').status_code == 401
    assert login(client, email='unknown@example.com').status_code == 401


def test_logout_clears_session(client):
    register(client)
    login(client)

    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/auth/me').status_code == 401


def test_authenticated_user_can_access_existing_task_category_and_stats_routes(client):
    register(client)
    login(client)

    category_response = client.post('/api/categories', json={'name': 'Work'})
    assert category_response.status_code == 201

    task_response = client.post('/api/tasks', json={
        'title': 'Complete report',
        'category_id': category_response.get_json()['id'],
    })
    assert task_response.status_code == 201
    assert len(client.get('/api/tasks').get_json()) == 1
    assert client.get('/api/categories').get_json() == [
        {'id': category_response.get_json()['id'], 'name': 'Work'}
    ]
    assert client.get('/api/stats').get_json()['total'] == 1


@pytest.mark.parametrize('method,path', [
    ('get', '/api/auth/me'),
    ('get', '/api/tasks'),
    ('post', '/api/tasks'),
    ('put', '/api/tasks/1'),
    ('delete', '/api/tasks/1'),
    ('get', '/api/categories'),
    ('post', '/api/categories'),
    ('delete', '/api/categories/1'),
    ('get', '/api/stats'),
])
def test_protected_routes_reject_unauthenticated_requests(client, method, path):
    response = getattr(client, method)(path, json={})

    assert response.status_code == 401
    assert response.get_json() == {'error': 'Unauthorized'}
