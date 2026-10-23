from datetime import datetime, timedelta, timezone

from app import db
from app.models import FocusSession, Task, User


def login(client, email, password):
    response = client.post('/api/auth/login', json={'email': email, 'password': password})
    assert response.status_code == 200


def make_user(app, username, role='employee', organization_id=None):
    with app.app_context():
        user = User(
            username=username,
            full_name=username.title(),
            email=f'{username}@example.com',
            role=role,
            organization_id=organization_id,
        )
        user.set_password('password123')
        db.session.add(user)
        db.session.commit()
        return user.id


def make_task(app, user_id, title='Focus task', estimate=2.0):
    with app.app_context():
        task = Task(title=title, description='Work', user_id=user_id,
                    assigned_to_id=user_id, estimated_effort_hours=estimate)
        db.session.add(task)
        db.session.commit()
        return task.id


def test_focus_session_lifecycle_and_server_duration(app, client, monkeypatch):
    user_id = make_user(app, 'focususer')
    task_id = make_task(app, user_id)
    login(client, 'focususer@example.com', 'password123')
    base = datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc)
    import app.routes.focus_sessions as routes
    current = [base]
    monkeypatch.setattr(routes, 'now_utc', lambda: current[0])

    started = client.post('/api/focus-sessions', json={'task_id': task_id})
    assert started.status_code == 201
    session_id = started.get_json()['data']['id']
    assert client.post('/api/focus-sessions', json={'task_id': task_id}).status_code == 409

    current[0] = base + timedelta(minutes=25)
    paused = client.post(f'/api/focus-sessions/{session_id}/pause')
    assert paused.status_code == 200
    assert paused.get_json()['data']['active_seconds'] == 1500

    current[0] = base + timedelta(minutes=40)
    assert client.post(f'/api/focus-sessions/{session_id}/resume').status_code == 200
    current[0] = base + timedelta(minutes=55)
    finished = client.post(f'/api/focus-sessions/{session_id}/finish')
    assert finished.status_code == 200
    assert finished.get_json()['data']['active_seconds'] == 2400
    assert finished.get_json()['data']['estimated_effort_hours'] == 2.0


def test_focus_history_is_private_and_manager_scope_is_enforced(app, client):
    employee_id = make_user(app, 'privateuser')
    other_id = make_user(app, 'otheruser')
    task_id = make_task(app, employee_id)
    other_task_id = make_task(app, other_id, 'Other task')
    with app.app_context():
        db.session.add_all([
            FocusSession(user_id=employee_id, task_id=task_id, status='finished',
                         started_at=datetime.now(timezone.utc), ended_at=datetime.now(timezone.utc),
                         active_seconds=600),
            FocusSession(user_id=other_id, task_id=other_task_id, status='finished',
                         started_at=datetime.now(timezone.utc), ended_at=datetime.now(timezone.utc),
                         active_seconds=900),
        ])
        db.session.commit()
    login(client, 'privateuser@example.com', 'password123')
    response = client.get('/api/focus-sessions')
    assert response.status_code == 200
    assert {item['task_id'] for item in response.get_json()['data']['items']} == {task_id}


def test_focus_invalid_transitions_and_deactivated_session(app, client):
    user_id = make_user(app, 'stateuser')
    task_id = make_task(app, user_id)
    login(client, 'stateuser@example.com', 'password123')
    assert client.post('/api/focus-sessions/999/pause').status_code == 409
    started = client.post('/api/focus-sessions', json={'task_id': task_id})
    session_id = started.get_json()['data']['id']
    assert client.post(f'/api/focus-sessions/{session_id}/resume').status_code == 409
    with app.app_context():
        db.session.get(User, user_id).account_active = False
        db.session.commit()
    assert client.post(f'/api/focus-sessions/{session_id}/pause').status_code == 403


def test_super_admin_can_view_global_focus_history(app, client):
    admin_id = make_user(app, 'focusadmin', role='super_admin')
    first_id = make_user(app, 'firstworker')
    second_id = make_user(app, 'secondworker')
    first_task = make_task(app, first_id, 'First task')
    second_task = make_task(app, second_id, 'Second task')
    with app.app_context():
        now = datetime.now(timezone.utc)
        db.session.add_all([
            FocusSession(user_id=first_id, task_id=first_task, status='finished',
                         started_at=now, ended_at=now, active_seconds=300),
            FocusSession(user_id=second_id, task_id=second_task, status='finished',
                         started_at=now, ended_at=now, active_seconds=600),
        ])
        db.session.commit()
    login(client, 'focusadmin@example.com', 'password123')
    response = client.get('/api/focus-sessions')
    assert response.status_code == 200
    assert {item['task_id'] for item in response.get_json()['data']['items']} == {first_task, second_task}
