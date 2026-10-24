"""Support desk and internal knowledge-base APIs.

All records are tenant scoped. Ticket requesters can read their own tickets;
organization administrators can triage all tickets. Staff replies, internal
notes, article publishing, and status transitions are explicitly authorized.
"""
from datetime import datetime, timedelta
import json
import re
from flask import Blueprint, request
from flask_login import current_user, login_required
from sqlalchemy import or_, false
from app import db
from app.models import User, ROLE_ADMIN, ROLE_SUPER_ADMIN
from app.domain_models import SupportTicket, SupportTicketComment, KnowledgeArticle
from app.routes.utils import active_account_required, api_error, api_success, log_audit

service_desk_bp = Blueprint("service_desk", __name__, url_prefix="/api/service-desk")
TICKET_STATUSES = {"open", "in_progress", "waiting_for_requester", "resolved", "closed"}
TICKET_PRIORITIES = {"low", "normal", "high", "urgent"}
TICKET_CATEGORIES = {"general", "access", "hardware", "software", "finance", "hr", "security", "other"}
ARTICLE_STATUSES = {"draft", "published", "archived"}


def _body():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _is_admin():
    return current_user.has_role(ROLE_ADMIN, ROLE_SUPER_ADMIN)


def _org_id():
    return current_user.organization_id


def _ticket_query():
    query = SupportTicket.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=_org_id())
    if not _is_admin():
        query = query.filter_by(requester_id=current_user.id)
    status = request.args.get("status")
    if status in TICKET_STATUSES:
        query = query.filter_by(status=status)
    priority = request.args.get("priority")
    if priority in TICKET_PRIORITIES:
        query = query.filter_by(priority=priority)
    category = request.args.get("category")
    if category in TICKET_CATEGORIES:
        query = query.filter_by(category=category)
    assignee = request.args.get("assignee_id")
    if assignee:
        try:
            query = query.filter_by(assignee_id=int(assignee))
        except ValueError:
            return query.filter(false())
    term = request.args.get("q", "").strip()[:100]
    if term:
        pattern = f"%{term}%"
        query = query.filter(or_(SupportTicket.ticket_key.ilike(pattern), SupportTicket.subject.ilike(pattern),
                                 SupportTicket.description.ilike(pattern)))
    return query


def _ticket(ticket_id):
    query = SupportTicket.query.filter_by(id=ticket_id)
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=_org_id())
    row = query.first()
    if row and not _is_admin() and row.requester_id != current_user.id:
        return None
    return row


def _next_key():
    prefix = f"SD-{datetime.utcnow():%y%m}-"
    existing = SupportTicket.query.filter_by(organization_id=_org_id()).filter(SupportTicket.ticket_key.like(prefix + "%")).all()
    sequence = []
    for item in existing:
        try:
            sequence.append(int(item.ticket_key.rsplit("-", 1)[1]))
        except (ValueError, IndexError):
            continue
    return prefix + f"{max(sequence, default=0) + 1:05d}"


def _valid_person(user_id):
    if user_id in (None, ""):
        return None
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        raise ValueError("assignee_id must be an integer.")
    person = db.session.get(User, uid)
    if not person or (not current_user.has_role(ROLE_SUPER_ADMIN) and person.organization_id != _org_id()):
        raise LookupError("Assignee not found in this organization.")
    return uid


@service_desk_bp.get("/tickets")
@login_required
@active_account_required
def list_tickets():
    try:
        page = max(1, min(int(request.args.get("page", 1)), 100000))
        page_size = max(1, min(int(request.args.get("page_size", 25)), 100))
    except ValueError:
        return api_error("page and page_size must be integers.", 400)
    query = _ticket_query()
    total = query.count()
    rows = query.order_by(SupportTicket.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return api_success({"items": [row.to_dict(include_description=False) for row in rows], "page": page,
                        "page_size": page_size, "total": total, "pages": (total + page_size - 1) // page_size})


@service_desk_bp.post("/tickets")
@login_required
@active_account_required
def create_ticket():
    data = _body()
    subject = str(data.get("subject", "")).strip()
    description = str(data.get("description", "")).strip()
    priority = str(data.get("priority", "normal"))
    category = str(data.get("category", "general"))
    if not _org_id():
        return api_error("An organization must be assigned before creating a support ticket.", 409)
    if not subject or len(subject) > 180 or not description or len(description) > 20000:
        return api_error("subject and description are required; subject must be at most 180 characters and description at most 20,000.", 400)
    if priority not in TICKET_PRIORITIES or category not in TICKET_CATEGORIES:
        return api_error("Unsupported ticket priority or category.", 400)
    row = SupportTicket(organization_id=_org_id(), ticket_key=_next_key(), requester_id=current_user.id,
                        category=category, subject=subject, description=description, priority=priority,
                        due_at=datetime.utcnow() + timedelta(hours={"urgent": 4, "high": 12, "normal": 48, "low": 120}[priority]))
    db.session.add(row)
    db.session.commit()
    log_audit("support_ticket.created", "support_ticket", row.id, {"ticket_key": row.ticket_key, "priority": priority})
    return api_success(row.to_dict(), "Support ticket created.", 201)


@service_desk_bp.get("/tickets/<int:ticket_id>")
@login_required
@active_account_required
def get_ticket(ticket_id):
    row = _ticket(ticket_id)
    if not row:
        return api_error("Support ticket not found.", 404)
    comments = SupportTicketComment.query.filter_by(ticket_id=row.id).order_by(SupportTicketComment.created_at.asc()).all()
    if not _is_admin():
        comments = [comment for comment in comments if not comment.internal_note]
    return api_success({**row.to_dict(), "comments": [comment.to_dict() for comment in comments]})


@service_desk_bp.patch("/tickets/<int:ticket_id>")
@login_required
@active_account_required
def update_ticket(ticket_id):
    row = _ticket(ticket_id)
    if not row:
        return api_error("Support ticket not found.", 404)
    data = _body()
    if not _is_admin():
        allowed = {"satisfaction_score", "satisfaction_note"}
        if set(data) - allowed:
            return api_error("Only organization administrators can triage tickets.", 403)
        if row.status not in {"resolved", "closed"}:
            return api_error("Feedback can only be submitted after resolution.", 409)
        try:
            score = int(data.get("satisfaction_score"))
            if score < 1 or score > 5:
                raise ValueError
        except (TypeError, ValueError):
            return api_error("satisfaction_score must be an integer from 1 to 5.", 400)
        row.satisfaction_score = score
        row.satisfaction_note = str(data.get("satisfaction_note", ""))[:1000]
        db.session.commit()
        log_audit("support_ticket.feedback", "support_ticket", row.id, {"score": score})
        return api_success(row.to_dict(), "Feedback recorded.")

    if "status" in data:
        status = str(data["status"])
        if status not in TICKET_STATUSES:
            return api_error("Unsupported ticket status.", 400)
        if row.status == "closed" and status != "closed":
            return api_error("Closed tickets must be reopened before being triaged.", 409)
        row.status = status
        now = datetime.utcnow()
        if status in {"resolved", "closed"}:
            row.resolved_at = row.resolved_at or now
        if status == "closed":
            row.closed_at = now
        elif status in {"open", "in_progress", "waiting_for_requester"}:
            row.closed_at = None
            row.resolved_at = None
    if "priority" in data:
        if data["priority"] not in TICKET_PRIORITIES:
            return api_error("Unsupported ticket priority.", 400)
        row.priority = data["priority"]
        row.due_at = datetime.utcnow() + timedelta(hours={"urgent": 4, "high": 12, "normal": 48, "low": 120}[row.priority])
    if "category" in data:
        if data["category"] not in TICKET_CATEGORIES:
            return api_error("Unsupported ticket category.", 400)
        row.category = data["category"]
    if "assignee_id" in data:
        try:
            row.assignee_id = _valid_person(data["assignee_id"])
        except (ValueError, LookupError) as exc:
            return api_error(str(exc), 400 if isinstance(exc, ValueError) else 404)
    if row.first_response_at is None and ("status" in data or "assignee_id" in data):
        row.first_response_at = datetime.utcnow()
    db.session.commit()
    log_audit("support_ticket.updated", "support_ticket", row.id, {"fields": sorted(data)})
    return api_success(row.to_dict(), "Support ticket updated.")


@service_desk_bp.post("/tickets/<int:ticket_id>/comments")
@login_required
@active_account_required
def add_ticket_comment(ticket_id):
    row = _ticket(ticket_id)
    if not row:
        return api_error("Support ticket not found.", 404)
    data = _body()
    body = str(data.get("body", "")).strip()
    internal = bool(data.get("internal_note", False))
    if not body or len(body) > 12000:
        return api_error("Comment body is required and must be at most 12,000 characters.", 400)
    if internal and not _is_admin():
        return api_error("Only organization administrators can create internal notes.", 403)
    comment = SupportTicketComment(ticket_id=row.id, author_id=current_user.id, body=body, internal_note=internal)
    db.session.add(comment)
    if row.first_response_at is None and current_user.id != row.requester_id:
        row.first_response_at = datetime.utcnow()
    if row.status == "open" and current_user.id != row.requester_id:
        row.status = "in_progress"
    db.session.commit()
    log_audit("support_ticket.comment_added", "support_ticket", row.id, {"internal_note": internal})
    return api_success(comment.to_dict(), "Reply added.", 201)


@service_desk_bp.get("/metrics")
@login_required
@active_account_required
def ticket_metrics():
    query = SupportTicket.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=_org_id())
    if not _is_admin():
        query = query.filter_by(requester_id=current_user.id)
    rows = query.all()
    now = datetime.utcnow()
    active = [row for row in rows if row.status not in {"resolved", "closed"}]
    overdue = [row for row in active if row.due_at and row.due_at < now]
    response_minutes = [(row.first_response_at - row.created_at).total_seconds() / 60 for row in rows if row.first_response_at]
    resolution_minutes = [(row.resolved_at - row.created_at).total_seconds() / 60 for row in rows if row.resolved_at]
    ratings = [row.satisfaction_score for row in rows if row.satisfaction_score is not None]
    return api_success({"total": len(rows), "open": sum(row.status == "open" for row in rows),
        "in_progress": sum(row.status == "in_progress" for row in rows), "waiting": sum(row.status == "waiting_for_requester" for row in rows),
        "resolved": sum(row.status == "resolved" for row in rows), "closed": sum(row.status == "closed" for row in rows),
        "overdue": len(overdue), "average_first_response_minutes": round(sum(response_minutes) / len(response_minutes), 1) if response_minutes else None,
        "average_resolution_minutes": round(sum(resolution_minutes) / len(resolution_minutes), 1) if resolution_minutes else None,
        "average_satisfaction": round(sum(ratings) / len(ratings), 2) if ratings else None})


def _slug(title):
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:150]
    return slug or "article"


def _article_query(include_drafts=False):
    query = KnowledgeArticle.query
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=_org_id())
    if not include_drafts:
        query = query.filter_by(status="published")
    category = request.args.get("category", "").strip()[:64]
    if category:
        query = query.filter_by(category=category)
    term = request.args.get("q", "").strip()[:100]
    if term:
        pattern = f"%{term}%"
        query = query.filter(or_(KnowledgeArticle.title.ilike(pattern), KnowledgeArticle.summary.ilike(pattern), KnowledgeArticle.body.ilike(pattern)))
    return query


@service_desk_bp.get("/knowledge")
@login_required
@active_account_required
def list_articles():
    include_drafts = _is_admin() and request.args.get("include_drafts") == "1"
    query = _article_query(include_drafts=include_drafts)
    rows = query.order_by(KnowledgeArticle.updated_at.desc()).limit(100).all()
    return api_success({"items": [row.to_dict(include_body=False) for row in rows], "total": len(rows)})


@service_desk_bp.post("/knowledge")
@login_required
@active_account_required
def create_article():
    if not _is_admin():
        return api_error("Administrator permission required to author knowledge articles.", 403)
    if not _org_id():
        return api_error("An organization must be assigned before creating an article.", 409)
    data = _body()
    title, body = str(data.get("title", "")).strip(), str(data.get("body", "")).strip()
    if not title or len(title) > 180 or not body or len(body) > 40000:
        return api_error("title and body are required; title must be at most 180 characters and body at most 40,000.", 400)
    tags = data.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 30 or any(not isinstance(tag, str) or len(tag) > 40 for tag in tags):
        return api_error("tags must be a list of at most 30 strings, each at most 40 characters.", 400)
    status = str(data.get("status", "draft"))
    if status not in ARTICLE_STATUSES:
        return api_error("Unsupported article status.", 400)
    base_slug = _slug(str(data.get("slug") or title))
    slug, suffix = base_slug, 2
    while KnowledgeArticle.query.filter_by(organization_id=_org_id(), slug=slug).first():
        slug = f"{base_slug[:165]}-{suffix}"
        suffix += 1
    row = KnowledgeArticle(organization_id=_org_id(), slug=slug, title=title,
        summary=str(data.get("summary", ""))[:500], body=body,
        category=str(data.get("category", "general")).strip()[:64] or "general",
        tags_json=json.dumps(sorted(set(tag.strip() for tag in tags if tag.strip())), ensure_ascii=False),
        status=status, author_id=current_user.id,
        published_at=datetime.utcnow() if status == "published" else None)
    db.session.add(row)
    db.session.commit()
    log_audit("knowledge_article.created", "knowledge_article", row.id, {"status": status})
    return api_success(row.to_dict(), "Knowledge article created.", 201)


@service_desk_bp.get("/knowledge/<int:article_id>")
@login_required
@active_account_required
def get_article(article_id):
    query = KnowledgeArticle.query.filter_by(id=article_id)
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=_org_id())
    row = query.first()
    if not row or (row.status != "published" and not _is_admin()):
        return api_error("Knowledge article not found.", 404)
    row.view_count += 1
    db.session.commit()
    return api_success(row.to_dict())


@service_desk_bp.patch("/knowledge/<int:article_id>")
@login_required
@active_account_required
def update_article(article_id):
    if not _is_admin():
        return api_error("Administrator permission required to edit knowledge articles.", 403)
    query = KnowledgeArticle.query.filter_by(id=article_id)
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=_org_id())
    row = query.first()
    if not row:
        return api_error("Knowledge article not found.", 404)
    data = _body()
    if "title" in data:
        title = str(data["title"]).strip()
        if not title or len(title) > 180:
            return api_error("title must contain 1–180 characters.", 400)
        row.title = title
    if "body" in data:
        body = str(data["body"]).strip()
        if not body or len(body) > 40000:
            return api_error("body must contain 1–40,000 characters.", 400)
        row.body = body
    for field, maximum in (("summary", 500), ("category", 64)):
        if field in data:
            setattr(row, field, str(data[field]).strip()[:maximum])
    if "tags" in data:
        tags = data["tags"]
        if not isinstance(tags, list) or len(tags) > 30 or any(not isinstance(tag, str) or len(tag) > 40 for tag in tags):
            return api_error("tags must be a list of at most 30 short strings.", 400)
        row.tags_json = json.dumps(sorted(set(tag.strip() for tag in tags if tag.strip())), ensure_ascii=False)
    if "status" in data:
        status = str(data["status"])
        if status not in ARTICLE_STATUSES:
            return api_error("Unsupported article status.", 400)
        row.status = status
        row.published_at = row.published_at or datetime.utcnow() if status == "published" else None
    db.session.commit()
    log_audit("knowledge_article.updated", "knowledge_article", row.id, {"fields": sorted(data)})
    return api_success(row.to_dict(), "Knowledge article updated.")


@service_desk_bp.post("/knowledge/<int:article_id>/feedback")
@login_required
@active_account_required
def article_feedback(article_id):
    query = KnowledgeArticle.query.filter_by(id=article_id, status="published")
    if not current_user.has_role(ROLE_SUPER_ADMIN):
        query = query.filter_by(organization_id=_org_id())
    row = query.first()
    if not row:
        return api_error("Knowledge article not found.", 404)
    helpful = _body().get("helpful")
    if not isinstance(helpful, bool):
        return api_error("helpful must be true or false.", 400)
    if helpful:
        row.helpful_count += 1
    else:
        row.not_helpful_count += 1
    db.session.commit()
    return api_success({"id": row.id, "helpful_count": row.helpful_count, "not_helpful_count": row.not_helpful_count}, "Feedback recorded.")
