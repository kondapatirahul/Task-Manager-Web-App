"""Regression tests for the finance, risk, OKR, and asset management APIs."""
from datetime import date, timedelta
from decimal import Decimal
import pytest
from app import db
from app.models import User, Organization, Task
from app.domain_models import BudgetTransaction, RiskRecord, KeyResult, Objective, AssetRecord


def make_user(username, role="admin", org_id=None):
    user = User(username=username, full_name=username.title(), email=f"{username}@example.com",
                role=role, organization_id=org_id)
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    return user


def login(client, username):
    return client.post("/api/auth/login", json={"email": f"{username}@example.com", "password": "password123"})


def org():
    row = Organization(name="Enterprise Operations Test")
    db.session.add(row)
    db.session.commit()
    return row


def test_finance_transaction_requires_positive_amount(app, client):
    with app.app_context():
        organization = org()
        make_user("financeadmin", org_id=organization.id)
    login(client, "financeadmin")
    response = client.post("/api/finance/transactions", json={"amount": "0", "category": "travel"})
    assert response.status_code == 400
    assert "greater than zero" in response.get_json()["error"]


def test_finance_transaction_approval_updates_task_spent_budget(app, client):
    with app.app_context():
        organization = org()
        user = make_user("ledgeradmin", org_id=organization.id)
        task = Task(title="Purchase laptop", description="Test", user_id=user.id, creator_id=user.id,
                    assignee_id=user.id, organization_id=organization.id, actual_budget=Decimal("1000.00"),
                    spent_budget=Decimal("0.00"))
        db.session.add(task)
        db.session.commit()
        task_id = task.id
    login(client, "ledgeradmin")
    created = client.post("/api/finance/transactions", json={"amount": "125.50", "task_id": task_id,
        "transaction_date": date.today().isoformat(), "category": "equipment", "merchant": "Example supplier"})
    assert created.status_code == 201
    tx_id = created.get_json()["data"]["id"]
    approved = client.post(f"/api/finance/transactions/{tx_id}/approve", json={})
    assert approved.status_code == 200
    with app.app_context():
        task = db.session.get(Task, task_id)
        assert Decimal(str(task.spent_budget)) == Decimal("125.50")
        tx = db.session.get(BudgetTransaction, tx_id)
        assert tx.status == "approved"


def test_finance_reject_requires_reason(app, client):
    with app.app_context():
        organization = org()
        user = make_user("rejectadmin", org_id=organization.id)
        tx = BudgetTransaction(organization_id=organization.id, created_by=user.id, category="travel",
            transaction_type="expense", amount=Decimal("45.00"), transaction_date=date.today(), status="submitted")
        db.session.add(tx)
        db.session.commit()
        tx_id = tx.id
    login(client, "rejectadmin")
    response = client.post(f"/api/finance/transactions/{tx_id}/reject", json={"reason": "  "})
    assert response.status_code == 400


def test_risk_score_and_severity_are_deterministic(app):
    with app.app_context():
        organization = org()
        user = make_user("riskowner", org_id=organization.id)
        risk = RiskRecord(organization_id=organization.id, created_by=user.id, key="R-TEST-0001",
            title="Potential outage", probability=5, impact=4)
        db.session.add(risk)
        db.session.commit()
        assert risk.score == 20
        assert risk.severity == "critical"
        assert risk.to_dict()["score"] == 20


def test_risk_api_validates_probability(app, client):
    with app.app_context():
        organization = org()
        make_user("riskadmin", org_id=organization.id)
    login(client, "riskadmin")
    response = client.post("/api/risks", json={"title": "Invalid score", "probability": 9, "impact": 2})
    assert response.status_code == 400


def test_objective_key_result_progress_clamps_to_range(app):
    with app.app_context():
        organization = org()
        user = make_user("okrowner", org_id=organization.id)
        objective = Objective(organization_id=organization.id, owner_id=user.id, created_by=user.id, title="Improve delivery")
        db.session.add(objective)
        db.session.flush()
        result = KeyResult(objective_id=objective.id, title="Increase reliability", start_value=0,
                           current_value=150, target_value=100, direction="increase")
        db.session.add(result)
        db.session.commit()
        assert result.progress == 100
        result.current_value = -5
        db.session.commit()
        assert result.progress == 0


def test_objective_api_creates_and_updates_key_result_history(app, client):
    with app.app_context():
        organization = org()
        make_user("okradmin", org_id=organization.id)
    login(client, "okradmin")
    created = client.post("/api/objectives", json={"title": "Improve support", "period": "quarterly"})
    assert created.status_code == 201
    objective_id = created.get_json()["data"]["id"]
    key_result = client.post(f"/api/objectives/{objective_id}/key-results", json={
        "title": "Reduce response time", "start_value": 10, "current_value": 10, "target_value": 2, "direction": "decrease"})
    assert key_result.status_code == 201
    result_id = key_result.get_json()["data"]["id"]
    updated = client.patch(f"/api/objectives/{objective_id}/key-results/{result_id}", json={"current_value": 5, "note": "Mid-quarter update"})
    assert updated.status_code == 200
    history = client.get(f"/api/objectives/{objective_id}/key-results/{result_id}/history")
    assert history.status_code == 200
    assert len(history.get_json()["data"]["history"]) == 1


def test_asset_tag_is_unique_per_organization(app, client):
    with app.app_context():
        organization = org()
        make_user("assetadmin", org_id=organization.id)
    login(client, "assetadmin")
    payload = {"asset_tag": "LAP-0001", "name": "Finance laptop", "category": "laptop", "purchase_cost": "75000.00"}
    first = client.post("/api/assets", json=payload)
    second = client.post("/api/assets", json=payload)
    assert first.status_code == 201
    assert second.status_code == 409


def test_employee_cannot_register_assets(app, client):
    with app.app_context():
        organization = org()
        make_user("assetemployee", role="employee", org_id=organization.id)
    login(client, "assetemployee")
    response = client.post("/api/assets", json={"asset_tag": "PHONE-1", "name": "Phone"})
    assert response.status_code == 403


def test_asset_assignment_and_return_are_stateful(app, client):
    with app.app_context():
        organization = org()
        admin = make_user("assetmanager", org_id=organization.id)
        employee = make_user("assetrecipient", role="employee", org_id=organization.id)
        asset = AssetRecord(organization_id=organization.id, asset_tag="MON-100", name="Monitor", created_by=admin.id)
        db.session.add(asset)
        db.session.commit()
        asset_id, employee_id = asset.id, employee.id
    login(client, "assetmanager")
    assigned = client.post(f"/api/assets/{asset_id}/assignments", json={"user_id": employee_id})
    assert assigned.status_code == 201
    with app.app_context():
        assert db.session.get(AssetRecord, asset_id).status == "assigned"
    returned = client.post(f"/api/assets/{asset_id}/return", json={"condition_in": "Good condition"})
    assert returned.status_code == 200
    with app.app_context():
        assert db.session.get(AssetRecord, asset_id).status == "available"
