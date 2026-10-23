from datetime import date, timedelta

from app import db
from app.models import ROLE_EMPLOYEE, ROLE_TEAM_LEAD, Task, Team, User


def make_user(app, email, role=ROLE_EMPLOYEE):
    with app.app_context():
        user = User(
            username=email.split('@')[0],
            full_name=email.split('@')[0],
            email=email,
            role=role,
        )
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def login(client, email):
    response = client.post('/api/auth/login', json={
        'email': email,
        'password': 'password123',
    })
    assert response.status_code == 200


def test_calendar_range_filters_and_date_boundaries(app, client):
    user_id = make_user(app, 'calendar@example.com')
    start = date(2026, 10, 1)
    with app.app_context():
        created = [
            Task(title='At start', user_id=user_id, due_date=start),
            Task(title='At end', user_id=user_id, due_date=start + timedelta(days=6), priority='high'),
            Task(title='Outside', user_id=user_id, due_date=start + timedelta(days=7)),
            Task(title='No date', user_id=user_id),
            Task(title='Completed', user_id=user_id, due_date=start + timedelta(days=2), status='completed'),
        ]
        db.session.add_all(created)
        db.session.commit()
        task_id = created[0].id
    login(client, 'calendar@example.com')
    response = client.get('/api/calendar/tasks?start=2026-10-01&end=2026-10-07')
    assert response.status_code == 200
    tasks = response.get_json()['data']['tasks']
    assert {task['title'] for task in tasks} == {'At start', 'At end', 'Completed'}

    response = client.get('/api/calendar/tasks?start=2026-10-01&end=2026-10-07&priority=high')
    assert [task['title'] for task in response.get_json()['data']['tasks']] == ['At end']

    response = client.get('/api/calendar/tasks?start=2026-10-01&end=2026-10-07&status=not-a-status')
    assert response.status_code == 400
    assert client.put(f'/api/tasks/{task_id}', json={'due_date': '2026-10-08'}).status_code == 200


def test_calendar_deadline_filters_exclude_completed_and_missing_dates(app, client):
    user_id = make_user(app, 'calendar-deadlines@example.com')
    today = date.today()
    with app.app_context():
        db.session.add_all([
            Task(title='Overdue', user_id=user_id, due_date=today - timedelta(days=1)),
            Task(title='Upcoming', user_id=user_id, due_date=today + timedelta(days=1)),
            Task(title='Completed overdue', user_id=user_id, due_date=today - timedelta(days=2), status='completed'),
            Task(title='Undated', user_id=user_id),
        ])
        db.session.commit()
    login(client, 'calendar-deadlines@example.com')
    range_args = f'start={today - timedelta(days=7):%Y-%m-%d}&end={today + timedelta(days=7):%Y-%m-%d}'
    overdue = client.get(f'/api/calendar/tasks?{range_args}&deadline=overdue').get_json()['data']['tasks']
    upcoming = client.get(f'/api/calendar/tasks?{range_args}&deadline=upcoming').get_json()['data']['tasks']
    assert [task['title'] for task in overdue] == ['Overdue']
    assert [task['title'] for task in upcoming] == ['Upcoming']


def test_calendar_team_lead_scope_and_employee_filter(app, client):
    lead_id = make_user(app, 'calendar-lead@example.com', ROLE_TEAM_LEAD)
    member_id = make_user(app, 'calendar-member@example.com')
    outside_id = make_user(app, 'calendar-outside@example.com')
    with app.app_context():
        lead = db.session.get(User, lead_id)
        member = db.session.get(User, member_id)
        team = Team(name='Calendar team', lead_id=lead_id)
        team.members.append(member)
        db.session.add(team)
        db.session.add_all([
            Task(title='In team', user_id=member_id, assigned_to_id=member_id, team=team, due_date=date(2026, 10, 5)),
            Task(title='Outside team', user_id=outside_id, assigned_to_id=outside_id, due_date=date(2026, 10, 5)),
        ])
        db.session.commit()
    login(client, 'calendar-lead@example.com')
    query = '/api/calendar/tasks?start=2026-10-01&end=2026-10-31'
    response = client.get(query)
    assert {task['title'] for task in response.get_json()['data']['tasks']} == {'In team'}
    assert client.get(f'{query}&employee_id={outside_id}').status_code == 403
    assert client.get('/api/calendar/tasks?start=2026-10-31&end=2026-10-01').status_code == 400


def test_calendar_page_and_unauthenticated_access(client):
    assert client.get('/calendar').status_code == 302
    assert client.get('/api/calendar/tasks?start=2026-10-01&end=2026-10-02').status_code == 401
