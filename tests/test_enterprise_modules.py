"""Regression coverage for newly introduced enterprise APIs."""
from datetime import datetime, timedelta, timezone
from app import db
from app.models import User, Task, Organization
from app.enterprise_models import Project, ProjectMember, TaskDependency, SavedView

def _ensure_org(app, user_id):
    with app.app_context():
        user = db.session.get(User, user_id)
        if user.organization_id is None:
            org = Organization.query.first()
            if org is None:
                org = Organization(name="Test Organization", slug="test-organization")
                db.session.add(org)
                db.session.flush()
            user.organization_id = org.id
            db.session.commit()

def _login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code in (200, 302)

def test_project_create_and_member_listing(auth_client_a, app, user_a):
    _ensure_org(app, user_a)
    response = auth_client_a.post("/api/enterprise/projects", json={
        "name": "Release Platform", "key": "REL", "description": "Quarterly release planning"
    })
    assert response.status_code == 201
    payload = response.get_json()["data"]
    assert payload["name"] == "Release Platform"
    details = auth_client_a.get(f"/api/enterprise/projects/{payload['id']}")
    assert details.status_code == 200
    assert details.get_json()["data"]["task_count"] == 0

def test_project_key_collision_is_rejected(auth_client_a, app, user_a):
    _ensure_org(app, user_a)
    first = auth_client_a.post("/api/enterprise/projects", json={"name": "Platform", "key": "PLAT"})
    second = auth_client_a.post("/api/enterprise/projects", json={"name": "Platform Two", "key": "PLAT"})
    assert first.status_code == 201
    assert second.status_code == 409

def test_saved_view_rejects_unknown_filter_fields(auth_client_a, app, user_a):
    _ensure_org(app, user_a)
    response = auth_client_a.post("/api/enterprise/views", json={
        "name": "Unsafe view", "entity_type": "task",
        "filters": [{"field": "password_hash", "operator": "eq", "value": "x"}],
        "columns": ["title"]
    })
    assert response.status_code == 400

def test_saved_view_can_be_created_and_listed(auth_client_a, app, user_a):
    _ensure_org(app, user_a)
    response = auth_client_a.post("/api/enterprise/views", json={
        "name": "Urgent work", "entity_type": "task",
        "filters": [{"field": "priority", "operator": "eq", "value": "urgent"}],
        "columns": ["title", "status", "priority"]
    })
    assert response.status_code == 201
    view_id = response.get_json()["data"]["id"]
    listed = auth_client_a.get("/api/enterprise/views?entity_type=task")
    assert listed.status_code == 200
    assert any(item["id"] == view_id for item in listed.get_json()["data"])

def test_custom_field_type_validation():
    from app.services.enterprise import validate_custom_field
    assert validate_custom_field("number", 4.5)[0] is True
    assert validate_custom_field("number", "4.5")[0] is False
    assert validate_custom_field("select", "green", ["red", "blue"])[0] is False

def test_dependency_cycle_detection(app, user_a):
    _ensure_org(app, user_a)
    from app.services.enterprise import detect_dependency_cycle
    with app.app_context():
        from app.models import Organization
        user = db.session.get(User, user_a)
        task_one = Task(title="One", description="One", user_id=user.id, creator_id=user.id,
                        assignee_id=user.id, organization_id=user.organization_id, status="todo")
        task_two = Task(title="Two", description="Two", user_id=user.id, creator_id=user.id,
                        assignee_id=user.id, organization_id=user.organization_id, status="todo")
        db.session.add_all([task_one, task_two])
        db.session.commit()
        row = TaskDependency(organization_id=user.organization_id, task_id=task_one.id,
                             depends_on_task_id=task_two.id, created_by=user.id)
        db.session.add(row)
        db.session.commit()
        assert detect_dependency_cycle(task_two.id, task_one.id) is True
