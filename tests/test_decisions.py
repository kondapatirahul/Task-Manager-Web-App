from app import db
from app.models import (
    DecisionHistory,
    Organization,
    ProjectDecision,
    Task,
    Team,
    User,
    team_members,
    ROLE_ADMIN,
    ROLE_EMPLOYEE,
)


def user(app, email, role=ROLE_EMPLOYEE, organization_id=None):
    with app.app_context():
        record = User(
            username=email.split('@')[0],
            full_name=email.split('@')[0],
            email=email,
            role=role,
            organization_id=organization_id,
        )
        record.set_password('password123')
        db.session.add(record)
        db.session.commit()
        return record.id


def login(client, email):
    response = client.post('/api/auth/login', json={
        'email': email,
        'password': 'password123',
    })
    assert response.status_code == 200


def setup_project(app):
    with app.app_context():
        org = Organization(name='Decision Org')
        db.session.add(org)
        db.session.flush()
        admin = User(
            username='decision-admin',
            full_name='Decision Admin',
            email='decision-admin@example.com',
            role=ROLE_ADMIN,
            organization_id=org.id,
        )
        employee = User(
            username='decision-member',
            full_name='Decision Member',
            email='decision-member@example.com',
            role=ROLE_EMPLOYEE,
            organization_id=org.id,
        )
        admin.set_password('password123')
        employee.set_password('password123')
        db.session.add_all([admin, employee])
        db.session.flush()
        team = Team(name='Decision Project', organization_id=org.id, lead_id=admin.id)
        team.members.append(employee)
        task = Task(
            title='Decision task',
            user_id=admin.id,
            assigned_to_id=employee.id,
            team=team,
        )
        db.session.add(task)
        db.session.commit()
        return admin.email, employee.email, team.id, task.id, org.id


def test_decision_crud_search_linked_tasks_and_history(app, client):
    admin_email, _, team_id, task_id, _ = setup_project(app)
    login(client, admin_email)
    created = client.post('/api/decisions', json={
        'team_id': team_id,
        'title': 'Use event-driven notifications',
        'details': 'Notifications should be persisted before delivery.',
        'rationale': 'This preserves auditability.',
        'alternatives': 'Polling was considered.',
        'task_ids': [task_id],
    })
    assert created.status_code == 201
    decision = created.get_json()['data']
    assert decision['linked_tasks'][0]['id'] == task_id
    decision_id = decision['id']
    assert len(decision['history']) == 1

    search = client.get('/api/decisions?q=event-driven')
    assert search.status_code == 200
    assert search.get_json()['data']['items'][0]['id'] == decision_id
    linked = client.get(f'/api/decisions?task_id={task_id}')
    assert linked.status_code == 200
    assert len(linked.get_json()['data']['items']) == 1

    updated = client.put(f'/api/decisions/{decision_id}', json={
        'title': 'Use persisted notifications',
        'details': 'Persist notifications before delivery.',
        'rationale': 'Auditability and retries.',
        'alternatives': 'Polling remains rejected.',
        'status': 'accepted',
        'change_note': 'Architecture review accepted this decision.',
    })
    assert updated.status_code == 200
    assert updated.get_json()['data']['status'] == 'accepted'
    with app.app_context():
        assert DecisionHistory.query.filter_by(decision_id=decision_id).count() == 2
        assert db.session.get(ProjectDecision, decision_id).title == 'Use persisted notifications'


def test_employee_can_view_but_cannot_create_or_update_decisions(app, client):
    _, employee_email, team_id, _, _ = setup_project(app)
    login(client, employee_email)
    assert client.get('/api/decisions').status_code == 200
    created = client.post('/api/decisions', json={
        'team_id': team_id,
        'title': 'Unauthorized',
        'details': 'Should not be saved.',
        'rationale': 'No permission.',
    })
    assert created.status_code == 403


def test_decisions_are_isolated_by_organization(app, client):
    admin_email, _, team_id, _, _ = setup_project(app)
    other_org_id = user(app, 'other-decision-admin@example.com', ROLE_ADMIN)
    with app.app_context():
        other = db.session.get(User, other_org_id)
        org = Organization(name='Other Decision Org')
        db.session.add(org)
        db.session.flush()
        other.organization_id = org.id
        other_team = Team(name='Other Project', organization_id=org.id, lead_id=other.id)
        db.session.add(other_team)
        db.session.flush()
        decision = ProjectDecision(
            team_id=other_team.id,
            author_id=other.id,
            title='Confidential decision',
            details='Private details.',
            rationale='Private rationale.',
        )
        db.session.add(decision)
        db.session.commit()
        decision_id = decision.id
    login(client, admin_email)
    assert client.get(f'/api/decisions/{decision_id}').status_code == 404
    assert client.get('/api/decisions').get_json()['data']['items'] == []


def test_invalid_decision_input_is_rejected(app, client):
    admin_email, _, team_id, _, _ = setup_project(app)
    login(client, admin_email)
    assert client.post('/api/decisions', json={
        'team_id': team_id,
        'title': '',
        'details': 'Details',
        'rationale': 'Reason',
    }).status_code == 400
    assert client.get('/api/decisions?status=unknown').status_code == 400
