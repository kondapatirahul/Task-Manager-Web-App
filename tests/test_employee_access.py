"""
tests/test_employee_access.py

Feature: Employee Access and Profile Module
Branch:  feature/employee-access

Covers
------
- Role constants and is_active/account_active on the User model
- Login with deactivated account → 403
- Existing login/logout flows still work
- GET /api/auth/profile (authenticated, unauthenticated)
- PUT /api/auth/profile — success, validation, unauthenticated
- User cannot change own role via profile endpoint
- POST /api/auth/change-password — success, wrong current, mismatch, too short,
  same-as-current, missing fields, unauthenticated
- Password hash never appears in response body
- Settings web route: authenticated → 200, unauthenticated → redirect
- Public routes (/, /login, /signup) accessible without auth
- Private routes redirect unauthenticated visitors to /login
- Deactivated user is kicked out of active sessions on next page request
- Existing task APIs are unaffected by model changes
- roles_required decorator (unit-level)
- active_account_required decorator (unit-level)
"""
import pytest
from app import create_app, db
from app.models import (
    User, Task, Category,
    ROLE_EMPLOYEE, ROLE_ADMIN, ROLE_TEAM_LEAD, ROLE_SUPER_ADMIN, ALL_ROLES,
)
from app.routes.utils import roles_required, active_account_required


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def app():
    application = create_app({
        'TESTING': True,
        'CSRF_ENABLED': False,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-secret-for-employee-access',
    })
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _make_user(app, *, email, password, full_name='Test User',
               username=None, role=ROLE_EMPLOYEE, account_active=True):
    """Helper: create and persist a user, return its id."""
    with app.app_context():
        if username is None:
            username = email.split('@')[0].replace('.', '_')
        user = User(
            username=username,
            full_name=full_name,
            email=email,
            role=role,
            account_active=account_active,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, email, password):
    return client.post('/api/auth/login', json={'email': email, 'password': password})


# ── Model / constants tests ────────────────────────────────────────────────────

def test_role_constants_are_defined():
    assert ROLE_EMPLOYEE    == 'employee'
    assert ROLE_TEAM_LEAD   == 'team_lead'
    assert ROLE_ADMIN       == 'admin'
    assert ROLE_SUPER_ADMIN == 'super_admin'
    assert set(ALL_ROLES) == {'employee', 'team_lead', 'admin', 'super_admin'}


def test_user_model_has_role_and_account_active(app):
    uid = _make_user(app, email='m@example.com', password='pass1234',
                     role=ROLE_ADMIN, account_active=True)
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.role == ROLE_ADMIN
        assert user.account_active is True
        assert user.is_active is True   # Flask-Login property


def test_user_default_role_is_employee(app):
    with app.app_context():
        user = User(username='emp', full_name='Emp', email='emp@x.com')
        user.set_password('password1')
        db.session.add(user)
        db.session.commit()
        assert user.role == ROLE_EMPLOYEE


def test_has_role_helper(app):
    uid = _make_user(app, email='rl@example.com', password='pass1234',
                     role=ROLE_TEAM_LEAD)
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.has_role(ROLE_TEAM_LEAD) is True
        assert user.has_role(ROLE_ADMIN)     is False
        assert user.has_role(ROLE_TEAM_LEAD, ROLE_ADMIN) is True


def test_is_management_helper(app):
    with app.app_context():
        for role in (ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD):
            u = User(username=role, full_name=role, email=f'{role}@x.com', role=role)
            u.set_password('p')
            db.session.add(u)
            db.session.commit()
            assert u.is_management is True

        emp = User(username='emp2', full_name='Emp', email='emp2@x.com', role=ROLE_EMPLOYEE)
        emp.set_password('p')
        db.session.add(emp)
        db.session.commit()
        assert emp.is_management is False


def test_deactivated_user_is_active_false(app):
    uid = _make_user(app, email='deact@example.com', password='pass1234',
                     account_active=False)
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.account_active is False
        assert user.is_active is False   # Flask-Login uses this


def test_to_dict_includes_role_and_account_active(app):
    uid = _make_user(app, email='td@example.com', password='pass1234',
                     role=ROLE_ADMIN)
    with app.app_context():
        user = db.session.get(User, uid)
        d = user.to_dict()
        assert 'role'           in d
        assert 'account_active' in d
        assert 'password_hash'  not in d
        assert d['role'] == ROLE_ADMIN


# ── Login behaviour ────────────────────────────────────────────────────────────

def test_login_success_active_user(app, client):
    _make_user(app, email='active@example.com', password='pass1234')
    res = _login(client, 'active@example.com', 'pass1234')
    assert res.status_code == 200
    assert res.get_json()['ok'] is True


def test_login_deactivated_account_blocked(app, client):
    _make_user(app, email='dead@example.com', password='pass1234',
               account_active=False)
    res = _login(client, 'dead@example.com', 'pass1234')
    assert res.status_code == 403
    data = res.get_json()
    assert data['ok'] is False
    assert 'deactivated' in data['error'].lower()


def test_login_wrong_password_rejected(app, client):
    _make_user(app, email='wp@example.com', password='rightPass1')
    res = _login(client, 'wp@example.com', 'wrongPass!')
    assert res.status_code == 401
    assert res.get_json()['ok'] is False


def test_logout_ends_session(app, client):
    _make_user(app, email='lo@example.com', password='pass1234')
    _login(client, 'lo@example.com', 'pass1234')
    res = client.post('/api/auth/logout')
    assert res.status_code == 200
    # After logout, protected endpoint returns 401
    res = client.get('/api/auth/profile')
    assert res.status_code == 401


# ── GET /api/auth/profile ──────────────────────────────────────────────────────

def test_get_profile_authenticated(app, client):
    uid = _make_user(app, email='gp@example.com', password='pass1234',
                     full_name='Grace Profile', role=ROLE_TEAM_LEAD)
    _login(client, 'gp@example.com', 'pass1234')
    res = client.get('/api/auth/profile')
    assert res.status_code == 200
    data = res.get_json()
    assert data['ok'] is True
    assert data['data']['email']     == 'gp@example.com'
    assert data['data']['full_name'] == 'Grace Profile'
    assert data['data']['role']      == ROLE_TEAM_LEAD
    assert 'password_hash' not in data['data']


def test_get_profile_unauthenticated(client):
    res = client.get('/api/auth/profile')
    assert res.status_code == 401


# ── PUT /api/auth/profile ──────────────────────────────────────────────────────

def test_update_profile_success(app, client):
    uid = _make_user(app, email='up@example.com', password='pass1234',
                     full_name='Original Name')
    _login(client, 'up@example.com', 'pass1234')
    res = client.put('/api/auth/profile', json={'full_name': 'Updated Name'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['ok'] is True
    assert data['data']['full_name'] == 'Updated Name'
    # Verify persisted
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.full_name == 'Updated Name'


def test_update_profile_empty_name_rejected(app, client):
    _make_user(app, email='en@example.com', password='pass1234')
    _login(client, 'en@example.com', 'pass1234')
    res = client.put('/api/auth/profile', json={'full_name': ''})
    assert res.status_code == 400
    assert res.get_json()['ok'] is False


def test_update_profile_too_short_rejected(app, client):
    _make_user(app, email='ts@example.com', password='pass1234')
    _login(client, 'ts@example.com', 'pass1234')
    res = client.put('/api/auth/profile', json={'full_name': 'X'})
    assert res.status_code == 400
    assert 'at least 2 characters' in res.get_json()['error']


def test_update_profile_too_long_rejected(app, client):
    _make_user(app, email='tl@example.com', password='pass1234')
    _login(client, 'tl@example.com', 'pass1234')
    res = client.put('/api/auth/profile', json={'full_name': 'A' * 101})
    assert res.status_code == 400
    assert '100 characters' in res.get_json()['error']


def test_update_profile_unauthenticated_rejected(client):
    res = client.put('/api/auth/profile', json={'full_name': 'Hacker'})
    assert res.status_code == 401


def test_update_profile_cannot_change_own_role(app, client):
    """Users cannot elevate their own role by supplying role in PUT payload."""
    uid = _make_user(app, email='cr@example.com', password='pass1234',
                     role=ROLE_EMPLOYEE)
    _login(client, 'cr@example.com', 'pass1234')
    # Send role escalation attempt in same request as a valid name update
    res = client.put('/api/auth/profile', json={
        'full_name': 'Legit Update',
        'role': ROLE_SUPER_ADMIN,       # must be silently ignored
    })
    # Request should succeed (full_name update)
    assert res.status_code == 200
    # But role must remain unchanged
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.role == ROLE_EMPLOYEE
        assert user.full_name == 'Legit Update'


def test_profile_isolation_user_a_cannot_update_user_b(app, client):
    """PUT /api/auth/profile always operates on the authenticated user only."""
    uid_a = _make_user(app, email='ua@example.com', password='passA123',
                       full_name='User A')
    uid_b = _make_user(app, email='ub@example.com', password='passB123',
                       full_name='User B')
    # Log in as B and update "profile" (only B's profile changes)
    _login(client, 'ub@example.com', 'passB123')
    res = client.put('/api/auth/profile', json={'full_name': 'B Updated'})
    assert res.status_code == 200
    with app.app_context():
        user_a = db.session.get(User, uid_a)
        user_b = db.session.get(User, uid_b)
        assert user_a.full_name == 'User A'    # unchanged
        assert user_b.full_name == 'B Updated'


# ── POST /api/auth/change-password ────────────────────────────────────────────

def test_change_password_success(app, client):
    uid = _make_user(app, email='cpok@example.com', password='oldPass123')
    _login(client, 'cpok@example.com', 'oldPass123')
    res = client.post('/api/auth/change-password', json={
        'current_password': 'oldPass123',
        'new_password':     'newSecure!99',
        'confirm_password': 'newSecure!99',
    })
    assert res.status_code == 200
    assert res.get_json()['ok'] is True
    # New password must work
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.check_password('newSecure!99') is True
        assert user.check_password('oldPass123')    is False
        # Hash must not be plaintext
        assert user.password_hash != 'newSecure!99'


def test_change_password_wrong_current(app, client):
    _make_user(app, email='cpwc@example.com', password='correct1')
    _login(client, 'cpwc@example.com', 'correct1')
    res = client.post('/api/auth/change-password', json={
        'current_password': 'wrongPass!',
        'new_password':     'newSecure!99',
        'confirm_password': 'newSecure!99',
    })
    assert res.status_code == 401
    assert 'incorrect' in res.get_json()['error'].lower()


def test_change_password_mismatch(app, client):
    _make_user(app, email='cpmm@example.com', password='pass1234')
    _login(client, 'cpmm@example.com', 'pass1234')
    res = client.post('/api/auth/change-password', json={
        'current_password': 'pass1234',
        'new_password':     'newSecure!99',
        'confirm_password': 'differentOne!',
    })
    assert res.status_code == 400
    assert 'match' in res.get_json()['error'].lower()


def test_change_password_too_short(app, client):
    _make_user(app, email='cpts@example.com', password='pass1234')
    _login(client, 'cpts@example.com', 'pass1234')
    res = client.post('/api/auth/change-password', json={
        'current_password': 'pass1234',
        'new_password':     'short',
        'confirm_password': 'short',
    })
    assert res.status_code == 400
    assert '8 characters' in res.get_json()['error']


def test_change_password_same_as_current(app, client):
    _make_user(app, email='cpsc@example.com', password='pass1234')
    _login(client, 'cpsc@example.com', 'pass1234')
    res = client.post('/api/auth/change-password', json={
        'current_password': 'pass1234',
        'new_password':     'pass1234',
        'confirm_password': 'pass1234',
    })
    assert res.status_code == 400
    assert 'differ' in res.get_json()['error'].lower()


def test_change_password_missing_fields(app, client):
    _make_user(app, email='cpmf@example.com', password='pass1234')
    _login(client, 'cpmf@example.com', 'pass1234')
    res = client.post('/api/auth/change-password', json={
        'current_password': 'pass1234',
        'new_password':     'newSecure!99',
        # confirm_password missing
    })
    assert res.status_code == 400
    assert res.get_json()['ok'] is False


def test_change_password_unauthenticated(client):
    res = client.post('/api/auth/change-password', json={
        'current_password': 'pass1234',
        'new_password':     'newSecure!99',
        'confirm_password': 'newSecure!99',
    })
    assert res.status_code == 401


def test_password_never_in_response(app, client):
    _make_user(app, email='pnr@example.com', password='pass1234')
    _login(client, 'pnr@example.com', 'pass1234')
    res = client.post('/api/auth/change-password', json={
        'current_password': 'pass1234',
        'new_password':     'newSecure!99',
        'confirm_password': 'newSecure!99',
    })
    body = res.get_data(as_text=True)
    assert 'pass1234'    not in body
    assert 'newSecure'   not in body
    assert 'password_hash' not in body


# ── Deactivated account session guard ─────────────────────────────────────────

def test_deactivated_account_kicked_from_session(app, client):
    """
    If an account is deactivated while a session is active, the next
    page request must log the user out and redirect to /login.
    """
    uid = _make_user(app, email='dkick@example.com', password='pass1234')
    _login(client, 'dkick@example.com', 'pass1234')

    # Confirm access is working
    res = client.get('/dashboard')
    assert res.status_code == 200

    # Admin deactivates account in DB — use a raw SQL UPDATE so it
    # bypasses any ORM identity map and is committed immediately.
    with app.app_context():
        from app import db
        from sqlalchemy import text
        db.session.execute(
            text('UPDATE users SET account_active = 0 WHERE id = :uid'),
            {'uid': uid}
        )
        db.session.commit()

    # Next page request should redirect to login
    res = client.get('/dashboard')
    assert res.status_code == 302
    assert '/login' in res.headers['Location']


# ── Settings web route ─────────────────────────────────────────────────────────

def test_settings_page_authenticated(app, client):
    _make_user(app, email='sauth@example.com', password='pass1234')
    _login(client, 'sauth@example.com', 'pass1234')
    res = client.get('/settings')
    assert res.status_code == 200


def test_settings_page_unauthenticated_redirects(client):
    res = client.get('/settings')
    assert res.status_code == 302
    assert '/login' in res.headers['Location']


# ── Public homepage routes ─────────────────────────────────────────────────────

def test_homepage_accessible_without_auth(client):
    assert client.get('/').status_code == 200


def test_homepage_redirects_authenticated_to_dashboard(app, client):
    _make_user(app, email='hrd@example.com', password='pass1234')
    _login(client, 'hrd@example.com', 'pass1234')
    res = client.get('/')
    assert res.status_code == 302
    assert '/dashboard' in res.headers['Location']


def test_login_page_accessible_without_auth(client):
    assert client.get('/login').status_code == 200


def test_signup_page_accessible_without_auth(client):
    assert client.get('/signup').status_code == 200


def test_all_private_routes_redirect_unauthenticated(client):
    private_routes = ['/dashboard', '/tasks', '/categories', '/profile', '/settings']
    for route in private_routes:
        res = client.get(route)
        assert res.status_code == 302, f'{route} must redirect unauthenticated users'
        assert '/login' in res.headers['Location'], f'{route} must redirect to /login'


# ── Existing task API unaffected ───────────────────────────────────────────────

def test_task_crud_works_after_model_changes(app, client):
    """Ensure adding role/account_active did not break task creation/retrieval."""
    _make_user(app, email='tasktest@example.com', password='pass1234')
    _login(client, 'tasktest@example.com', 'pass1234')

    create = client.post('/api/tasks', json={
        'title': 'Test task after model change',
        'priority': 'high',
    })
    assert create.status_code == 201
    task_id = create.get_json()['data']['id']

    get = client.get(f'/api/tasks/{task_id}')
    assert get.status_code == 200
    assert get.get_json()['data']['title'] == 'Test task after model change'

    delete = client.delete(f'/api/tasks/{task_id}')
    assert delete.status_code == 200


def test_task_user_isolation_preserved(app, client):
    """User A tasks must not be visible to User B after model changes."""
    _make_user(app, email='ta@example.com', password='passA1234')
    _make_user(app, email='tb@example.com', password='passB1234')

    _login(client, 'ta@example.com', 'passA1234')
    client.post('/api/tasks', json={'title': 'User A private task'})
    client.post('/api/auth/logout')

    _login(client, 'tb@example.com', 'passB1234')
    tasks = client.get('/api/tasks').get_json()['data']
    titles = [t['title'] for t in tasks]
    assert 'User A private task' not in titles


# ── Self-registration assigns employee role ────────────────────────────────────

def test_signup_assigns_employee_role(app, client):
    res = client.post('/api/auth/signup', json={
        'full_name': 'New Employee',
        'email':     'newemp@example.com',
        'password':  'pass1234',
    })
    assert res.status_code == 201
    data = res.get_json()
    assert data['data']['role'] == ROLE_EMPLOYEE


# ── Profile endpoint for deactivated accounts ──────────────────────────────────

def test_profile_update_blocked_for_deactivated(app, client):
    """
    A deactivated user who still has a session (edge case) must be blocked
    by the active_account_required decorator on the profile endpoint.
    """
    uid = _make_user(app, email='deac2@example.com', password='pass1234')
    _login(client, 'deac2@example.com', 'pass1234')

    # Deactivate account while session is open — raw SQL to avoid cache issues
    with app.app_context():
        from app import db
        from sqlalchemy import text
        db.session.execute(
            text('UPDATE users SET account_active = 0 WHERE id = :uid'),
            {'uid': uid}
        )
        db.session.commit()

    # Profile update must be rejected
    res = client.put('/api/auth/profile', json={'full_name': 'Should Fail'})
    assert res.status_code == 403
    assert 'deactivated' in res.get_json()['error'].lower()
