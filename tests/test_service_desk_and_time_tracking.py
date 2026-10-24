"""Regression coverage for support desk and timesheet workflows."""
from datetime import date
import pytest
from app import db
from app.models import Organization, User
from app.domain_models import SupportTicket, TimeEntry, KnowledgeArticle


def _attach_org(user_id, name='Acme Test Org'):
    org = Organization(name=name)
    db.session.add(org)
    db.session.flush()
    user = db.session.get(User, user_id)
    user.organization_id = org.id
    db.session.commit()
    return org.id


def test_employee_can_create_and_list_own_support_ticket(app, auth_client_a, user_a):
    with app.app_context():
        _attach_org(user_a)
    response = auth_client_a.post('/api/service-desk/tickets', json={
        'subject': 'VPN access required', 'description': 'Cannot connect to the company VPN.',
        'category': 'access', 'priority': 'high'
    })
    assert response.status_code == 201
    created = response.get_json()['data']
    assert created['ticket_key'].startswith('SD-')
    assert created['status'] == 'open'
    listed = auth_client_a.get('/api/service-desk/tickets')
    assert listed.status_code == 200
    assert listed.get_json()['data']['total'] == 1


def test_ticket_creation_rejects_invalid_priority(app, auth_client_a, user_a):
    with app.app_context():
        _attach_org(user_a)
    response = auth_client_a.post('/api/service-desk/tickets', json={
        'subject': 'Something', 'description': 'Details', 'priority': 'blocker'
    })
    assert response.status_code == 400


def test_employee_cannot_create_internal_note(app, auth_client_a, user_a):
    with app.app_context():
        org_id = _attach_org(user_a)
        ticket = SupportTicket(organization_id=org_id, ticket_key='SD-2601-00001', requester_id=user_a,
                               subject='A request', description='Details')
        db.session.add(ticket)
        db.session.commit()
        ticket_id = ticket.id
    response = auth_client_a.post(f'/api/service-desk/tickets/{ticket_id}/comments', json={
        'body': 'Private staff note', 'internal_note': True
    })
    assert response.status_code == 403


def test_knowledge_article_creation_requires_admin(app, auth_client_a, user_a):
    with app.app_context():
        _attach_org(user_a)
    response = auth_client_a.post('/api/service-desk/knowledge', json={
        'title': 'VPN setup', 'body': 'Step-by-step VPN instructions', 'status': 'published'
    })
    assert response.status_code == 403


def test_time_entry_requires_valid_minutes(app, auth_client_a, user_a):
    with app.app_context():
        _attach_org(user_a)
    response = auth_client_a.post('/api/time-tracking/entries', json={
        'work_date': date.today().isoformat(), 'minutes': 1500, 'description': 'Over limit'
    })
    assert response.status_code == 400


def test_employee_can_create_and_submit_time_entry(app, auth_client_a, user_a):
    with app.app_context():
        _attach_org(user_a)
    response = auth_client_a.post('/api/time-tracking/entries', json={
        'work_date': date.today().isoformat(), 'minutes': 75, 'description': 'Review and testing', 'billable': True
    })
    assert response.status_code == 201
    entry_id = response.get_json()['data']['id']
    submit = auth_client_a.post(f'/api/time-tracking/entries/{entry_id}/submit', json={})
    assert submit.status_code == 200
    assert submit.get_json()['data']['status'] == 'submitted'


def test_vendor_api_requires_admin(client, app, user_a):
    from app.models import ROLE_ADMIN
    with app.app_context():
        user = db.session.get(User, user_a)
        org = Organization(name='Vendor Test Org')
        db.session.add(org)
        db.session.flush()
        user.organization_id = org.id
        user.role = ROLE_ADMIN
        db.session.commit()
    response = client.post('/api/auth/login', json={
        'email': 'usera@example.com', 'password': 'password123'
    })
    assert response.status_code == 200
    created = client.post('/api/vendors', json={
        'name': 'Acme Cloud Services', 'vendor_code': 'ACME-001', 'risk_tier': 'low', 'status': 'active'
    })
    assert created.status_code == 201
    assert created.get_json()['data']['vendor_code'] == 'ACME-001'


def test_vendor_duplicate_code_is_rejected(client, app, user_a):
    from app.models import ROLE_ADMIN
    with app.app_context():
        org = Organization(name='Duplicate Vendor Org')
        db.session.add(org)
        db.session.flush()
        user = db.session.get(User, user_a)
        user.organization_id = org.id
        user.role = ROLE_ADMIN
        db.session.commit()
    client.post('/api/auth/login', json={'email': 'usera@example.com', 'password': 'password123'})
    payload = {'name': 'Vendor One', 'vendor_code': 'SAME-1'}
    assert client.post('/api/vendors', json=payload).status_code == 201
    duplicate = client.post('/api/vendors', json={'name': 'Vendor Two', 'vendor_code': 'SAME-1'})
    assert duplicate.status_code == 409
