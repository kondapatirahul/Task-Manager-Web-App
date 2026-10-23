from datetime import date
from pathlib import Path

from sqlalchemy import text

from app import db, create_app
from app.models import (
    Activity,
    Organization,
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    ROLE_SUPER_ADMIN,
    ROLE_TEAM_LEAD,
    Task,
    Team,
    User,
)


def make_user(app, email, role, organization_id=None, active=True):
    with app.app_context():
        user = User(
            username=email.split('@')[0],
            full_name=email.split('@')[0],
            email=email,
            role=role,
            organization_id=organization_id,
            account_active=active,
        )
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def login(client, email, csrf_token=None):
    headers = {'X-CSRFToken': csrf_token} if csrf_token else {}
    return client.post('/api/auth/login', json={
        'email': email,
        'password': 'password123',
    }, headers=headers)


def test_organization_admin_isolation_and_super_admin_access(app, client):
    with app.app_context():
        org_a = Organization(name='Hardening A')
        org_b = Organization(name='Hardening B')
        db.session.add_all([org_a, org_b])
        db.session.commit()
        org_a_id = org_a.id
        org_b_id = org_b.id
    admin_id = make_user(app, 'hardening-admin@example.com', ROLE_ADMIN, org_a_id)
    employee_b_id = make_user(app, 'hardening-b@example.com', ROLE_EMPLOYEE, org_b_id)
    super_id = make_user(app, 'hardening-super@example.com', ROLE_SUPER_ADMIN)
    with app.app_context():
        task = Task(
            title='Private organization B task',
            user_id=employee_b_id,
            assigned_to_id=employee_b_id,
            due_date=date(2026, 10, 23),
        )
        db.session.add(task)
        db.session.flush()
        db.session.add(Activity(
            task_id=task.id,
            activity_type='test',
            description='Private activity',
        ))
        db.session.commit()
        task_id = task.id

    assert login(client, 'hardening-admin@example.com').status_code == 200
    calendar = client.get('/api/calendar/tasks?start=2026-10-01&end=2026-10-31')
    assert calendar.get_json()['data']['tasks'] == []
    assert client.get('/api/workload/team').get_json()['data']['employees'] == []
    assert client.get('/api/analytics/team?start=2026-10-01&end=2026-10-31').get_json()['data']['totals']['open'] == 0
    assert client.get('/api/analytics/export.csv?start=2026-10-01&end=2026-10-31').get_data(as_text=True).count('hardening-b') == 0
    assert client.get('/api/activity').get_json()['data']['items'] == []

    client.post('/api/auth/logout')
    assert login(client, 'hardening-super@example.com').status_code == 200
    calendar = client.get('/api/calendar/tasks?start=2026-10-01&end=2026-10-31')
    assert [item['id'] for item in calendar.get_json()['data']['tasks']] == [task_id]
    assert client.get(f'/api/workload/employees/{employee_b_id}').status_code == 200


def test_workload_employee_scope_for_admin_team_lead_and_employee(app, client):
    with app.app_context():
        org_a = Organization(name='Workload A')
        org_b = Organization(name='Workload B')
        db.session.add_all([org_a, org_b])
        db.session.commit()
        org_a_id, org_b_id = org_a.id, org_b.id

    admin_id = make_user(app, 'workload-admin@example.com', ROLE_ADMIN, org_a_id)
    lead_a_id = make_user(app, 'workload-lead-a@example.com', ROLE_TEAM_LEAD, org_a_id)
    member_a_id = make_user(app, 'workload-member-a@example.com', ROLE_EMPLOYEE, org_a_id)
    lead_b_id = make_user(app, 'workload-lead-b@example.com', ROLE_TEAM_LEAD, org_b_id)
    member_b_id = make_user(app, 'workload-member-b@example.com', ROLE_EMPLOYEE, org_b_id)
    super_id = make_user(app, 'workload-super@example.com', ROLE_SUPER_ADMIN)

    with app.app_context():
        team_a = Team(name='Workload team A', organization_id=org_a_id, lead_id=lead_a_id)
        team_b = Team(name='Workload team B', organization_id=org_b_id, lead_id=lead_b_id)
        db.session.add_all([team_a, team_b])
        db.session.flush()
        team_a.members.append(db.session.get(User, member_a_id))
        team_b.members.append(db.session.get(User, member_b_id))
        db.session.commit()

    assert login(client, 'workload-admin@example.com').status_code == 200
    assert client.get(f'/api/workload/employees/{member_a_id}').status_code == 200
    assert client.get(f'/api/workload/employees/{member_b_id}').status_code == 403
    assert client.get('/api/workload/employees/999999').status_code == 403

    client.post('/api/auth/logout')
    assert login(client, 'workload-lead-a@example.com').status_code == 200
    assert client.get(f'/api/workload/employees/{member_a_id}').status_code == 200
    assert client.get(f'/api/workload/employees/{member_b_id}').status_code == 403

    client.post('/api/auth/logout')
    assert login(client, 'workload-member-a@example.com').status_code == 200
    assert client.get(f'/api/workload/employees/{member_a_id}').status_code == 200
    assert client.get(f'/api/workload/employees/{member_b_id}').status_code == 403

    client.post('/api/auth/logout')
    assert login(client, 'workload-super@example.com').status_code == 200
    assert client.get(f'/api/workload/employees/{member_b_id}').status_code == 200


def test_super_admin_and_team_lead_reporting_scope(app, client):
    with app.app_context():
        org_a = Organization(name='Reporting A')
        org_b = Organization(name='Reporting B')
        db.session.add_all([org_a, org_b])
        db.session.commit()
        org_a_id, org_b_id = org_a.id, org_b.id
    lead_a_id = make_user(app, 'reporting-lead-a@example.com', ROLE_TEAM_LEAD, org_a_id)
    member_a_id = make_user(app, 'reporting-member-a@example.com', ROLE_EMPLOYEE, org_a_id)
    lead_b_id = make_user(app, 'reporting-lead-b@example.com', ROLE_TEAM_LEAD, org_b_id)
    member_b_id = make_user(app, 'reporting-member-b@example.com', ROLE_EMPLOYEE, org_b_id)
    super_id = make_user(app, 'reporting-super@example.com', ROLE_SUPER_ADMIN)
    with app.app_context():
        team_a = Team(name='Reporting team A', organization_id=org_a_id, lead_id=lead_a_id)
        team_b = Team(name='Reporting team B', organization_id=org_b_id, lead_id=lead_b_id)
        db.session.add_all([team_a, team_b])
        db.session.flush()
        team_a.members.append(db.session.get(User, member_a_id))
        team_b.members.append(db.session.get(User, member_b_id))
        db.session.flush()
        task_a = Task(title='Reporting A task', user_id=member_a_id, assigned_to_id=member_a_id, team=team_a)
        task_b = Task(title='Reporting B task', user_id=member_b_id, assigned_to_id=member_b_id, team=team_b)
        db.session.add_all([task_a, task_b])
        db.session.flush()
        db.session.add_all([
            Activity(task_id=task_a.id, activity_type='test', description='A activity'),
            Activity(task_id=task_b.id, activity_type='test', description='B activity'),
        ])
        task_a_id, task_b_id = task_a.id, task_b.id
        db.session.commit()

    query = '?start=2026-10-01&end=2026-10-31'
    assert login(client, 'reporting-lead-a@example.com').status_code == 200
    assert client.get('/api/workload/team').status_code == 200
    assert client.get(f'/api/analytics/team{query}').get_json()['data']['totals']['open'] == 1
    export = client.get(f'/api/analytics/export.csv{query}').get_data(as_text=True)
    assert 'reporting-member-a' in export
    assert 'reporting-member-b' not in export
    assert all(item['task_id'] == task_a_id for item in client.get('/api/activity').get_json()['data']['items'])

    client.post('/api/auth/logout')
    assert login(client, 'reporting-super@example.com').status_code == 200
    assert client.get('/api/workload/team').get_json()['data']['employee_count'] == 2
    assert client.get(f'/api/workload/employees/{member_b_id}').status_code == 200
    assert client.get(f'/api/analytics/team{query}').get_json()['data']['totals']['open'] == 2
    export = client.get(f'/api/analytics/export.csv{query}').get_data(as_text=True)
    assert 'reporting-member-a' in export and 'reporting-member-b' in export
    activity_ids = {item['task_id'] for item in client.get('/api/activity').get_json()['data']['items']}
    assert {task_a_id, task_b_id}.issubset(activity_ids)


def test_csrf_missing_invalid_and_valid_tokens(app):
    csrf_app = create_app({
        'TESTING': False,
        'CSRF_ENABLED': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'hardening-csrf-secret',
    })
    with csrf_app.app_context():
        db.create_all()
        user = User(username='csrf-user', full_name='CSRF User', email='csrf@example.com')
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
    csrf_client = csrf_app.test_client()
    assert csrf_client.get('/login').status_code == 200
    with csrf_client.session_transaction() as session:
        token = session['csrf_token']
    assert csrf_client.post('/api/tasks', json={'title': 'Missing token'}).status_code == 403
    assert csrf_client.post('/api/tasks', json={'title': 'Bad token'}, headers={'X-CSRFToken': 'bad'}).status_code == 403
    assert login(csrf_client, 'csrf@example.com', token).status_code == 200
    assert csrf_client.get('/api/workload/me').status_code == 200
    assert csrf_client.post('/api/tasks', json={'title': 'Valid token'}, headers={'X-CSRFToken': token}).status_code == 201
    assert csrf_client.post('/api/auth/logout').status_code == 403
    assert csrf_client.post('/api/auth/logout', headers={'X-CSRFToken': token}).status_code == 200


def test_csrf_registration_aliases_and_authenticated_mutations(app):
    csrf_app = create_app({
        'TESTING': False,
        'CSRF_ENABLED': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'hardening-csrf-alias-secret',
    })
    with csrf_app.app_context():
        db.create_all()
    csrf_client = csrf_app.test_client()
    assert csrf_client.get('/login').status_code == 200
    with csrf_client.session_transaction() as session:
        token = session['csrf_token']
    assert csrf_client.post('/api/auth/register', json={
        'email': 'alias@example.com',
        'username': 'alias',
        'password': 'password123',
    }, headers={'X-CSRFToken': token}).status_code == 201
    assert csrf_client.put('/api/auth/profile', json={'full_name': 'Alias User'}, headers={
        'X-CSRFToken': token,
    }).status_code == 200
    assert csrf_client.put('/api/auth/profile', json={'full_name': 'Missing Token'}).status_code == 403


def test_deactivated_sessions_are_denied_from_mutating_affected_apis(app, client):
    user_id = make_user(app, 'deactivated-mutations@example.com', ROLE_EMPLOYEE)
    assert login(client, 'deactivated-mutations@example.com').status_code == 200
    goal_response = client.post('/api/goals', json={
        'title': 'Mutation goal',
        'goal_type': 'complete_tasks',
        'target_value': 1,
        'start_date': '2026-10-01',
        'target_date': '2026-10-31',
    })
    assert goal_response.status_code == 201
    goal_id = goal_response.get_json()['data']['id']
    with app.app_context():
        db.session.execute(
            text('UPDATE users SET account_active = 0 WHERE id = :user_id'),
            {'user_id': user_id},
        )
        db.session.commit()
    assert client.post('/api/goals', json={}).status_code in (401, 403)
    assert client.put(f'/api/goals/{goal_id}', json={}).status_code in (401, 403)
    assert client.patch(f'/api/goals/{goal_id}/complete').status_code in (401, 403)
    assert client.delete(f'/api/goals/{goal_id}').status_code in (401, 403)


def test_attachment_metadata_is_not_interpolated_into_html():
    source = Path(__file__).parents[1].joinpath('static', 'js', 'task_detail.js').read_text()
    assert 'title="${att.original_filename}"' not in source
    assert '${att.original_filename}' not in source
    assert '${att.file_size_human}</div>' not in source
    assert 'name.textContent = attachment.original_filename' in source
    assert 'size.textContent = attachment.file_size_human' in source
    assert 'getSafeAttachmentUrl' in source


def test_deactivated_sessions_are_denied_from_affected_apis(app, client):
    user_id = make_user(app, 'deactivated@example.com', ROLE_EMPLOYEE)
    assert login(client, 'deactivated@example.com').status_code == 200
    with app.app_context():
        db.session.execute(
            text('UPDATE users SET account_active = 0 WHERE id = :user_id'),
            {'user_id': user_id},
        )
        db.session.commit()
    endpoints = [
        '/api/goals',
        '/api/analytics',
        '/api/calendar/tasks?start=2026-10-01&end=2026-10-02',
        '/api/workload/me',
        '/api/notifications',
        '/api/activity',
    ]
    for endpoint in endpoints:
        assert client.get(endpoint).status_code == 403
