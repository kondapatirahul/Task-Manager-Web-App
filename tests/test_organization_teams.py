"""
tests/test_organization_teams.py

Integration and authorization tests for:
- Organization & Department Administration
- Teams and Team Memberships
- Employee Directory & Multi-factor Search/Filter
- Secure Employee Account Activation Flow
- Permission Boundaries (Admin, HR, Team Lead, Employee)
- Safe Deactivation & Record Preservation
"""
import pytest
from app import create_app, db
from app.models import (
    User, Department, Organization, Team, Task, Category, team_members,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_HR, ROLE_TEAM_LEAD, ROLE_EMPLOYEE,
    ALL_ROLES
)


@pytest.fixture
def app():
    application = create_app({
        'TESTING': True,
        'CSRF_ENABLED': False,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-secret-key-org-teams',
    })
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _make_user(app, *, email, password='password123', full_name='Test User',
               username=None, role=ROLE_EMPLOYEE, account_active=True,
               organization_id=None, department_id=None, job_title=None):
    with app.app_context():
        uname = username or email.split('@')[0]
        user = User(
            username=uname,
            full_name=full_name,
            email=email,
            role=role,
            account_active=account_active,
            organization_id=organization_id,
            department_id=department_id,
            job_title=job_title
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, email, password='password123'):
    return client.post('/api/auth/login', json={
        'email': email,
        'password': password
    })


# ── Employee Directory & Activation Flow Tests ───────────────────────────────

def test_admin_can_create_employee_with_activation_token(app, client):
    """Admin creates employee without password, receiving activation token."""
    _make_user(app, email='admin@corp.com', role=ROLE_ADMIN)
    _login(client, 'admin@corp.com')

    res = client.post('/api/employees', json={
        'full_name': 'Sarah Connor',
        'email': 'sarah@corp.com',
        'role': ROLE_EMPLOYEE,
        'job_title': 'Security Engineer'
    })
    assert res.status_code == 201
    data = res.get_json()['data']
    assert data['full_name'] == 'Sarah Connor'
    assert data['email'] == 'sarah@corp.com'
    assert data['role'] == ROLE_EMPLOYEE
    assert data['account_active'] is True
    assert 'activation_token' in data
    assert len(data['activation_token']) >= 8


def test_employee_creation_validations(app, client):
    """Validate duplicate emails, missing fields, and email syntax."""
    _make_user(app, email='admin@corp.com', role=ROLE_ADMIN)
    _login(client, 'admin@corp.com')

    # Missing email
    r1 = client.post('/api/employees', json={'full_name': 'No Email'})
    assert r1.status_code == 400
    assert r1.get_json()['ok'] is False

    # Missing full name
    r2 = client.post('/api/employees', json={'email': 'name@corp.com'})
    assert r2.status_code == 400

    # Duplicate email
    client.post('/api/employees', json={'full_name': 'First', 'email': 'dup@corp.com'})
    r3 = client.post('/api/employees', json={'full_name': 'Second', 'email': 'dup@corp.com'})
    assert r3.status_code == 409
    assert 'already exists' in r3.get_json()['error']


def test_regular_employee_cannot_create_or_invite_employees(app, client):
    """Regular employees are blocked from calling employee creation API."""
    _make_user(app, email='emp@corp.com', role=ROLE_EMPLOYEE)
    _login(client, 'emp@corp.com')

    res = client.post('/api/employees', json={
        'full_name': 'Hacker',
        'email': 'hacker@corp.com'
    })
    assert res.status_code == 403
    assert res.get_json()['ok'] is False


def test_role_escalation_prevention(app, client):
    """HR user cannot promote/create an Admin or Super Admin."""
    _make_user(app, email='hr@corp.com', role=ROLE_HR)
    _login(client, 'hr@corp.com')

    res = client.post('/api/employees', json={
        'full_name': 'Elevated User',
        'email': 'elevated@corp.com',
        'role': ROLE_ADMIN
    })
    assert res.status_code == 403
    assert 'permission' in res.get_json()['error']


# ── Search & Filter Combinations ──────────────────────────────────────────────

def test_employee_search_and_filter_combinations(app, client):
    """Test combined filtering by query keyword, department, team, role, and status."""
    with app.app_context():
        org = Organization(name='TechCorp')
        db.session.add(org)
        db.session.flush()

        d_eng = Department(name='Engineering', organization_id=org.id)
        d_hr = Department(name='Human Resources', organization_id=org.id)
        db.session.add_all([d_eng, d_hr])
        db.session.flush()

        t_backend = Team(name='Backend Core', organization_id=org.id, department_id=d_eng.id)
        db.session.add(t_backend)
        db.session.flush()

        # Users
        u1 = User(username='alice', full_name='Alice Smith', email='alice@tc.com',
                  role=ROLE_ADMIN, department_id=d_eng.id, organization_id=org.id, account_active=True)
        u1.set_password('pass1234')

        u2 = User(username='bob', full_name='Bob Jones', email='bob@tc.com',
                  role=ROLE_TEAM_LEAD, department_id=d_eng.id, organization_id=org.id, account_active=True)
        u2.set_password('pass1234')

        u3 = User(username='carol', full_name='Carol Davis', email='carol@tc.com',
                  role=ROLE_EMPLOYEE, department_id=d_hr.id, organization_id=org.id, account_active=False)
        u3.set_password('pass1234')

        db.session.add_all([u1, u2, u3])
        db.session.commit()

        # Assign Bob to backend team
        db.session.execute(team_members.insert().values(team_id=t_backend.id, user_id=u2.id, role='lead', joined_at=u2.created_at))
        db.session.commit()

        d_eng_id = d_eng.id
        t_backend_id = t_backend.id

    _login(client, 'alice@tc.com', 'pass1234')

    # 1. Search keyword "Jones"
    r1 = client.get('/api/employees?q=Jones')
    assert r1.status_code == 200
    assert len(r1.get_json()['data']) == 1
    assert r1.get_json()['data'][0]['username'] == 'bob'

    # 2. Filter by department
    r2 = client.get(f'/api/employees?department_id={d_eng_id}')
    assert len(r2.get_json()['data']) == 2

    # 3. Filter by team
    r3 = client.get(f'/api/employees?team_id={t_backend_id}')
    assert len(r3.get_json()['data']) == 1
    assert r3.get_json()['data'][0]['username'] == 'bob'

    # 4. Filter by role
    r4 = client.get('/api/employees?role=team_lead')
    assert len(r4.get_json()['data']) == 1
    assert r4.get_json()['data'][0]['username'] == 'bob'

    # 5. Filter by inactive status
    r5 = client.get('/api/employees?status=inactive')
    assert len(r5.get_json()['data']) == 1
    assert r5.get_json()['data'][0]['username'] == 'carol'


# ── Team Management & Boundaries ──────────────────────────────────────────────

def test_team_crud_and_lead_access_boundaries(app, client):
    """
    Team Leads view only their authorized teams.
    Viewing or managing unauthorized teams returns 403.
    """
    with app.app_context():
        org = Organization(name='Acme Corp')
        db.session.add(org)
        db.session.flush()

        lead_a = User(username='leada', full_name='Lead Alpha', email='leada@acme.com',
                      role=ROLE_TEAM_LEAD, organization_id=org.id)
        lead_a.set_password('pass1234')

        lead_b = User(username='leadb', full_name='Lead Beta', email='leadb@acme.com',
                      role=ROLE_TEAM_LEAD, organization_id=org.id)
        lead_b.set_password('pass1234')

        emp = User(username='dev1', full_name='Developer 1', email='dev1@acme.com',
                   role=ROLE_EMPLOYEE, organization_id=org.id)
        emp.set_password('pass1234')

        db.session.add_all([lead_a, lead_b, emp])
        db.session.commit()

        team_a = Team(name='Alpha Squad', organization_id=org.id, lead_id=lead_a.id)
        team_b = Team(name='Beta Squad', organization_id=org.id, lead_id=lead_b.id)
        db.session.add_all([team_a, team_b])
        db.session.commit()

        db.session.execute(team_members.insert().values(team_id=team_a.id, user_id=lead_a.id, role='lead', joined_at=lead_a.created_at))
        db.session.execute(team_members.insert().values(team_id=team_b.id, user_id=lead_b.id, role='lead', joined_at=lead_b.created_at))
        db.session.commit()

        t_a_id = team_a.id
        t_b_id = team_b.id
        emp_id = emp.id

    # Lead A logs in
    _login(client, 'leada@acme.com', 'pass1234')

    # Lead A only sees their authorized team in listing
    res_list = client.get('/api/teams')
    assert res_list.status_code == 200
    teams_visible = [t['name'] for t in res_list.get_json()['data']]
    assert 'Alpha Squad' in teams_visible
    assert 'Beta Squad' not in teams_visible

    # Lead A viewing team B directly is forbidden
    res_unauth = client.get(f'/api/teams/{t_b_id}')
    assert res_unauth.status_code == 403

    # Lead A can add Developer 1 to team A
    res_add = client.post(f'/api/teams/{t_a_id}/members', json={'user_id': emp_id})
    assert res_add.status_code == 201

    # Duplicate addition rejected
    res_dup = client.post(f'/api/teams/{t_a_id}/members', json={'user_id': emp_id})
    assert res_dup.status_code == 409

    # Lead A trying to add member to team B is forbidden
    res_hack = client.post(f'/api/teams/{t_b_id}/members', json={'user_id': emp_id})
    assert res_hack.status_code == 403

    # Lead A removes Developer 1 from team A
    res_rm = client.delete(f'/api/teams/{t_a_id}/members/{emp_id}')
    assert res_rm.status_code == 200


def test_team_task_assignment_and_preservation(app, client):
    """
    Team task creation, assignment to member, and safe deletion of team
    (tasks are safely preserved with team_id set to None).
    """
    with app.app_context():
        org = Organization(name='Omega Inc')
        db.session.add(org)
        db.session.flush()

        admin = User(username='om_admin', full_name='Admin', email='admin@omega.com', role=ROLE_ADMIN, organization_id=org.id)
        admin.set_password('pass1234')

        dev = User(username='om_dev', full_name='Dev', email='dev@omega.com', role=ROLE_EMPLOYEE, organization_id=org.id)
        dev.set_password('pass1234')

        db.session.add_all([admin, dev])
        db.session.commit()

        team = Team(name='DevOps', organization_id=org.id)
        db.session.add(team)
        db.session.commit()

        db.session.execute(team_members.insert().values(team_id=team.id, user_id=admin.id, role='lead', joined_at=admin.created_at))
        db.session.execute(team_members.insert().values(team_id=team.id, user_id=dev.id, role='member', joined_at=dev.created_at))
        db.session.commit()

        t_id = team.id
        dev_id = dev.id

    _login(client, 'admin@omega.com', 'pass1234')

    # Create task assigned to team and developer
    res_t = client.post(f'/api/teams/{t_id}/tasks', json={
        'title': 'Setup CI/CD Pipeline',
        'priority': 'high',
        'assigned_to_id': dev_id
    })
    assert res_t.status_code == 201
    task_id = res_t.get_json()['data']['id']
    assert res_t.get_json()['data']['assigned_to_id'] == dev_id
    assert res_t.get_json()['data']['team_id'] == t_id

    # Delete team safely
    del_team = client.delete(f'/api/teams/{t_id}')
    assert del_team.status_code == 200

    # Verify task still exists in database and team_id is now None (historical record preserved)
    with app.app_context():
        persisted_task = db.session.get(Task, task_id)
        assert persisted_task is not None
        assert persisted_task.title == 'Setup CI/CD Pipeline'
        assert persisted_task.team_id is None
        assert persisted_task.assigned_to_id == dev_id


# ── Account Deactivation & Safety ─────────────────────────────────────────────

def test_account_deactivation_and_login_block(app, client):
    """
    Deactivating an account sets account_active to False.
    Historical records and tasks are kept. Deactivated user cannot log in.
    """
    admin_id = _make_user(app, email='admin@sec.com', role=ROLE_ADMIN)
    target_id = _make_user(app, email='worker@sec.com', role=ROLE_EMPLOYEE)

    # Add a task for worker
    with app.app_context():
        t = Task(title='Important Work', user_id=target_id)
        db.session.add(t)
        db.session.commit()
        t_id = t.id

    # Admin deactivates worker
    _login(client, 'admin@sec.com')
    res_deact = client.patch(f'/api/employees/{target_id}/status', json={'account_active': False})
    assert res_deact.status_code == 200
    assert res_deact.get_json()['data']['account_active'] is False

    # Deactivated user attempts login → rejected (403)
    client.post('/api/auth/logout')
    res_login = client.post('/api/auth/login', json={'email': 'worker@sec.com', 'password': 'password123'})
    assert res_login.status_code == 403
    assert 'deactivated' in res_login.get_json()['error'].lower()

    # Verify task record was NOT deleted
    with app.app_context():
        task = db.session.get(Task, t_id)
        assert task is not None
        assert task.title == 'Important Work'


def test_cannot_deactivate_self(app, client):
    """Admin cannot deactivate their own account."""
    _make_user(app, email='admin_self@sec.com', role=ROLE_ADMIN)
    _login(client, 'admin_self@sec.com')

    with app.app_context():
        user = User.query.filter_by(email='admin_self@sec.com').first()
        uid = user.id

    res = client.patch(f'/api/employees/{uid}/status', json={'account_active': False})
    assert res.status_code == 400
    assert 'own account' in res.get_json()['error']


# ── Web Routes & Public Protection ────────────────────────────────────────────

def test_employees_and_teams_web_routes_protected(app, client):
    """Web views /employees and /teams require authentication."""
    # Unauthenticated redirects to /login
    r_emp = client.get('/employees')
    assert r_emp.status_code == 302
    assert '/login' in r_emp.headers['Location']

    r_team = client.get('/teams')
    assert r_team.status_code == 302
    assert '/login' in r_team.headers['Location']

    # Authenticated user gets 200
    _make_user(app, email='webuser@corp.com')
    _login(client, 'webuser@corp.com')

    assert client.get('/employees').status_code == 200
    assert client.get('/teams').status_code == 200
