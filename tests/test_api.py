"""
Automated Integration Test Suite for Task Manager REST API.
Authored by M8 (QA / Docs / Demo).
"""
import pytest
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app, db

@pytest.fixture
def client():
    """Create a clean in-memory test database."""
    test_app = create_app()
    test_app.config['TESTING'] = True
    test_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    test_app.config['WTF_CSRF_ENABLED'] = False

    with test_app.test_client() as client:
        with test_app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()

def test_auth_registration(client):
    """Test user registration endpoint."""
    user_payload = {
        "username": "qa_user",
        "email": "qa@taskflow.local",
        "password": "Password123"
    }
    res = client.post('/api/auth/register', json=user_payload)
    assert res.status_code in [200, 201]

def test_auth_login(client):
    """Test user login endpoint."""
    client.post('/api/auth/register', json={
        "username": "login_user",
        "email": "login@taskflow.local",
        "password": "Password123"
    })
    res = client.post('/api/auth/login', json={
        "email": "login@taskflow.local",
        "password": "Password123"
    })
    assert res.status_code == 200

def test_get_tasks_unauthorized(client):
    """Verify tasks are protected when not logged in."""
    res = client.get('/api/tasks')
    assert res.status_code == 401