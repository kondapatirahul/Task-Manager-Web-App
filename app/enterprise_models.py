"""Additional normalized models for TaskNest's enterprise workspace features.

These models intentionally live in a separate module to keep the legacy domain
models stable while new capabilities are introduced incrementally. JSON-shaped
configuration is stored as text for SQLite compatibility and validated at the
service boundary.
"""
from datetime import datetime, timezone
from app import db

def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class Project(db.Model):
    __tablename__ = "tn_projects"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(140), nullable=False)
    key = db.Column(db.String(16), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(24), nullable=False, default="active")
    start_date = db.Column(db.Date, nullable=True)
    target_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)
    __table_args__ = (
        db.UniqueConstraint("organization_id", "key", name="uq_tn_project_org_key"),
        db.Index("ix_tn_project_org_status", "organization_id", "status"),
    )
    def to_dict(self):
        return {"id": self.id, "organization_id": self.organization_id,
                "owner_id": self.owner_id, "name": self.name, "key": self.key,
                "description": self.description, "status": self.status,
                "start_date": self.start_date.isoformat() if self.start_date else None,
                "target_date": self.target_date.isoformat() if self.target_date else None,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}

class ProjectMember(db.Model):
    __tablename__ = "tn_project_members"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("tn_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = db.Column(db.String(24), nullable=False, default="contributor")
    added_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    __table_args__ = (db.UniqueConstraint("project_id", "user_id", name="uq_tn_project_member"),)
    def to_dict(self):
        return {"id": self.id, "project_id": self.project_id, "user_id": self.user_id,
                "role": self.role, "added_by": self.added_by,
                "created_at": self.created_at.isoformat() if self.created_at else None}

class ProjectTask(db.Model):
    __tablename__ = "tn_project_tasks"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("tn_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    linked_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    __table_args__ = (db.UniqueConstraint("project_id", "task_id", name="uq_tn_project_task"),)

class TaskDependency(db.Model):
    __tablename__ = "tn_task_dependencies"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    depends_on_task_id = db.Column(db.Integer, db.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    dependency_type = db.Column(db.String(24), nullable=False, default="blocks")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    __table_args__ = (
        db.UniqueConstraint("task_id", "depends_on_task_id", name="uq_tn_task_dependency"),
        db.CheckConstraint("task_id != depends_on_task_id", name="ck_tn_no_self_dependency"),
    )
    def to_dict(self):
        return {"id": self.id, "task_id": self.task_id,
                "depends_on_task_id": self.depends_on_task_id,
                "dependency_type": self.dependency_type,
                "created_by": self.created_by,
                "created_at": self.created_at.isoformat() if self.created_at else None}

class SavedView(db.Model):
    __tablename__ = "tn_saved_views"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(32), nullable=False, default="task")
    filters_json = db.Column(db.Text, nullable=False, default="{}")
    columns_json = db.Column(db.Text, nullable=False, default="[]")
    is_shared = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)
    def to_dict(self):
        import json
        return {"id": self.id, "name": self.name, "entity_type": self.entity_type,
                "filters": json.loads(self.filters_json or "{}"),
                "columns": json.loads(self.columns_json or "[]"),
                "is_shared": bool(self.is_shared), "owner_id": self.owner_id,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}

class CustomFieldDefinition(db.Model):
    __tablename__ = "tn_custom_field_definitions"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    entity_type = db.Column(db.String(32), nullable=False, default="task")
    field_key = db.Column(db.String(48), nullable=False)
    label = db.Column(db.String(100), nullable=False)
    field_type = db.Column(db.String(24), nullable=False)
    required = db.Column(db.Boolean, nullable=False, default=False)
    options_json = db.Column(db.Text, nullable=False, default="[]")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    __table_args__ = (db.UniqueConstraint("organization_id", "entity_type", "field_key", name="uq_tn_custom_field_key"),)
    def to_dict(self):
        import json
        return {"id": self.id, "entity_type": self.entity_type, "field_key": self.field_key,
                "label": self.label, "field_type": self.field_type, "required": self.required,
                "options": json.loads(self.options_json or "[]"), "active": self.active,
                "created_at": self.created_at.isoformat() if self.created_at else None}

class CustomFieldValue(db.Model):
    __tablename__ = "tn_custom_field_values"
    id = db.Column(db.Integer, primary_key=True)
    definition_id = db.Column(db.Integer, db.ForeignKey("tn_custom_field_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    value_json = db.Column(db.Text, nullable=False, default="null")
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)
    __table_args__ = (db.UniqueConstraint("definition_id", "entity_id", name="uq_tn_custom_field_value"),)

class WorkflowRule(db.Model):
    __tablename__ = "tn_workflow_rules"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    trigger_event = db.Column(db.String(64), nullable=False, index=True)
    conditions_json = db.Column(db.Text, nullable=False, default="[]")
    actions_json = db.Column(db.Text, nullable=False, default="[]")
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)
    def to_dict(self):
        import json
        return {"id": self.id, "name": self.name, "description": self.description,
                "trigger_event": self.trigger_event,
                "conditions": json.loads(self.conditions_json or "[]"),
                "actions": json.loads(self.actions_json or "[]"), "enabled": self.enabled,
                "creator_id": self.creator_id,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}

class WorkflowRun(db.Model):
    __tablename__ = "tn_workflow_runs"
    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("tn_workflow_rules.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(32), nullable=False)
    entity_id = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(24), nullable=False, default="queued")
    detail_json = db.Column(db.Text, nullable=False, default="{}")
    started_at = db.Column(db.DateTime, nullable=False, default=_now)
    finished_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (db.UniqueConstraint("rule_id", "event_id", name="uq_tn_workflow_event_once"),)
    def to_dict(self):
        import json
        return {"id": self.id, "rule_id": self.rule_id, "event_id": self.event_id,
                "entity_type": self.entity_type, "entity_id": self.entity_id,
                "status": self.status, "detail": json.loads(self.detail_json or "{}"),
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "finished_at": self.finished_at.isoformat() if self.finished_at else None}

class WebhookEndpoint(db.Model):
    __tablename__ = "tn_webhook_endpoints"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(2048), nullable=False)
    secret_hash = db.Column(db.String(128), nullable=False)
    events_json = db.Column(db.Text, nullable=False, default="[]")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    def to_dict(self):
        import json
        return {"id": self.id, "name": self.name, "url": self.url,
                "events": json.loads(self.events_json or "[]"), "active": self.active,
                "created_at": self.created_at.isoformat() if self.created_at else None}

class WebhookDelivery(db.Model):
    __tablename__ = "tn_webhook_deliveries"
    id = db.Column(db.Integer, primary_key=True)
    endpoint_id = db.Column(db.Integer, db.ForeignKey("tn_webhook_endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id = db.Column(db.String(80), nullable=False, index=True)
    event_type = db.Column(db.String(64), nullable=False)
    payload_json = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(24), nullable=False, default="pending", index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    next_attempt_at = db.Column(db.DateTime, nullable=True, index=True)
    last_status_code = db.Column(db.Integer, nullable=True)
    last_error = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    __table_args__ = (db.UniqueConstraint("endpoint_id", "event_id", name="uq_tn_webhook_delivery_once"),)
    def to_dict(self):
        import json
        return {"id": self.id, "endpoint_id": self.endpoint_id, "event_id": self.event_id,
                "event_type": self.event_type, "payload": json.loads(self.payload_json),
                "status": self.status, "attempts": self.attempts,
                "next_attempt_at": self.next_attempt_at.isoformat() if self.next_attempt_at else None,
                "last_status_code": self.last_status_code, "last_error": self.last_error,
                "created_at": self.created_at.isoformat() if self.created_at else None}

class ProjectMilestone(db.Model):
    __tablename__ = "tn_project_milestones"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("tn_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(24), nullable=False, default="open")
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)
    def to_dict(self):
        return {"id": self.id, "project_id": self.project_id, "title": self.title,
                "description": self.description,
                "due_date": self.due_date.isoformat() if self.due_date else None,
                "status": self.status, "owner_id": self.owner_id,
                "created_by": self.created_by,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}

class TimeEntry(db.Model):
    __tablename__ = "tn_timer_entries"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=True, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("tn_projects.id"), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    started_at = db.Column(db.DateTime, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    duration_minutes = db.Column(db.Integer, nullable=True)
    note = db.Column(db.String(1000), nullable=False, default="")
    billable = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(20), nullable=False, default="draft")
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)
    __table_args__ = (
        db.CheckConstraint("duration_minutes IS NULL OR duration_minutes >= 0", name="ck_tn_time_nonnegative"),
        db.Index("ix_tn_time_org_user_start", "organization_id", "user_id", "started_at"),
    )
    def to_dict(self):
        return {"id": self.id, "organization_id": self.organization_id,
                "task_id": self.task_id, "project_id": self.project_id, "user_id": self.user_id,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "ended_at": self.ended_at.isoformat() if self.ended_at else None,
                "duration_minutes": self.duration_minutes, "note": self.note,
                "billable": bool(self.billable), "status": self.status,
                "approved_by": self.approved_by,
                "approved_at": self.approved_at.isoformat() if self.approved_at else None,
                "created_at": self.created_at.isoformat() if self.created_at else None}

class TaskTemplate(db.Model):
    __tablename__ = "tn_task_templates"
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    default_priority = db.Column(db.String(20), nullable=False, default="medium")
    default_category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    checklist_json = db.Column(db.Text, nullable=False, default="[]")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)
    def to_dict(self):
        import json
        return {"id": self.id, "name": self.name, "description": self.description,
                "default_priority": self.default_priority, "default_category_id": self.default_category_id,
                "checklist": json.loads(self.checklist_json or "[]"), "active": self.active,
                "owner_id": self.owner_id,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None}
