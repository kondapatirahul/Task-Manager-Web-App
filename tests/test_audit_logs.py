"""Regression tests for the administrative audit-log API."""
from datetime import datetime

from app import db
from app.models import AuditLog, User, ROLE_ADMIN


def _login_as(client, app, user_id, role):
    with app.app_context():
        user = db.session.get(User, user_id)
        user.role = role
        db.session.commit()
        email = user.email
    response = client.post('/api/auth/login', json={
        'email': email,
        'password': 'password123',
    })
    assert response.status_code == 200


def _audit_event(action, entity_type='Task', details='event details', created_at=None):
    event = AuditLog(
        action=action,
        entity_type=entity_type,
        details=details,
        created_at=created_at or datetime.utcnow(),
    )
    db.session.add(event)
    return event


def test_employee_cannot_read_audit_logs(auth_client_a):
    response = auth_client_a.get('/api/audit-logs')
    assert response.status_code == 403
    assert response.get_json()['ok'] is False


def test_admin_can_filter_and_paginate_audit_logs(client, app, user_a):
    _login_as(client, app, user_a, ROLE_ADMIN)
    with app.app_context():
        _audit_event('task_created', details='Created a task')
        _audit_event('task_deleted', details='Deleted a task')
        _audit_event('leave_approved', entity_type='LeaveRequest')
        db.session.commit()

    response = client.get('/api/audit-logs?action=task_created&page=1&page_size=1')
    assert response.status_code == 200
    payload = response.get_json()['data']
    assert len(payload['items']) == 1
    assert payload['items'][0]['action'] == 'task_created'
    assert payload['pagination']['total'] == 1
    assert payload['pagination']['page_size'] == 1
    assert payload['filters']['action'] == 'task_created'


def test_audit_log_filters_validate_input(client, app, user_a):
    _login_as(client, app, user_a, ROLE_ADMIN)
    invalid_page = client.get('/api/audit-logs?page=0')
    assert invalid_page.status_code == 400
    assert "'page'" in invalid_page.get_json()['error']

    invalid_dates = client.get('/api/audit-logs?start_date=2026-10-25&end_date=2026-10-01')
    assert invalid_dates.status_code == 400
    assert 'cannot be after' in invalid_dates.get_json()['error']


def test_csv_export_is_available_and_prevents_formula_injection(client, app, user_a):
    _login_as(client, app, user_a, ROLE_ADMIN)
    with app.app_context():
        _audit_event('=HYPERLINK("https://example.invalid")', details='@SUM(A1:A2)')
        db.session.commit()

    response = client.get('/api/audit-logs/export.csv')
    assert response.status_code == 200
    assert 'text/csv' in response.content_type
    body = response.get_data(as_text=True)
    assert "'=HYPERLINK" in body
    assert "'@SUM" in body
    assert 'tasknest-audit-logs.csv' in response.headers['Content-Disposition']
