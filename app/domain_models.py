"""Normalized enterprise finance, risk, objectives, and asset-management models.

The models in this module are intentionally separate from the legacy schema.
They are registered when the corresponding route blueprints are imported before
create_all runs. All money is stored as fixed-precision Decimal/NUMERIC values.
"""
from datetime import datetime, timezone
from decimal import Decimal
from app import db


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BudgetTransaction(db.Model):
    __tablename__ = "tn_budget_transactions"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("tn_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category = db.Column(db.String(32), nullable=False, default="operational")
    transaction_type = db.Column(db.String(16), nullable=False, default="expense")
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    merchant = db.Column(db.String(160), nullable=False, default="")
    reference = db.Column(db.String(100), nullable=False, default="")
    description = db.Column(db.String(2000), nullable=False, default="")
    transaction_date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="submitted", index=True)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    rejected_reason = db.Column(db.String(1000), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_utc, onupdate=now_utc)
    __table_args__ = (
        db.CheckConstraint("amount > 0", name="ck_tn_budget_transaction_positive"),
        db.CheckConstraint("transaction_type IN ('expense','credit','adjustment')", name="ck_tn_budget_transaction_type"),
        db.Index("ix_tn_budget_org_status_date", "organization_id", "status", "transaction_date"),
    )

    def to_dict(self):
        return {"id": self.id, "organization_id": self.organization_id, "task_id": self.task_id,
                "project_id": self.project_id, "created_by": self.created_by, "category": self.category,
                "transaction_type": self.transaction_type, "amount": str(self.amount), "currency": self.currency,
                "merchant": self.merchant, "reference": self.reference, "description": self.description,
                "transaction_date": self.transaction_date.isoformat() if self.transaction_date else None,
                "status": self.status, "approved_by": self.approved_by,
                "approved_at": self.approved_at.isoformat() if self.approved_at else None,
                "rejected_reason": self.rejected_reason, "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


class ExpensePolicy(db.Model):
    __tablename__ = "tn_expense_policies"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(32), nullable=False, default="operational")
    maximum_amount = db.Column(db.Numeric(14, 2), nullable=True)
    requires_receipt_above = db.Column(db.Numeric(14, 2), nullable=True)
    requires_approval = db.Column(db.Boolean, nullable=False, default=True)
    allowed_roles_json = db.Column(db.Text, nullable=False, default='["employee","team_lead","admin","super_admin"]')
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_utc, onupdate=now_utc)

    def to_dict(self):
        import json
        return {"id": self.id, "name": self.name, "category": self.category,
                "maximum_amount": str(self.maximum_amount) if self.maximum_amount is not None else None,
                "requires_receipt_above": str(self.requires_receipt_above) if self.requires_receipt_above is not None else None,
                "requires_approval": self.requires_approval, "allowed_roles": json.loads(self.allowed_roles_json or "[]"),
                "active": self.active, "created_by": self.created_by,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


class PurchaseRequest(db.Model):
    __tablename__ = "tn_purchase_requests"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey("tn_projects.id", ondelete="SET NULL"), nullable=True)
    title = db.Column(db.String(180), nullable=False)
    vendor = db.Column(db.String(180), nullable=False, default="")
    justification = db.Column(db.Text, nullable=False, default="")
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    status = db.Column(db.String(24), nullable=False, default="pending", index=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    review_note = db.Column(db.String(1000), nullable=False, default="")
    reviewed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_utc, onupdate=now_utc)
    __table_args__ = (db.CheckConstraint("amount > 0", name="ck_tn_purchase_amount_positive"),)

    def to_dict(self):
        return {"id": self.id, "requester_id": self.requester_id, "task_id": self.task_id,
                "project_id": self.project_id, "title": self.title, "vendor": self.vendor,
                "justification": self.justification, "amount": str(self.amount), "currency": self.currency,
                "status": self.status, "reviewer_id": self.reviewer_id, "review_note": self.review_note,
                "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


class RiskRecord(db.Model):
    __tablename__ = "tn_risk_records"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("tn_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    key = db.Column(db.String(24), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    category = db.Column(db.String(32), nullable=False, default="delivery")
    probability = db.Column(db.Integer, nullable=False, default=3)
    impact = db.Column(db.Integer, nullable=False, default=3)
    response_strategy = db.Column(db.String(24), nullable=False, default="mitigate")
    mitigation_plan = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(24), nullable=False, default="identified", index=True)
    due_date = db.Column(db.Date, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_utc, onupdate=now_utc)
    __table_args__ = (
        db.UniqueConstraint("organization_id", "key", name="uq_tn_risk_org_key"),
        db.CheckConstraint("probability BETWEEN 1 AND 5", name="ck_tn_risk_probability"),
        db.CheckConstraint("impact BETWEEN 1 AND 5", name="ck_tn_risk_impact"),
        db.Index("ix_tn_risk_org_status_score", "organization_id", "status", "probability", "impact"),
    )

    @property
    def score(self):
        return int(self.probability or 0) * int(self.impact or 0)

    @property
    def severity(self):
        score = self.score
        return "critical" if score >= 20 else "high" if score >= 15 else "medium" if score >= 8 else "low"

    def to_dict(self):
        return {"id": self.id, "organization_id": self.organization_id, "project_id": self.project_id,
                "owner_id": self.owner_id, "created_by": self.created_by, "key": self.key,
                "title": self.title, "description": self.description, "category": self.category,
                "probability": self.probability, "impact": self.impact, "score": self.score,
                "severity": self.severity, "response_strategy": self.response_strategy,
                "mitigation_plan": self.mitigation_plan, "status": self.status,
                "due_date": self.due_date.isoformat() if self.due_date else None,
                "closed_at": self.closed_at.isoformat() if self.closed_at else None,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


class RiskAction(db.Model):
    __tablename__ = "tn_risk_actions"
    id = db.Column(db.Integer, primary_key=True)
    risk_id = db.Column(db.Integer, db.ForeignKey("tn_risk_records.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(24), nullable=False, default="open")
    completion_note = db.Column(db.String(1000), nullable=False, default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    completed_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {"id": self.id, "risk_id": self.risk_id, "title": self.title, "owner_id": self.owner_id,
                "due_date": self.due_date.isoformat() if self.due_date else None, "status": self.status,
                "completion_note": self.completion_note, "created_by": self.created_by,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "completed_at": self.completed_at.isoformat() if self.completed_at else None}


class Objective(db.Model):
    __tablename__ = "tn_objectives"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("tn_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    period = db.Column(db.String(32), nullable=False, default="quarterly")
    start_date = db.Column(db.Date, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(24), nullable=False, default="active", index=True)
    confidence = db.Column(db.Integer, nullable=False, default=3)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_utc, onupdate=now_utc)
    __table_args__ = (db.CheckConstraint("confidence BETWEEN 1 AND 5", name="ck_tn_objective_confidence"),)

    def to_dict(self, include_key_results=False):
        result = {"id": self.id, "organization_id": self.organization_id, "project_id": self.project_id,
                  "owner_id": self.owner_id, "created_by": self.created_by, "title": self.title,
                  "description": self.description, "period": self.period,
                  "start_date": self.start_date.isoformat() if self.start_date else None,
                  "due_date": self.due_date.isoformat() if self.due_date else None, "status": self.status,
                  "confidence": self.confidence, "progress": self.progress,
                  "created_at": self.created_at.isoformat() if self.created_at else None,
                  "updated_at": self.updated_at.isoformat() if self.updated_at else None}
        if include_key_results:
            result["key_results"] = [item.to_dict() for item in KeyResult.query.filter_by(objective_id=self.id).all()]
        return result

    @property
    def progress(self):
        results = KeyResult.query.filter_by(objective_id=self.id).all()
        if not results:
            return 0
        return round(sum(item.progress for item in results) / len(results))


class KeyResult(db.Model):
    __tablename__ = "tn_key_results"
    id = db.Column(db.Integer, primary_key=True)
    objective_id = db.Column(db.Integer, db.ForeignKey("tn_objectives.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    metric_type = db.Column(db.String(20), nullable=False, default="numeric")
    unit = db.Column(db.String(32), nullable=False, default="")
    start_value = db.Column(db.Numeric(16, 4), nullable=False, default=Decimal("0"))
    current_value = db.Column(db.Numeric(16, 4), nullable=False, default=Decimal("0"))
    target_value = db.Column(db.Numeric(16, 4), nullable=False, default=Decimal("100"))
    direction = db.Column(db.String(12), nullable=False, default="increase")
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="active")
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_utc, onupdate=now_utc)
    __table_args__ = (
        db.CheckConstraint("direction IN ('increase','decrease')", name="ck_tn_key_result_direction"),
        db.Index("ix_tn_key_result_objective", "objective_id", "status"),
    )

    @property
    def progress(self):
        start, current, target = map(float, (self.start_value or 0, self.current_value or 0, self.target_value or 0))
        denominator = (target - start) if self.direction == "increase" else (start - target)
        numerator = (current - start) if self.direction == "increase" else (start - current)
        if denominator == 0:
            return 100 if current == target else 0
        return max(0, min(100, round((numerator / denominator) * 100)))

    def to_dict(self):
        return {"id": self.id, "objective_id": self.objective_id, "title": self.title,
                "metric_type": self.metric_type, "unit": self.unit, "start_value": str(self.start_value),
                "current_value": str(self.current_value), "target_value": str(self.target_value),
                "direction": self.direction, "owner_id": self.owner_id, "status": self.status,
                "progress": self.progress, "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


class KeyResultUpdate(db.Model):
    __tablename__ = "tn_key_result_updates"
    id = db.Column(db.Integer, primary_key=True)
    key_result_id = db.Column(db.Integer, db.ForeignKey("tn_key_results.id", ondelete="CASCADE"), nullable=False, index=True)
    previous_value = db.Column(db.Numeric(16, 4), nullable=False)
    new_value = db.Column(db.Numeric(16, 4), nullable=False)
    note = db.Column(db.String(1000), nullable=False, default="")
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)

    def to_dict(self):
        return {"id": self.id, "key_result_id": self.key_result_id, "previous_value": str(self.previous_value),
                "new_value": str(self.new_value), "note": self.note, "updated_by": self.updated_by,
                "created_at": self.created_at.isoformat() if self.created_at else None}


class AssetRecord(db.Model):
    __tablename__ = "tn_assets"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    asset_tag = db.Column(db.String(64), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(48), nullable=False, default="equipment")
    serial_number = db.Column(db.String(120), nullable=False, default="")
    purchase_date = db.Column(db.Date, nullable=True)
    purchase_cost = db.Column(db.Numeric(14, 2), nullable=True)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    status = db.Column(db.String(24), nullable=False, default="available", index=True)
    location = db.Column(db.String(180), nullable=False, default="")
    vendor = db.Column(db.String(180), nullable=False, default="")
    warranty_until = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=False, default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_utc, onupdate=now_utc)
    __table_args__ = (
        db.UniqueConstraint("organization_id", "asset_tag", name="uq_tn_asset_org_tag"),
        db.CheckConstraint("purchase_cost IS NULL OR purchase_cost >= 0", name="ck_tn_asset_cost_nonnegative"),
    )

    def to_dict(self):
        return {"id": self.id, "asset_tag": self.asset_tag, "name": self.name, "category": self.category,
                "serial_number": self.serial_number, "purchase_date": self.purchase_date.isoformat() if self.purchase_date else None,
                "purchase_cost": str(self.purchase_cost) if self.purchase_cost is not None else None,
                "currency": self.currency, "status": self.status, "location": self.location, "vendor": self.vendor,
                "warranty_until": self.warranty_until.isoformat() if self.warranty_until else None,
                "notes": self.notes, "created_by": self.created_by,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


class AssetAssignment(db.Model):
    __tablename__ = "tn_asset_assignments"
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("tn_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assigned_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    returned_at = db.Column(db.DateTime, nullable=True)
    condition_out = db.Column(db.String(500), nullable=False, default="")
    condition_in = db.Column(db.String(500), nullable=False, default="")
    notes = db.Column(db.String(1000), nullable=False, default="")
    def to_dict(self):
        return {"id": self.id, "asset_id": self.asset_id, "user_id": self.user_id,
                "assigned_by": self.assigned_by, "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
                "returned_at": self.returned_at.isoformat() if self.returned_at else None,
                "condition_out": self.condition_out, "condition_in": self.condition_in, "notes": self.notes}


class AssetMaintenance(db.Model):
    __tablename__ = "tn_asset_maintenance"
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey("tn_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    priority = db.Column(db.String(16), nullable=False, default="normal")
    status = db.Column(db.String(24), nullable=False, default="open", index=True)
    cost = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0"))
    due_date = db.Column(db.Date, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_utc, onupdate=now_utc)
    __table_args__ = (db.CheckConstraint("cost >= 0", name="ck_tn_maintenance_cost_nonnegative"),)
    def to_dict(self):
        return {"id": self.id, "asset_id": self.asset_id, "requested_by": self.requested_by,
                "assigned_to": self.assigned_to, "title": self.title, "description": self.description,
                "priority": self.priority, "status": self.status, "cost": str(self.cost),
                "due_date": self.due_date.isoformat() if self.due_date else None,
                "completed_at": self.completed_at.isoformat() if self.completed_at else None,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


# ---------------------------------------------------------------------------
# Service desk, knowledge management, and time accounting
# ---------------------------------------------------------------------------

class SupportTicket(db.Model):
    """Organization-scoped support request with a lightweight SLA lifecycle."""
    __tablename__ = "tn_support_tickets"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    ticket_key = db.Column(db.String(32), nullable=False)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    category = db.Column(db.String(32), nullable=False, default="general")
    subject = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    priority = db.Column(db.String(16), nullable=False, default="normal", index=True)
    status = db.Column(db.String(24), nullable=False, default="open", index=True)
    due_at = db.Column(db.DateTime, nullable=True, index=True)
    first_response_at = db.Column(db.DateTime, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    satisfaction_score = db.Column(db.Integer, nullable=True)
    satisfaction_note = db.Column(db.String(1000), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_utc, onupdate=now_utc)
    __table_args__ = (
        db.UniqueConstraint("organization_id", "ticket_key", name="uq_tn_ticket_org_key"),
        db.CheckConstraint("satisfaction_score IS NULL OR satisfaction_score BETWEEN 1 AND 5", name="ck_tn_ticket_score"),
        db.Index("ix_tn_ticket_org_status_priority", "organization_id", "status", "priority"),
    )

    def to_dict(self, include_description=True):
        result = {
            "id": self.id, "ticket_key": self.ticket_key, "organization_id": self.organization_id,
            "requester_id": self.requester_id, "assignee_id": self.assignee_id,
            "category": self.category, "subject": self.subject, "priority": self.priority,
            "status": self.status, "due_at": self.due_at.isoformat() if self.due_at else None,
            "first_response_at": self.first_response_at.isoformat() if self.first_response_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "satisfaction_score": self.satisfaction_score, "satisfaction_note": self.satisfaction_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_description:
            result["description"] = self.description
        return result


class SupportTicketComment(db.Model):
    """Public replies and internal notes attached to support tickets."""
    __tablename__ = "tn_support_ticket_comments"
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tn_support_tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    internal_note = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc, index=True)
    edited_at = db.Column(db.DateTime, nullable=True)
    def to_dict(self):
        return {"id": self.id, "ticket_id": self.ticket_id, "author_id": self.author_id,
                "body": self.body, "internal_note": self.internal_note,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "edited_at": self.edited_at.isoformat() if self.edited_at else None}


class KnowledgeArticle(db.Model):
    """Published internal knowledge articles with revision-friendly metadata."""
    __tablename__ = "tn_knowledge_articles"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    slug = db.Column(db.String(180), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    summary = db.Column(db.String(500), nullable=False, default="")
    body = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(64), nullable=False, default="general", index=True)
    tags_json = db.Column(db.Text, nullable=False, default="[]")
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    published_at = db.Column(db.DateTime, nullable=True)
    view_count = db.Column(db.Integer, nullable=False, default=0)
    helpful_count = db.Column(db.Integer, nullable=False, default=0)
    not_helpful_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_utc, onupdate=now_utc)
    __table_args__ = (
        db.UniqueConstraint("organization_id", "slug", name="uq_tn_knowledge_org_slug"),
        db.CheckConstraint("view_count >= 0 AND helpful_count >= 0 AND not_helpful_count >= 0", name="ck_tn_knowledge_counters"),
    )
    def to_dict(self, include_body=True):
        import json
        result = {"id": self.id, "slug": self.slug, "title": self.title, "summary": self.summary,
                  "category": self.category, "tags": json.loads(self.tags_json or "[]"), "status": self.status,
                  "author_id": self.author_id, "published_at": self.published_at.isoformat() if self.published_at else None,
                  "view_count": self.view_count, "helpful_count": self.helpful_count,
                  "not_helpful_count": self.not_helpful_count,
                  "created_at": self.created_at.isoformat() if self.created_at else None,
                  "updated_at": self.updated_at.isoformat() if self.updated_at else None}
        if include_body:
            result["body"] = self.body
        return result


class TimeEntry(db.Model):
    """Submitted time log; approvals are explicit and audit-friendly."""
    __tablename__ = "tn_time_entries"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("tn_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    work_date = db.Column(db.Date, nullable=False, index=True)
    minutes = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(1200), nullable=False, default="")
    billable = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(20), nullable=False, default="draft", index=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_note = db.Column(db.String(1000), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_utc, onupdate=now_utc)
    __table_args__ = (
        db.CheckConstraint("minutes > 0 AND minutes <= 1440", name="ck_tn_time_entry_minutes"),
        db.Index("ix_tn_time_entry_org_date_status", "organization_id", "work_date", "status"),
    )
    def to_dict(self):
        return {"id": self.id, "user_id": self.user_id, "task_id": self.task_id, "project_id": self.project_id,
                "work_date": self.work_date.isoformat(), "minutes": self.minutes,
                "hours": round(self.minutes / 60, 2), "description": self.description,
                "billable": self.billable, "status": self.status,
                "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
                "reviewed_by": self.reviewed_by, "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
                "review_note": self.review_note, "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


class VendorRecord(db.Model):
    """Supplier directory with status, risk tier, and contract ownership."""
    __tablename__ = "tn_vendors"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    vendor_code = db.Column(db.String(32), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(64), nullable=False, default="general")
    contact_name = db.Column(db.String(120), nullable=False, default="")
    contact_email = db.Column(db.String(180), nullable=False, default="")
    contact_phone = db.Column(db.String(48), nullable=False, default="")
    website = db.Column(db.String(500), nullable=False, default="")
    status = db.Column(db.String(24), nullable=False, default="active", index=True)
    risk_tier = db.Column(db.String(16), nullable=False, default="medium")
    payment_terms = db.Column(db.String(120), nullable=False, default="")
    tax_reference = db.Column(db.String(100), nullable=False, default="")
    notes = db.Column(db.Text, nullable=False, default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_utc, onupdate=now_utc)
    __table_args__ = (
        db.UniqueConstraint("organization_id", "vendor_code", name="uq_tn_vendor_code"),
        db.UniqueConstraint("organization_id", "name", name="uq_tn_vendor_name"),
        db.CheckConstraint("risk_tier IN ('low','medium','high','critical')", name="ck_tn_vendor_risk_tier"),
    )
    def to_dict(self):
        return {"id": self.id, "vendor_code": self.vendor_code, "name": self.name, "category": self.category,
                "contact_name": self.contact_name, "contact_email": self.contact_email, "contact_phone": self.contact_phone,
                "website": self.website, "status": self.status, "risk_tier": self.risk_tier,
                "payment_terms": self.payment_terms, "tax_reference": self.tax_reference, "notes": self.notes,
                "created_by": self.created_by, "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


class VendorContract(db.Model):
    """Contract metadata and renewal tracking for a supplier."""
    __tablename__ = "tn_vendor_contracts"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("tn_vendors.id", ondelete="CASCADE"), nullable=False, index=True)
    contract_number = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False, index=True)
    value = db.Column(db.Numeric(14, 2), nullable=False, default=Decimal("0.00"))
    currency = db.Column(db.String(3), nullable=False, default="INR")
    auto_renew = db.Column(db.Boolean, nullable=False, default=False)
    notice_days = db.Column(db.Integer, nullable=False, default=30)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(db.String(24), nullable=False, default="draft", index=True)
    notes = db.Column(db.Text, nullable=False, default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_utc, onupdate=now_utc)
    __table_args__ = (
        db.UniqueConstraint("organization_id", "contract_number", name="uq_tn_contract_number"),
        db.CheckConstraint("end_date >= start_date", name="ck_tn_contract_dates"),
        db.CheckConstraint("value >= 0 AND notice_days BETWEEN 0 AND 365", name="ck_tn_contract_value_notice"),
    )
    @property
    def renewal_due(self):
        from datetime import date
        return (self.end_date - date.today()).days <= self.notice_days
    def to_dict(self):
        return {"id": self.id, "vendor_id": self.vendor_id, "contract_number": self.contract_number,
                "title": self.title, "start_date": self.start_date.isoformat(), "end_date": self.end_date.isoformat(),
                "value": str(self.value), "currency": self.currency, "auto_renew": self.auto_renew,
                "notice_days": self.notice_days, "owner_id": self.owner_id, "status": self.status,
                "renewal_due": self.renewal_due, "notes": self.notes, "created_by": self.created_by,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


class CompliancePolicy(db.Model):
    """Versioned organizational policy with publish and acknowledgement tracking."""
    __tablename__ = "tn_compliance_policies"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    policy_key = db.Column(db.String(48), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    summary = db.Column(db.String(600), nullable=False, default="")
    body = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(64), nullable=False, default="general", index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(24), nullable=False, default="draft", index=True)
    effective_date = db.Column(db.Date, nullable=True)
    review_date = db.Column(db.Date, nullable=True)
    requires_acknowledgement = db.Column(db.Boolean, nullable=False, default=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    published_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    updated_at = db.Column(db.DateTime, nullable=False, default=now_utc, onupdate=now_utc)
    __table_args__ = (
        db.UniqueConstraint("organization_id", "policy_key", "version", name="uq_tn_policy_version"),
        db.CheckConstraint("version >= 1", name="ck_tn_policy_version_positive"),
        db.CheckConstraint("review_date IS NULL OR effective_date IS NULL OR review_date >= effective_date", name="ck_tn_policy_review_after_effective"),
    )
    def to_dict(self):
        return {"id": self.id, "policy_key": self.policy_key, "title": self.title, "summary": self.summary,
                "body": self.body, "category": self.category, "version": self.version, "status": self.status,
                "effective_date": self.effective_date.isoformat() if self.effective_date else None,
                "review_date": self.review_date.isoformat() if self.review_date else None,
                "requires_acknowledgement": self.requires_acknowledgement, "owner_id": self.owner_id,
                "created_by": self.created_by, "published_at": self.published_at.isoformat() if self.published_at else None,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}


class PolicyAcknowledgement(db.Model):
    """Employee acknowledgement for a specific policy version."""
    __tablename__ = "tn_policy_acknowledgements"
    id = db.Column(db.Integer, primary_key=True)
    policy_id = db.Column(db.Integer, db.ForeignKey("tn_compliance_policies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    policy_version = db.Column(db.Integer, nullable=False)
    acknowledged_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    acknowledgement_text = db.Column(db.String(500), nullable=False, default="I have read and understood this policy.")
    ip_address = db.Column(db.String(64), nullable=False, default="")
    __table_args__ = (db.UniqueConstraint("policy_id", "user_id", "policy_version", name="uq_tn_policy_ack_version"),)
    def to_dict(self):
        return {"id": self.id, "policy_id": self.policy_id, "user_id": self.user_id,
                "policy_version": self.policy_version, "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
                "acknowledgement_text": self.acknowledgement_text}


class ComplianceEvidence(db.Model):
    """Metadata for audit evidence; files remain in the configured file store."""
    __tablename__ = "tn_compliance_evidence"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    policy_id = db.Column(db.Integer, db.ForeignKey("tn_compliance_policies.id", ondelete="SET NULL"), nullable=True, index=True)
    title = db.Column(db.String(180), nullable=False)
    evidence_type = db.Column(db.String(48), nullable=False, default="document")
    reference_uri = db.Column(db.String(1000), nullable=False, default="")
    description = db.Column(db.String(3000), nullable=False, default="")
    collected_on = db.Column(db.Date, nullable=False)
    expires_on = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(24), nullable=False, default="current", index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now_utc)
    __table_args__ = (db.CheckConstraint("expires_on IS NULL OR expires_on >= collected_on", name="ck_tn_evidence_expiry"),)
    def to_dict(self):
        return {"id": self.id, "policy_id": self.policy_id, "title": self.title, "evidence_type": self.evidence_type,
                "reference_uri": self.reference_uri, "description": self.description,
                "collected_on": self.collected_on.isoformat(), "expires_on": self.expires_on.isoformat() if self.expires_on else None,
                "status": self.status, "uploaded_by": self.uploaded_by,
                "created_at": self.created_at.isoformat() if self.created_at else None}
