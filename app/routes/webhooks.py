"""Webhook endpoint registry and delivery queue inspection.

This module queues delivery records but deliberately does not perform outbound
HTTP requests inside a web request. A worker can claim pending records and send
them with a timeout, redirect policy, DNS/IP validation, and retry backoff.
"""
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request
from flask_login import current_user, login_required
from app import db
from app.enterprise_models import WebhookEndpoint, WebhookDelivery
from app.routes.utils import active_account_required, api_error, api_success, log_audit
from app.services.enterprise import safe_webhook_events, valid_public_https_url

webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/api/enterprise/webhooks")

def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}

def _scope():
    return WebhookEndpoint.query.filter_by(organization_id=current_user.organization_id)

@webhooks_bp.get("")
@login_required
@active_account_required
def list_endpoints():
    rows = _scope().order_by(WebhookEndpoint.created_at.desc()).limit(200).all()
    return api_success([row.to_dict() for row in rows])

@webhooks_bp.post("")
@login_required
@active_account_required
def create_endpoint():
    if not current_user.has_role("admin", "super_admin"):
        return api_error("Administrator permission required.", 403)
    data = _body()
    name = str(data.get("name", "")).strip()
    url = str(data.get("url", "")).strip()
    events = data.get("events", [])
    if not name or len(name) > 100:
        return api_error("name is required and must be at most 100 characters.", 400)
    if not valid_public_https_url(url):
        return api_error("url must be a valid HTTP(S) endpoint and cannot use localhost.", 400)
    if not isinstance(events, list) or not events or len(events) > 30:
        return api_error("events must be a non-empty list of event names.", 400)
    allowed = safe_webhook_events()
    if any(not isinstance(event, str) or event not in allowed and event != "*" for event in events):
        return api_error("One or more webhook events are unsupported.", 400)
    secret = secrets.token_urlsafe(32)
    # The derived key is not returned again. The caller receives the secret once.
    secret_digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    row = WebhookEndpoint(organization_id=current_user.organization_id,
                          creator_id=current_user.id, name=name, url=url,
                          secret_hash=secret_digest, events_json=json.dumps(sorted(set(events))))
    db.session.add(row)
    db.session.commit()
    log_audit("webhook.created", "webhook_endpoint", row.id, {"events": sorted(set(events))})
    return api_success({**row.to_dict(), "signing_secret": secret},
                       "Webhook registered. Save the signing secret now; it is not shown again.", 201)

@webhooks_bp.patch("/<int:endpoint_id>")
@login_required
@active_account_required
def update_endpoint(endpoint_id):
    if not current_user.has_role("admin", "super_admin"):
        return api_error("Administrator permission required.", 403)
    row = _scope().filter_by(id=endpoint_id).first()
    if not row:
        return api_error("Webhook endpoint not found.", 404)
    data = _body()
    if "name" in data:
        name = str(data["name"]).strip()
        if not name or len(name) > 100:
            return api_error("name must be at most 100 characters.", 400)
        row.name = name
    if "url" in data:
        url = str(data["url"]).strip()
        if not valid_public_https_url(url):
            return api_error("url must be a valid HTTP(S) endpoint and cannot use localhost.", 400)
        row.url = url
    if "events" in data:
        events = data["events"]
        allowed = safe_webhook_events()
        if not isinstance(events, list) or not events or len(events) > 30 or any(e not in allowed and e != "*" for e in events):
            return api_error("events contains unsupported values.", 400)
        row.events_json = json.dumps(sorted(set(events)))
    if "active" in data:
        row.active = bool(data["active"])
    db.session.commit()
    return api_success(row.to_dict(), "Webhook endpoint updated.")

@webhooks_bp.delete("/<int:endpoint_id>")
@login_required
@active_account_required
def delete_endpoint(endpoint_id):
    if not current_user.has_role("admin", "super_admin"):
        return api_error("Administrator permission required.", 403)
    row = _scope().filter_by(id=endpoint_id).first()
    if not row:
        return api_error("Webhook endpoint not found.", 404)
    db.session.delete(row)
    db.session.commit()
    log_audit("webhook.deleted", "webhook_endpoint", endpoint_id, {})
    return api_success({"deleted": True})

@webhooks_bp.get("/deliveries")
@login_required
@active_account_required
def list_deliveries():
    try:
        limit = min(100, max(1, int(request.args.get("limit", 50))))
    except ValueError:
        return api_error("limit must be an integer.", 400)
    query = WebhookDelivery.query.join(WebhookEndpoint).filter(
        WebhookEndpoint.organization_id == current_user.organization_id)
    status = request.args.get("status")
    if status in {"pending", "delivering", "delivered", "failed"}:
        query = query.filter(WebhookDelivery.status == status)
    rows = query.order_by(WebhookDelivery.created_at.desc()).limit(limit).all()
    return api_success([row.to_dict() for row in rows])

@webhooks_bp.post("/deliveries/<int:delivery_id>/retry")
@login_required
@active_account_required
def retry_delivery(delivery_id):
    if not current_user.has_role("admin", "super_admin"):
        return api_error("Administrator permission required.", 403)
    row = (WebhookDelivery.query.join(WebhookEndpoint)
           .filter(WebhookDelivery.id == delivery_id,
                   WebhookEndpoint.organization_id == current_user.organization_id).first())
    if not row:
        return api_error("Webhook delivery not found.", 404)
    if row.status == "delivered":
        return api_error("A delivered webhook cannot be retried.", 409)
    row.status = "pending"
    row.next_attempt_at = datetime.now(timezone.utc).replace(tzinfo=None)
    row.last_error = None
    db.session.commit()
    log_audit("webhook.delivery_retry", "webhook_delivery", row.id, {})
    return api_success(row.to_dict(), "Delivery queued for retry.")
