"""Shared persistence for TaskNest enterprise operational workspaces.

The records are deliberately typed by module while retaining a structured payload for
module-specific fields. Identity, tenant ownership, workflow state, timestamps, and
audit events remain relational and indexed. Domain services validate payload schemas
before any record is written.
"""
from datetime import datetime, timezone
from app import db


def operations_now():
    """Return a naive UTC timestamp compatible with the existing SQLite schema."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class OperationalRecord(db.Model):
    """A tenant-scoped record managed by one of the operational workspaces."""
    __tablename__ = "tn_operational_records"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    module_key = db.Column(db.String(40), nullable=False, index=True)
    record_key = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(240), nullable=False)
    summary = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(40), nullable=False, default="draft", index=True)
    priority = db.Column(db.String(20), nullable=False, default="medium", index=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    due_date = db.Column(db.Date, nullable=True, index=True)
    payload_json = db.Column(db.JSON, nullable=False, default=dict)
    version = db.Column(db.Integer, nullable=False, default=1)
    archived = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=operations_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=operations_now, onupdate=operations_now)

    __table_args__ = (
        db.UniqueConstraint("organization_id", "module_key", "record_key",
                            name="uq_tn_ops_org_module_key"),
        db.Index("ix_tn_ops_org_module_status", "organization_id", "module_key", "status"),
        db.Index("ix_tn_ops_org_module_updated", "organization_id", "module_key", "updated_at"),
    )

    def to_dict(self, include_payload=True):
        result = {
            "id": self.id, "organization_id": self.organization_id,
            "module": self.module_key, "key": self.record_key, "title": self.title,
            "summary": self.summary, "status": self.status, "priority": self.priority,
            "owner_id": self.owner_id, "created_by": self.created_by,
            "updated_by": self.updated_by,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "version": self.version, "archived": bool(self.archived),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_payload:
            result["fields"] = self.payload_json or {}
        return result


class OperationalEvent(db.Model):
    """Append-only activity/comment history attached to an operational record."""
    __tablename__ = "tn_operational_events"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    record_id = db.Column(db.Integer, db.ForeignKey("tn_operational_records.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    event_type = db.Column(db.String(40), nullable=False, index=True)
    from_status = db.Column(db.String(40), nullable=True)
    to_status = db.Column(db.String(40), nullable=True)
    message = db.Column(db.Text, nullable=False, default="")
    details_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=operations_now, index=True)

    record = db.relationship("OperationalRecord", backref=db.backref(
        "events", lazy="dynamic", cascade="all, delete-orphan", order_by="OperationalEvent.created_at"
    ))

    def to_dict(self):
        return {
            "id": self.id, "record_id": self.record_id, "actor_id": self.actor_id,
            "event_type": self.event_type, "from_status": self.from_status,
            "to_status": self.to_status, "message": self.message,
            "details": self.details_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class OperationalSequence(db.Model):
    """Organization-scoped monotonic key allocator for human-readable references."""
    __tablename__ = "tn_operational_sequences"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False)
    module_key = db.Column(db.String(40), nullable=False)
    last_value = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("organization_id", "module_key", name="uq_tn_ops_sequence"),
    )



class OperationalChecklistItem(db.Model):
    """Checklist item with ownership and completion evidence."""
    __tablename__ = "tn_operational_checklist_items"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    record_id = db.Column(db.Integer, db.ForeignKey("tn_operational_records.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    title = db.Column(db.String(240), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    required = db.Column(db.Boolean, nullable=False, default=True)
    completed = db.Column(db.Boolean, nullable=False, default=False, index=True)
    completed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    evidence_reference = db.Column(db.String(1000), nullable=False, default="")
    position = db.Column(db.Integer, nullable=False, default=0)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=operations_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=operations_now, onupdate=operations_now)

    record = db.relationship("OperationalRecord", backref=db.backref(
        "checklist_items", lazy="dynamic", cascade="all, delete-orphan"
    ))

    def to_dict(self):
        return {
            "id": self.id, "record_id": self.record_id, "title": self.title,
            "description": self.description, "required": bool(self.required),
            "completed": bool(self.completed), "completed_by": self.completed_by,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "evidence_reference": self.evidence_reference, "position": self.position,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class OperationalAttachment(db.Model):
    """Metadata for an evidence document stored by a configured storage adapter."""
    __tablename__ = "tn_operational_attachments"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    record_id = db.Column(db.Integer, db.ForeignKey("tn_operational_records.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    display_name = db.Column(db.String(240), nullable=False)
    storage_key = db.Column(db.String(500), nullable=False)
    content_type = db.Column(db.String(120), nullable=False, default="application/octet-stream")
    byte_size = db.Column(db.Integer, nullable=False, default=0)
    sha256_digest = db.Column(db.String(64), nullable=False, default="")
    evidence_type = db.Column(db.String(40), nullable=False, default="supporting")
    created_at = db.Column(db.DateTime, nullable=False, default=operations_now)

    record = db.relationship("OperationalRecord", backref=db.backref(
        "attachments", lazy="dynamic", cascade="all, delete-orphan"
    ))

    __table_args__ = (
        db.CheckConstraint("byte_size >= 0", name="ck_tn_ops_attachment_size_nonnegative"),
        db.Index("ix_tn_ops_attachment_org_record", "organization_id", "record_id"),
    )

    def to_dict(self):
        return {
            "id": self.id, "record_id": self.record_id, "uploaded_by": self.uploaded_by,
            "display_name": self.display_name, "content_type": self.content_type,
            "byte_size": self.byte_size, "sha256_digest": self.sha256_digest,
            "evidence_type": self.evidence_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class OperationalApproval(db.Model):
    """Explicit approval decision attached to an operational record."""
    __tablename__ = "tn_operational_approvals"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    record_id = db.Column(db.Integer, db.ForeignKey("tn_operational_records.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    stage_key = db.Column(db.String(60), nullable=False)
    approver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    decision = db.Column(db.String(20), nullable=False, default="pending", index=True)
    decision_note = db.Column(db.Text, nullable=False, default="")
    due_at = db.Column(db.DateTime, nullable=True)
    decided_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=operations_now)

    record = db.relationship("OperationalRecord", backref=db.backref(
        "approvals", lazy="dynamic", cascade="all, delete-orphan"
    ))

    __table_args__ = (
        db.CheckConstraint("decision IN ('pending','approved','rejected','skipped')",
                           name="ck_tn_ops_approval_decision"),
        db.UniqueConstraint("record_id", "stage_key", "approver_id",
                            name="uq_tn_ops_approval_stage_approver"),
    )

    def to_dict(self):
        return {
            "id": self.id, "record_id": self.record_id, "stage_key": self.stage_key,
            "approver_id": self.approver_id, "decision": self.decision,
            "decision_note": self.decision_note,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class OperationalSLAEvent(db.Model):
    """Immutable record of SLA clock starts, pauses, breaches, and acknowledgements."""
    __tablename__ = "tn_operational_sla_events"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    record_id = db.Column(db.Integer, db.ForeignKey("tn_operational_records.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    event_type = db.Column(db.String(30), nullable=False)
    target_minutes = db.Column(db.Integer, nullable=False, default=0)
    elapsed_minutes = db.Column(db.Integer, nullable=False, default=0)
    reason = db.Column(db.String(1000), nullable=False, default="")
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    occurred_at = db.Column(db.DateTime, nullable=False, default=operations_now, index=True)

    record = db.relationship("OperationalRecord", backref=db.backref(
        "sla_events", lazy="dynamic", cascade="all, delete-orphan"
    ))

    def to_dict(self):
        return {
            "id": self.id, "record_id": self.record_id, "event_type": self.event_type,
            "target_minutes": self.target_minutes, "elapsed_minutes": self.elapsed_minutes,
            "reason": self.reason, "actor_id": self.actor_id,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
        }



class OperationalPolicy(db.Model):
    """Tenant-specific defaults for operational response and review policy."""
    __tablename__ = "tn_operational_policies"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    module_key = db.Column(db.String(40), nullable=False)
    acknowledgement_minutes = db.Column(db.Integer, nullable=False, default=240)
    resolution_minutes = db.Column(db.Integer, nullable=False, default=4320)
    escalation_minutes = db.Column(db.Integer, nullable=False, default=1440)
    high_risk_requires_approval = db.Column(db.Boolean, nullable=False, default=True)
    evidence_required_for_close = db.Column(db.Boolean, nullable=False, default=False)
    default_owner_role = db.Column(db.String(30), nullable=False, default="team_lead")
    escalation_role = db.Column(db.String(30), nullable=False, default="admin")
    policy_notes = db.Column(db.Text, nullable=False, default="")
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=operations_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=operations_now, onupdate=operations_now)

    __table_args__ = (
        db.UniqueConstraint("organization_id", "module_key", name="uq_tn_ops_policy_org_module"),
        db.CheckConstraint("acknowledgement_minutes >= 0", name="ck_tn_ops_policy_ack_nonnegative"),
        db.CheckConstraint("resolution_minutes >= 0", name="ck_tn_ops_policy_resolution_nonnegative"),
        db.CheckConstraint("escalation_minutes >= 0", name="ck_tn_ops_policy_escalation_nonnegative"),
    )

    def to_dict(self):
        return {
            "id": self.id, "organization_id": self.organization_id, "module_key": self.module_key,
            "acknowledgement_minutes": self.acknowledgement_minutes,
            "resolution_minutes": self.resolution_minutes, "escalation_minutes": self.escalation_minutes,
            "high_risk_requires_approval": bool(self.high_risk_requires_approval),
            "evidence_required_for_close": bool(self.evidence_required_for_close),
            "default_owner_role": self.default_owner_role, "escalation_role": self.escalation_role,
            "policy_notes": self.policy_notes, "active": bool(self.active),
            "created_by": self.created_by, "updated_by": self.updated_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class OperationalLink(db.Model):
    """Typed relationships between records in different operational workspaces."""
    __tablename__ = "tn_operational_links"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, nullable=False, index=True)
    source_record_id = db.Column(db.Integer, db.ForeignKey("tn_operational_records.id", ondelete="CASCADE"),
                                 nullable=False, index=True)
    target_record_id = db.Column(db.Integer, db.ForeignKey("tn_operational_records.id", ondelete="CASCADE"),
                                 nullable=False, index=True)
    link_type = db.Column(db.String(40), nullable=False, default="relates_to")
    note = db.Column(db.String(2000), nullable=False, default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=operations_now)

    source = db.relationship("OperationalRecord", foreign_keys=[source_record_id],
                              backref=db.backref("outgoing_links", lazy="dynamic", cascade="all, delete-orphan"))
    target = db.relationship("OperationalRecord", foreign_keys=[target_record_id],
                              backref=db.backref("incoming_links", lazy="dynamic", cascade="all, delete-orphan"))

    __table_args__ = (
        db.CheckConstraint("source_record_id <> target_record_id", name="ck_tn_ops_link_not_self"),
        db.UniqueConstraint("source_record_id", "target_record_id", "link_type", name="uq_tn_ops_link"),
    )

    def to_dict(self):
        return {
            "id": self.id, "source_record_id": self.source_record_id,
            "target_record_id": self.target_record_id, "link_type": self.link_type,
            "note": self.note, "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "source_key": self.source.record_key if self.source else None,
            "target_key": self.target.record_key if self.target else None,
            "source_module": self.source.module_key if self.source else None,
            "target_module": self.target.module_key if self.target else None,
        }
