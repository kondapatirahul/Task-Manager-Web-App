from datetime import date

from app import db
from app.models import Organization, User, Task, TaskDependency, WorkflowTemplate, WorkflowTemplateTask


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


def template_payload(name='Release checklist', visibility='private'):
    return {
        'name': name,
        'description': 'Reusable release work.',
        'default_priority': 'high',
        'visibility': visibility,
        'checklist': [
            {'title': 'Prepare release', 'due_offset_days': 0, 'estimated_effort_hours': 1.5},
            {'title': 'Publish release', 'due_offset_days': 2, 'estimated_effort_hours': 2},
        ],
    }


def test_template_crud_duplicate_archive_and_generation(app, client):
    make_user(app, 'templateowner')
    login(client, 'templateowner')
    created = client.post('/api/workflow-templates', json=template_payload())
    assert created.status_code == 201
    template_id = created.get_json()['data']['id']

    listed = client.get('/api/workflow-templates').get_json()['data']
    assert len(listed) == 1
    assert listed[0]['checklist'][1]['due_offset_days'] == 2

    preview = client.get(f'/api/workflow-templates/{template_id}')
    assert preview.status_code == 200
    assert preview.get_json()['data']['generated_tasks'] == []

    generated = client.post(
        f'/api/workflow-templates/{template_id}/instantiate',
        json={'base_due_date': '2026-10-23'},
    )
    assert generated.status_code == 201
    task_ids = [item['id'] for item in generated.get_json()['data']['tasks']]
    with app.app_context():
        tasks = [db.session.get(Task, task_id) for task_id in task_ids]
        assert tasks[1].due_date == date(2026, 10, 25)
        assert tasks[0].priority == 'high'
        assert WorkflowTemplateTask.query.filter_by(template_id=template_id).count() == 2
        dependency = TaskDependency.query.filter_by(
            blocked_task_id=task_ids[1], blocking_task_id=task_ids[0]
        ).first()
        assert dependency is not None

    duplicate = client.post(f'/api/workflow-templates/{template_id}/duplicate', json={})
    assert duplicate.status_code == 201
    assert duplicate.get_json()['data']['visibility'] == 'private'
    assert client.post(f'/api/workflow-templates/{template_id}/archive').status_code == 200
    assert client.get('/api/workflow-templates').get_json()['data']


def test_template_validation_and_original_is_preserved(app, client):
    make_user(app, 'validationowner')
    login(client, 'validationowner')
    invalid = client.post('/api/workflow-templates', json={
        **template_payload(),
        'checklist': [{'title': ''}],
    })
    assert invalid.status_code == 400
    created = client.post('/api/workflow-templates', json=template_payload()).get_json()['data']
    update = client.put(f"/api/workflow-templates/{created['id']}", json={
        **template_payload('Updated checklist'),
        'checklist': [{'title': 'New step'}],
    })
    assert update.status_code == 200
    with app.app_context():
        generated = client.post(
            f"/api/workflow-templates/{created['id']}/instantiate",
            json={},
        )
        assert generated.status_code == 201
        template = db.session.get(WorkflowTemplate, created['id'])
        assert template.name == 'Updated checklist'
        assert template.checklist[0]['title'] == 'New step'


def test_private_and_organization_template_visibility(app, client):
    with app.app_context():
        org_a = Organization(name='Template Org A')
        org_b = Organization(name='Template Org B')
        db.session.add_all([org_a, org_b])
        db.session.commit()
        org_a_id, org_b_id = org_a.id, org_b.id
    make_user(app, 'managera', role='admin', organization_id=org_a_id)
    make_user(app, 'employeea', organization_id=org_a_id)
    make_user(app, 'employeeb', organization_id=org_b_id)

    login(client, 'managera')
    shared = client.post('/api/workflow-templates', json=template_payload('Shared', 'organization'))
    assert shared.status_code == 201
    shared_id = shared.get_json()['data']['id']
    client.post('/api/auth/logout')
    login(client, 'employeeb')
    assert client.get('/api/workflow-templates').get_json()['data'] == []
    assert client.get(f'/api/workflow-templates/{shared_id}').status_code == 404
    assert client.post(f'/api/workflow-templates/{shared_id}/instantiate', json={}).status_code == 404
