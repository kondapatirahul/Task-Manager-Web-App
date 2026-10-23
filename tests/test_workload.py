from datetime import date, datetime, timedelta, timezone

from app import db
from app.models import (
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    ROLE_SUPER_ADMIN,
    ROLE_TEAM_LEAD,
    Task,
    Team,
    User,
)


def _user(app, email, role=ROLE_EMPLOYEE, capacity=40):
    with app.app_context():
        user = User(username=email.split('@')[0], full_name=email.split('@')[0], email=email,
                    role=role, weekly_capacity_hours=capacity)
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def _login(client, email):
    response = client.post('/api/auth/login', json={'email': email, 'password': 'password123'})
    assert response.status_code == 200


def test_employee_workload_counts_effort_and_zero_capacity(app, client):
    employee_id = _user(app, 'workload@example.com', capacity=0)
    today = date.today()
    with app.app_context():
        db.session.add_all([
            Task(title='Overdue high', user_id=employee_id, priority='high',
                 due_date=today - timedelta(days=1), estimated_effort_hours=5),
            Task(title='Today', user_id=employee_id, due_date=today,
                 estimated_effort_hours=3, status='in_progress'),
            Task(title='No estimate', user_id=employee_id),
            Task(title='Done today', user_id=employee_id, status='completed',
                 completed_at=datetime.now(timezone.utc), due_date=today),
        ])
        db.session.commit()
    _login(client, 'workload@example.com')
    data = client.get('/api/workload/me').get_json()['data']
    assert data['open_tasks'] == 3
    assert data['in_progress'] == 1
    assert data['due_today'] == 1
    assert data['overdue'] == 1
    assert data['high_priority'] == 1
    assert data['completed_this_week'] == 1
    assert data['estimated_remaining_effort_hours'] == 8
    assert data['utilization_percent'] is None
    assert data['unestimated_tasks_count'] == 1


def test_team_lead_workload_is_scoped(app, client):
    lead_id = _user(app, 'lead-workload@example.com', ROLE_TEAM_LEAD)
    member_id = _user(app, 'member-workload@example.com')
    outside_id = _user(app, 'outside-workload@example.com')
    with app.app_context():
        lead = db.session.get(User, lead_id)
        member = db.session.get(User, member_id)
        team = Team(name='Authorized team', lead_id=lead_id)
        team.members.append(member)
        db.session.add(team)
        db.session.add_all([
            Task(title='Member task', user_id=member_id, assigned_to_id=member_id, team=team),
            Task(title='Outside task', user_id=outside_id, assigned_to_id=outside_id),
        ])
        db.session.commit()
    _login(client, 'lead-workload@example.com')
    response = client.get('/api/workload/team')
    assert response.status_code == 200
    employees = response.get_json()['data']['employees']
    assert {item['employee_id'] for item in employees} == {member_id, lead_id}
    assert client.get(f'/api/workload/employees/{outside_id}').status_code == 403


def test_workload_requires_authentication(client):
    assert client.get('/api/workload/me').status_code == 401
    assert client.get('/api/workload/team').status_code == 401


def test_assignment_recommendations_explain_capacity_and_team_scope(app, client):
    manager_id = _user(app, 'recommendation-admin@example.com', ROLE_SUPER_ADMIN)
    low_id = _user(app, 'low-load@example.com', capacity=20)
    high_id = _user(app, 'high-load@example.com', capacity=10)
    with app.app_context():
        db.session.add(Task(
            title='Existing estimate', user_id=high_id, assigned_to_id=high_id,
            estimated_effort_hours=9,
        ))
        proposed = Task(
            title='Proposed work', user_id=manager_id, estimated_effort_hours=4,
        )
        db.session.add(proposed)
        db.session.commit()
        proposed_id = proposed.id
    _login(client, 'recommendation-admin@example.com')
    response = client.post('/api/workload/recommendations', json={
        'task_id': proposed_id,
    })
    assert response.status_code == 200
    recommendations = response.get_json()['data']['recommendations']
    by_id = {item['employee_id']: item for item in recommendations}
    assert by_id[low_id]['planned_workload_hours'] == 4
    assert by_id[low_id]['would_exceed_capacity'] is False
    assert by_id[high_id]['would_exceed_capacity'] is True
    assert any('lower estimated workload' in reason for reason in by_id[low_id]['reasons'])


def test_assignment_accept_rechecks_and_never_silently_reassigns(app, client):
    manager_id = _user(app, 'accept-assignment@example.com', ROLE_SUPER_ADMIN)
    employee_id = _user(app, 'accept-employee@example.com', capacity=40)
    with app.app_context():
        task = Task(title='Assignable', user_id=manager_id, estimated_effort_hours=5)
        db.session.add(task)
        db.session.commit()
        task_id = task.id
    _login(client, 'accept-assignment@example.com')
    recommendation = client.post('/api/workload/recommendations', json={
        'task_id': task_id,
    })
    assert recommendation.status_code == 200
    with app.app_context():
        assert db.session.get(Task, task_id).assigned_to_id is None
    accepted = client.post(
        f'/api/workload/recommendations/{task_id}/accept',
        json={'employee_id': employee_id},
    )
    assert accepted.status_code == 200
    with app.app_context():
        assert db.session.get(Task, task_id).assigned_to_id == employee_id


def test_employees_cannot_request_or_accept_assignment_recommendations(app, client):
    employee_id = _user(app, 'employee-recommendation@example.com')
    _login(client, 'employee-recommendation@example.com')
    assert client.post('/api/workload/recommendations', json={}).status_code == 403
    assert client.post(
        '/api/workload/recommendations/999/accept',
        json={'employee_id': employee_id},
    ).status_code in (403, 404)


def test_team_lead_recommendations_only_include_led_team_members(app, client):
    lead_id = _user(app, 'recommendation-lead@example.com', ROLE_TEAM_LEAD)
    member_id = _user(app, 'recommendation-member@example.com')
    outside_id = _user(app, 'recommendation-outside@example.com')
    with app.app_context():
        team = Team(name='Recommendation team', lead_id=lead_id)
        team.members.append(db.session.get(User, member_id))
        db.session.add(team)
        task = Task(title='Team assignment', user_id=lead_id, team=team, estimated_effort_hours=2)
        db.session.add(task)
        db.session.commit()
        task_id = task.id
    _login(client, 'recommendation-lead@example.com')
    response = client.post('/api/workload/recommendations', json={'task_id': task_id})
    assert response.status_code == 200
    ids = {item['employee_id'] for item in response.get_json()['data']['recommendations']}
    assert member_id in ids
    assert outside_id not in ids
