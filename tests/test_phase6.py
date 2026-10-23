from datetime import date, datetime, timedelta, timezone

from app import db
from app.models import ROLE_EMPLOYEE, ROLE_TEAM_LEAD, Task, Team, User


def make_user(app, email, role=ROLE_EMPLOYEE, full_name=None):
    with app.app_context():
        user = User(
            username=email.split('@')[0],
            full_name=full_name or email.split('@')[0],
            email=email,
            role=role,
        )
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def login(client, email):
    assert client.post('/api/auth/login', json={
        'email': email,
        'password': 'password123',
    }).status_code == 200


def goal_payload(**overrides):
    payload = {
        'title': 'Finish focused work',
        'description': 'A personal target',
        'goal_type': 'complete_tasks',
        'target_value': 2,
        'start_date': '2026-10-01',
        'target_date': '2026-10-31',
    }
    payload.update(overrides)
    return payload


def test_personal_goals_validate_ownership_and_progress(app, client):
    owner_id = make_user(app, 'goal-owner@example.com')
    other_id = make_user(app, 'goal-other@example.com')
    with app.app_context():
        db.session.add_all([
            Task(title='Completed one', user_id=owner_id, status='completed',
                 completed_at=datetime(2026, 10, 5, tzinfo=timezone.utc)),
            Task(title='Completed two', user_id=owner_id, status='completed',
                 completed_at=datetime(2026, 10, 6, tzinfo=timezone.utc)),
        ])
        db.session.commit()
    login(client, 'goal-owner@example.com')
    response = client.post('/api/goals', json=goal_payload())
    assert response.status_code == 201
    goal = response.get_json()['data']
    assert goal['current_progress'] == 2
    assert goal['progress_percent'] == 100.0
    goal_id = goal['id']
    assert client.put(f'/api/goals/{goal_id}', json=goal_payload(target_date='2026-09-30')).status_code == 400
    assert client.delete(f'/api/goals/{goal_id}').status_code == 200
    assert client.get('/api/goals').get_json()['data'] == []

    login(client, 'goal-other@example.com')
    assert client.get(f'/api/goals/{goal_id}').status_code == 404
    assert other_id


def test_employee_analytics_uses_completion_dates_and_zero_safe_rate(app, client):
    user_id = make_user(app, 'analytics-owner@example.com')
    with app.app_context():
        db.session.add_all([
            Task(title='Done', user_id=user_id, status='completed',
                 created_at=datetime(2026, 10, 2, tzinfo=timezone.utc),
                 completed_at=datetime(2026, 10, 4, tzinfo=timezone.utc)),
            Task(title='Open', user_id=user_id, created_at=datetime(2026, 10, 5, tzinfo=timezone.utc)),
        ])
        db.session.commit()
    login(client, 'analytics-owner@example.com')
    data = client.get('/api/analytics?start=2026-10-01&end=2026-10-07').get_json()['data']
    assert data['completed'] == 1
    assert data['open'] == 1
    assert data['completion_rate'] == 50.0
    assert len(data['trend']) == 7
    assert client.get('/api/analytics?start=2026-10-08&end=2026-10-01').status_code == 400


def test_team_analytics_and_export_are_scoped(app, client):
    lead_id = make_user(app, 'analytics-lead@example.com', ROLE_TEAM_LEAD)
    member_id = make_user(app, 'analytics-member@example.com')
    outside_id = make_user(app, 'analytics-outside@example.com', full_name='=Injected')
    with app.app_context():
        lead = db.session.get(User, lead_id)
        member = db.session.get(User, member_id)
        team = Team(name='Analytics team', lead_id=lead_id)
        team.members.append(member)
        db.session.add(team)
        db.session.add_all([
            Task(title='Team task', user_id=member_id, assigned_to_id=member_id, team=team,
                 status='completed', completed_at=datetime(2026, 10, 5, tzinfo=timezone.utc)),
            Task(title='Private task', user_id=outside_id, assigned_to_id=outside_id),
        ])
        db.session.commit()
    login(client, 'analytics-lead@example.com')
    response = client.get('/api/analytics/team?start=2026-10-01&end=2026-10-31')
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['totals']['completed'] == 1
    assert {item['employee_id'] for item in data['employees']} == {lead_id, member_id}
    assert client.get(f'/api/analytics/export.csv?start=2026-10-01&end=2026-10-31').status_code == 200
    assert client.get('/api/analytics/team?start=2026-10-31&end=2026-10-01').status_code == 400


def test_analytics_and_goals_require_authentication(client):
    assert client.get('/api/goals').status_code == 401
    assert client.get('/api/analytics').status_code == 401
    assert client.get('/goals').status_code == 302
