from app.models import User
from app import db

def test_registration_success(client, app):
    res = client.post('/api/auth/signup', json={
        'full_name': 'Jane Doe',
        'email': 'jane@example.com',
        'password': 'securepassword'
    })
    assert res.status_code == 201
    data = res.get_json()
    assert data['ok'] is True
    assert data['data']['email'] == 'jane@example.com'

    # Check password is not plaintext
    with app.app_context():
        user = User.query.filter_by(email='jane@example.com').first()
        assert user is not None
        assert user.password_hash != 'securepassword'
        assert user.check_password('securepassword') is True

def test_registration_duplicate_email(client, user_a):
    res = client.post('/api/auth/signup', json={
        'full_name': 'Another User',
        'email': 'usera@example.com',
        'password': 'password999'
    })
    assert res.status_code == 409
    data = res.get_json()
    assert data['ok'] is False
    assert 'already registered' in data['error']

def test_registration_validation(client):
    # Invalid email
    res = client.post('/api/auth/signup', json={
        'full_name': 'Test',
        'email': 'not-an-email',
        'password': 'validpassword'
    })
    assert res.status_code == 400
    assert res.get_json()['ok'] is False

    # Short password
    res = client.post('/api/auth/signup', json={
        'full_name': 'Test',
        'email': 'test@example.com',
        'password': '123'
    })
    assert res.status_code == 400
    assert 'at least 6 characters' in res.get_json()['error']

def test_login_success(client, user_a):
    res = client.post('/api/auth/login', json={
        'email': 'usera@example.com',
        'password': 'password123'
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['ok'] is True
    assert data['data']['email'] == 'usera@example.com'

def test_login_failure(client, user_a):
    # Wrong password
    res = client.post('/api/auth/login', json={
        'email': 'usera@example.com',
        'password': 'wrongpassword'
    })
    assert res.status_code == 401
    assert res.get_json()['ok'] is False

    # Non-existent email
    res = client.post('/api/auth/login', json={
        'email': 'nobody@example.com',
        'password': 'password123'
    })
    assert res.status_code == 401
    assert res.get_json()['ok'] is False

def test_get_me_authenticated(client, user_a):
    client.post('/api/auth/login', json={
        'email': 'usera@example.com',
        'password': 'password123'
    })
    res = client.get('/api/auth/me')
    assert res.status_code == 200
    data = res.get_json()
    assert data['ok'] is True
    assert data['data']['email'] == 'usera@example.com'

def test_get_me_unauthenticated(client):
    res = client.get('/api/auth/me')
    assert res.status_code == 401
    assert res.get_json()['ok'] is False

def test_logout(client, user_a):
    client.post('/api/auth/login', json={
        'email': 'usera@example.com',
        'password': 'password123'
    })
    res = client.post('/api/auth/logout')
    assert res.status_code == 200
    assert res.get_json()['ok'] is True

    # Now verify unauthenticated
    res_me = client.get('/api/auth/me')
    assert res_me.status_code == 401

def test_protected_web_routes_redirect(client):
    res = client.get('/dashboard')
    assert res.status_code == 302
    assert '/login' in res.headers['Location']

    res = client.get('/tasks')
    assert res.status_code == 302
    assert '/login' in res.headers['Location']
