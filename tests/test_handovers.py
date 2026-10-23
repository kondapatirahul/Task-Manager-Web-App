from app import db
from app.models import (
    Notification,
    Organization,
    Task,
    TaskHandover,
    User,
    ROLE_EMPLOYEE,
    ROLE_SUPER_ADMIN,
)


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


def test_handover_create_accept_preserves_history_and_notifies(app, client):
    previous_id = make_user(app, 'handover-previous@example.com')
    new_owner_id = make_user(app, 'handover-new@example.com')
    manager_id = make_user(app, 'handover-manager@example.com', ROLE_SUPER_ADMIN)
    with app.app_context():
        task = Task(
            title='Handover task',
            user_id=previous_id,
            assigned_to_id=previous_id,
            estimated_effort_hours=4,
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id

    login(client, 'handover-previous@example.com')
    created = client.post(f'/api/tasks/{task_id}/handovers', json={
        'new_owner_id': new_owner_id,
        'reason': 'Moving to another project',
        'current_progress': 'Implementation is complete.',
        'next_steps': 'Run integration tests.',
    })
    assert created.status_code == 201
    handover_id = created.get_json()['data']['id']
    assert client.post(f'/api/tasks/{task_id}/handovers', json={
        'new_owner_id': new_owner_id,
        'reason': 'Duplicate',
        'current_progress': 'Progress',
        'next_steps': 'Next',
    }).status_code == 409

    login(client, 'handover-new@example.com')
    accepted = client.post(
        f'/api/tasks/{task_id}/handovers/{handover_id}/accept'
    )
    assert accepted.status_code == 200
    with app.app_context():
        assert db.session.get(Task, task_id).assigned_to_id == new_owner_id
        handover = db.session.get(TaskHandover, handover_id)
        assert handover.status == 'accepted'
        assert Notification.query.filter_by(
            recipient_id=previous_id,
            notification_type='handover_accepted',
        ).count() == 1

    login(client, 'handover-manager@example.com')
    history = client.get(f'/api/tasks/{task_id}/handovers')
    assert history.status_code == 200
    assert history.get_json()['data']['items'][0]['status'] == 'accepted'


def test_handover_decline_cancel_and_invalid_input(app, client):
    previous_id = make_user(app, 'handover-decline-previous@example.com')
    new_owner_id = make_user(app, 'handover-decline-new@example.com')
    with app.app_context():
        task = Task(title='Decline task', user_id=previous_id, assigned_to_id=previous_id)
        db.session.add(task)
        db.session.commit()
        task_id = task.id

    login(client, 'handover-decline-previous@example.com')
    invalid = client.post(f'/api/tasks/{task_id}/handovers', json={
        'new_owner_id': new_owner_id,
        'reason': '',
        'current_progress': 'Progress',
        'next_steps': 'Next',
    })
    assert invalid.status_code == 400
    created = client.post(f'/api/tasks/{task_id}/handovers', json={
        'new_owner_id': new_owner_id,
        'reason': 'Need a new owner',
        'current_progress': 'Initial review complete.',
        'next_steps': 'Continue implementation.',
    })
    handover_id = created.get_json()['data']['id']

    login(client, 'handover-decline-new@example.com')
    assert client.post(
        f'/api/tasks/{task_id}/handovers/{handover_id}/decline',
        json={'reason': 'Unavailable this week'},
    ).status_code == 200
    with app.app_context():
        assert db.session.get(Task, task_id).assigned_to_id == previous_id


def test_pending_handover_blocks_reassignment_and_stale_acceptance(app, client):
    previous_id = make_user(app, 'handover-stale-previous@example.com')
    new_owner_id = make_user(app, 'handover-stale-new@example.com')
    manager_id = make_user(app, 'handover-stale-manager@example.com', ROLE_SUPER_ADMIN)
    with app.app_context():
        task = Task(title='Stale task', user_id=previous_id, assigned_to_id=previous_id)
        db.session.add(task)
        db.session.commit()
        task_id = task.id

    login(client, 'handover-stale-previous@example.com')
    created = client.post(f'/api/tasks/{task_id}/handovers', json={
        'new_owner_id': new_owner_id,
        'reason': 'Planned transition',
        'current_progress': 'Work started.',
        'next_steps': 'Finish the task.',
    })
    handover_id = created.get_json()['data']['id']

    login(client, 'handover-stale-manager@example.com')
    blocked = client.put(f'/api/tasks/{task_id}', json={
        'assigned_to_id': new_owner_id,
    })
    assert blocked.status_code == 409
    with app.app_context():
        task = db.session.get(Task, task_id)
        task.status = 'completed'
        db.session.commit()

    login(client, 'handover-stale-new@example.com')
    accepted = client.post(
        f'/api/tasks/{task_id}/handovers/{handover_id}/accept'
    )
    assert accepted.status_code == 409
    with app.app_context():
        assert db.session.get(TaskHandover, handover_id).status == 'expired'


def test_unauthorized_employee_cannot_view_or_cancel_handover(app, client):
    previous_id = make_user(app, 'handover-private-previous@example.com')
    new_owner_id = make_user(app, 'handover-private-new@example.com')
    outsider_id = make_user(app, 'handover-private-outsider@example.com')
    with app.app_context():
        task = Task(title='Private task', user_id=previous_id, assigned_to_id=previous_id)
        db.session.add(task)
        db.session.commit()
        task_id = task.id

    login(client, 'handover-private-previous@example.com')
    created = client.post(f'/api/tasks/{task_id}/handovers', json={
        'new_owner_id': new_owner_id,
        'reason': 'Transition',
        'current_progress': 'Progress',
        'next_steps': 'Next steps',
    })
    handover_id = created.get_json()['data']['id']
    login(client, 'handover-private-outsider@example.com')
    assert client.get(f'/api/tasks/{task_id}/handovers').status_code == 404
    assert client.post(
        f'/api/tasks/{task_id}/handovers/{handover_id}/cancel'
    ).status_code == 404


def test_handover_rejects_cross_organization_owner(app, client):
    with app.app_context():
        org_a = Organization(name='Handover Org A')
        org_b = Organization(name='Handover Org B')
        db.session.add_all([org_a, org_b])
        db.session.flush()
        previous = User(
            username='handover-org-previous',
            full_name='Org Previous',
            email='handover-org-previous@example.com',
            organization_id=org_a.id,
        )
        other = User(
            username='handover-org-other',
            full_name='Org Other',
            email='handover-org-other@example.com',
            organization_id=org_b.id,
        )
        previous.set_password('password123')
        other.set_password('password123')
        db.session.add_all([previous, other])
        db.session.flush()
        task = Task(
            title='Organization handover',
            user_id=previous.id,
            assigned_to_id=previous.id,
        )
        db.session.add(task)
        db.session.commit()
        task_id = task.id
        other_id = other.id

    login(client, 'handover-org-previous@example.com')
    response = client.post(f'/api/tasks/{task_id}/handovers', json={
        'new_owner_id': other_id,
        'reason': 'Cross organization attempt',
        'current_progress': 'Progress',
        'next_steps': 'Next',
    })
    assert response.status_code == 403
