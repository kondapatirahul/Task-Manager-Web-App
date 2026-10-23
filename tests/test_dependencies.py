from pathlib import Path
from sqlalchemy import text

from app import db
from app.models import (
    Organization,
    Notification,
    Task,
    Team,
    User,
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
    ROLE_SUPER_ADMIN,
    ROLE_TEAM_LEAD,
)


def add_user(app, email, role=ROLE_EMPLOYEE, organization_id=None):
    with app.app_context():
        user = User(
            username=email.split('@')[0],
            full_name=email.split('@')[0],
            email=email,
            role=role,
            organization_id=organization_id,
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


def add_task(app, user_id, title, organization_id=None, team_id=None, status='todo'):
    with app.app_context():
        task = Task(
            title=title,
            user_id=user_id,
            assigned_to_id=user_id,
            team_id=team_id,
            status=status,
        )
        db.session.add(task)
        db.session.commit()
        return task.id


def test_dependency_create_list_remove_and_lifecycle(app, client):
    user_id = add_user(app, 'dependency-owner@example.com')
    blocking_id = add_task(app, user_id, 'Blocking task')
    blocked_id = add_task(app, user_id, 'Blocked task')
    login(client, 'dependency-owner@example.com')

    response = client.post(
        f'/api/tasks/{blocked_id}/dependencies',
        json={'blocking_task_id': blocking_id},
    )
    assert response.status_code == 201
    assert response.get_json()['data']['is_blocked'] is True

    details = client.get(f'/api/tasks/{blocked_id}').get_json()['data']
    assert details['dependencies']['blocked_by'][0]['task_id'] == blocking_id
    assert details['is_blocked_by_dependencies'] is True

    with app.app_context():
        db.session.get(Task, blocking_id).status = 'completed'
        db.session.commit()
    assert client.get(f'/api/tasks/{blocked_id}/dependencies').get_json()['data']['is_blocked'] is False

    with app.app_context():
        db.session.get(Task, blocking_id).status = 'todo'
        db.session.commit()
    assert client.get(f'/api/tasks/{blocked_id}/dependencies').get_json()['data']['is_blocked'] is True

    assert client.delete(
        f'/api/tasks/{blocked_id}/dependencies/{blocking_id}'
    ).status_code == 200
    assert client.get(f'/api/tasks/{blocked_id}/dependencies').get_json()['data']['blocked_by'] == []


def test_dependency_rejects_self_duplicate_missing_and_cycle(app, client):
    user_id = add_user(app, 'dependency-validation@example.com')
    first_id = add_task(app, user_id, 'First')
    second_id = add_task(app, user_id, 'Second')
    third_id = add_task(app, user_id, 'Third')
    login(client, 'dependency-validation@example.com')

    assert client.post(
        f'/api/tasks/{first_id}/dependencies',
        json={'blocking_task_id': first_id},
    ).status_code == 400
    assert client.post(
        f'/api/tasks/{first_id}/dependencies',
        json={'blocking_task_id': 'not-an-id'},
    ).status_code == 400
    assert client.post(
        f'/api/tasks/{first_id}/dependencies',
        json={'blocking_task_id': 999999},
    ).status_code == 404

    assert client.post(
        f'/api/tasks/{first_id}/dependencies',
        json={'blocking_task_id': second_id},
    ).status_code == 201
    assert client.post(
        f'/api/tasks/{first_id}/dependencies',
        json={'blocking_task_id': second_id},
    ).status_code == 409
    assert client.post(
        f'/api/tasks/{second_id}/dependencies',
        json={'blocking_task_id': third_id},
    ).status_code == 201
    assert client.post(
        f'/api/tasks/{third_id}/dependencies',
        json={'blocking_task_id': first_id},
    ).status_code == 409


def test_dependency_permissions_and_organization_isolation(app, client):
    with app.app_context():
        org_a = Organization(name='Dependency A')
        org_b = Organization(name='Dependency B')
        db.session.add_all([org_a, org_b])
        db.session.commit()
        org_a_id, org_b_id = org_a.id, org_b.id
    admin_id = add_user(app, 'dependency-admin@example.com', ROLE_ADMIN, org_a_id)
    employee_a_id = add_user(app, 'dependency-a@example.com', ROLE_EMPLOYEE, org_a_id)
    employee_b_id = add_user(app, 'dependency-b@example.com', ROLE_EMPLOYEE, org_b_id)
    lead_id = add_user(app, 'dependency-lead@example.com', ROLE_TEAM_LEAD, org_a_id)
    super_id = add_user(app, 'dependency-super@example.com', ROLE_SUPER_ADMIN)
    with app.app_context():
        team = Team(name='Dependency team', organization_id=org_a_id, lead_id=lead_id)
        team.members.append(db.session.get(User, employee_a_id))
        db.session.add(team)
        db.session.commit()
        team_id = team.id
    task_a = add_task(app, employee_a_id, 'Organization A task', org_a_id, team_id)
    task_b = add_task(app, employee_b_id, 'Organization B task', org_b_id)

    login(client, 'dependency-admin@example.com')
    assert client.post(
        f'/api/tasks/{task_a}/dependencies',
        json={'blocking_task_id': task_b},
    ).status_code == 404

    client.post('/api/auth/logout')
    login(client, 'dependency-a@example.com')
    assert client.post(
        f'/api/tasks/{task_a}/dependencies',
        json={'blocking_task_id': task_a},
    ).status_code == 400
    assert client.post(
        f'/api/tasks/{task_a}/dependencies',
        json={'blocking_task_id': task_b},
    ).status_code == 404

    client.post('/api/auth/logout')
    login(client, 'dependency-super@example.com')
    assert client.post(
        f'/api/tasks/{task_a}/dependencies',
        json={'blocking_task_id': task_b},
    ).status_code == 201


def test_dependency_deletion_is_protected_and_active_sessions_are_denied(app, client):
    user_id = add_user(app, 'dependency-delete@example.com')
    blocking_id = add_task(app, user_id, 'Required task')
    blocked_id = add_task(app, user_id, 'Dependent task')
    login(client, 'dependency-delete@example.com')
    assert client.post(
        f'/api/tasks/{blocked_id}/dependencies',
        json={'blocking_task_id': blocking_id},
    ).status_code == 201
    assert client.delete(f'/api/tasks/{blocking_id}').status_code == 409

    with app.app_context():
        db.session.execute(
            text('UPDATE users SET account_active = 0 WHERE id = :id'),
            {'id': user_id},
        )
        db.session.commit()
    assert client.get(f'/api/tasks/{blocked_id}/dependencies').status_code == 403
    assert client.post(
        f'/api/tasks/{blocked_id}/dependencies',
        json={'blocking_task_id': blocking_id},
    ).status_code in (401, 403)


def test_dependency_completion_notifies_owner_once_and_reopen_notifies_again(app, client):
    blocker_owner_id = add_user(app, 'dependency-blocker@example.com')
    dependent_owner_id = add_user(app, 'dependency-dependent@example.com')
    add_user(app, 'dependency-notification-admin@example.com', ROLE_SUPER_ADMIN)
    blocking_id = add_task(app, blocker_owner_id, 'Complete prerequisite')
    blocked_id = add_task(app, dependent_owner_id, 'Continue dependent work')

    login(client, 'dependency-notification-admin@example.com')
    assert client.post(
        f'/api/tasks/{blocked_id}/dependencies',
        json={'blocking_task_id': blocking_id},
    ).status_code == 201

    assert client.patch(
        f'/api/tasks/{blocking_id}/complete',
        json={'status': 'completed'},
    ).status_code == 200
    with app.app_context():
        cleared = Notification.query.filter_by(
            recipient_id=dependent_owner_id,
            notification_type='dependency_cleared',
        ).all()
        assert len(cleared) == 1

    assert client.patch(
        f'/api/tasks/{blocking_id}/complete',
        json={'status': 'completed'},
    ).status_code == 200
    with app.app_context():
        assert Notification.query.filter_by(
            recipient_id=dependent_owner_id,
            notification_type='dependency_cleared',
        ).count() == 1

    assert client.patch(
        f'/api/tasks/{blocking_id}/complete',
        json={'status': 'pending'},
    ).status_code == 200
    with app.app_context():
        reopened = Notification.query.filter_by(
            recipient_id=dependent_owner_id,
            notification_type='dependency_reopened',
        ).all()
        assert len(reopened) == 1
        assert 'blocked again' in reopened[0].message


def test_dependency_frontend_handles_safe_dynamic_data_and_errors():
    root = Path(__file__).parents[1]
    task_detail = (root / 'static' / 'js' / 'task_detail.js').read_text()
    task_list = (root / 'static' / 'js' / 'tasks.js').read_text()
    assert 'link.textContent = dependency.title' in task_detail
    assert "status.textContent = state.is_blocked" in task_detail
    assert "results.replaceChildren()" in task_detail
    assert "catch (err)" in task_detail
    assert 'this.escapeHtml(blocker.title)' in task_list
    assert 'No tasks found' in task_list
