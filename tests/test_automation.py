from datetime import date, datetime, timedelta, timezone

from app import db
from app.models import (
    AutomationExecution,
    AutomationRule,
    Organization,
    Task,
    TaskDependency,
    User,
    WorkflowTemplate,
)
from app.services.automation import process_overdue, run_recurring_rules


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


def login(client, username):
    response = client.post('/api/auth/login', json={
        'email': f'{username}@example.com',
        'password': 'password123',
    })
    assert response.status_code == 200


def test_overdue_processing_is_deduplicated(app):
    owner_id = make_user(app, 'overdueowner')
    with app.app_context():
        task = Task(
            title='Late task',
            user_id=owner_id,
            status='in_progress',
            due_date=date(2026, 10, 20),
        )
        db.session.add(task)
        db.session.commit()
        assert process_overdue(date(2026, 10, 23)) == 1
        assert process_overdue(date(2026, 10, 23)) == 0


def test_recurring_task_execution_is_idempotent_and_records_failure(app):
    owner_id = make_user(app, 'recurringowner')
    with app.app_context():
        source = Task(title='Weekly source', user_id=owner_id, status='pending', priority='medium')
        db.session.add(source)
        db.session.flush()
        run_at = datetime(2026, 10, 23, 8, tzinfo=timezone.utc)
        rule = AutomationRule(
            owner_id=owner_id,
            source_task_id=source.id,
            rule_type='recurring_task',
            name='Weekly copy',
            schedule='weekly',
            next_run_at=run_at,
        )
        db.session.add(rule)
        db.session.commit()
        assert run_recurring_rules(run_at) == 1
        assert run_recurring_rules(run_at) == 0
        assert Task.query.filter(Task.title == 'Weekly source').count() == 2
        assert AutomationExecution.query.filter_by(status='succeeded').count() == 1


def test_automation_api_enforces_scope_and_enable_disable(app, client):
    with app.app_context():
        org_a = Organization(name='Automation A')
        org_b = Organization(name='Automation B')
        db.session.add_all([org_a, org_b])
        db.session.commit()
        admin_id = make_user(app, 'automationadmin', role='admin', organization_id=org_a.id)
        other_id = make_user(app, 'automationother', organization_id=org_b.id)
        source = Task(title='Scoped source', user_id=admin_id, status='pending')
        db.session.add(source)
        db.session.commit()
        source_id = source.id
    login(client, 'automationadmin')
    response = client.post('/api/automation/rules', json={
        'rule_type': 'recurring_task',
        'name': 'Scoped recurrence',
        'schedule': 'daily',
        'next_run_at': '2026-10-23T08:00:00+00:00',
        'source_task_id': source_id,
    })
    assert response.status_code == 201
    rule_id = response.get_json()['data']['id']
    assert client.patch(f'/api/automation/rules/{rule_id}', json={'enabled': False}).status_code == 200
    client.post('/api/auth/logout')
    login(client, 'automationother')
    assert client.get(f'/api/automation/rules/{rule_id}/executions').status_code == 404
