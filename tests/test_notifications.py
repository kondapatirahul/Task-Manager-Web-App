from datetime import date, timedelta

from app import db
from app.models import Activity, Notification, Task, User, ROLE_ADMIN, ROLE_EMPLOYEE
from app.services.notifications import generate_deadline_reminders


def make_user(app, email, role=ROLE_EMPLOYEE):
    with app.app_context():
        user = User(
            username=email.split('@')[0],
            full_name=email.split('@')[0].title(),
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


def test_assignment_creates_notification_and_activity(app, client):
    creator_id = make_user(app, 'creator@example.com')
    assignee_id = make_user(app, 'assignee@example.com')
    with app.app_context():
        task = Task(title='Assigned task', user_id=creator_id)
        db.session.add(task)
        db.session.commit()
        task_id = task.id

    login(client, 'creator@example.com')
    response = client.put(f'/api/tasks/{task_id}', json={'assigned_to_id': assignee_id})
    assert response.status_code == 200

    with app.app_context():
        notification = Notification.query.filter_by(
            recipient_id=assignee_id, notification_type='task_reassigned'
        ).first()
        assert notification is not None
        assert Activity.query.filter_by(task_id=task_id).count() >= 1


def test_notification_read_actions_are_private(app, client):
    first_id = make_user(app, 'first-notify@example.com')
    second_id = make_user(app, 'second-notify@example.com')
    with app.app_context():
        db.session.add(Notification(
            recipient_id=second_id,
            notification_type='task_created',
            title='Private',
            message='Private notification',
        ))
        db.session.commit()
        notification_id = Notification.query.filter_by(recipient_id=second_id).first().id

    login(client, 'first-notify@example.com')
    assert client.get('/api/notifications').get_json()['data']['unread_count'] == 0
    assert client.patch(f'/api/notifications/{notification_id}/read').status_code == 404


def test_activity_visibility_pagination_and_reminder_deduplication(app, client):
    employee_id = make_user(app, 'activity-employee@example.com')
    other_id = make_user(app, 'activity-other@example.com')
    due_date = date(2026, 10, 24)
    with app.app_context():
        db.session.add_all([
            Task(title='Reminder task', user_id=employee_id, assigned_to_id=employee_id, due_date=due_date),
            Task(title='Completed task', user_id=employee_id, status='completed', due_date=due_date),
            Task(title='No deadline', user_id=employee_id),
            Activity(actor_id=other_id, activity_type='private', description='Other user task'),
        ])
        db.session.commit()
        assert generate_deadline_reminders(date(2026, 10, 23)) == 1
        assert generate_deadline_reminders(date(2026, 10, 23)) == 0

    login(client, 'activity-employee@example.com')
    notifications = client.get('/api/notifications?per_page=1').get_json()['data']
    assert notifications['has_more'] is False
    assert notifications['items'][0]['type'] == 'deadline_reminder'
    activity = client.get('/api/activity?per_page=1').get_json()['data']
    assert all(item['description'] != 'Other user task' for item in activity['items'])


def test_admin_can_view_activity_and_dashboard_regression(app, client):
    make_user(app, 'activity-admin@example.com', ROLE_ADMIN)
    login(client, 'activity-admin@example.com')
    assert client.get('/api/activity').status_code == 200
    assert 'Dashboard' in client.get('/dashboard').get_data(as_text=True)
