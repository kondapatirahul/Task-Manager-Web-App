"""
TaskNest Collaboration Notification Service & M7 Integration Point.

This module provides the central notification hook for task collaboration events.
When M7 (In-app Notification System & Alerts) is implemented, this service will dispatch
real-time alerts, in-app notifications, and message highlights.
"""

import logging
from typing import Optional, List, Dict, Any
from app import db

logger = logging.getLogger('tasknest.notifications')


def notify_task_collaboration_event(
    event_type: str,
    task,
    actor,
    recipients: Optional[List[int]] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Dispatch a task collaboration notification event.

    Supported event types:
    - 'comment_created': Participant posted a new message in the discussion thread.
    - 'user_mentioned': User was @mentioned in a discussion message.
    - 'reference_uploaded': Team lead attached task reference files.
    - 'submission_created': Assignee submitted work with deliverables for review.
    - 'review_approved': Team lead approved submission and completed task.
    - 'review_changes_requested': Team lead requested changes on submitted work.

    Integration Point for M7:
    -------------------------
    Once the M7 Notification module is active, wire the event to:
    1. Query user notification preferences.
    2. Insert records into the `notifications` table (`recipient_id`, `actor_id`, `task_id`, `type`, `message`, `read=False`).
    3. Push real-time WebSocket / SSE payload to active user sessions.
    """
    metadata = metadata or {}
    logger.info(
        f"[Collaboration Event] type='{event_type}' task_id={getattr(task, 'id', None)} "
        f"actor='{getattr(actor, 'username', 'system')}' "
        f"recipients={recipients} metadata={metadata}"
    )

    # Future M7 hook:
    # try:
    #     from app.models import Notification
    #     for r_id in (recipients or []):
    #         if r_id != actor.id:
    #             notif = Notification(user_id=r_id, actor_id=actor.id, task_id=task.id, event_type=event_type, ...)
    #             db.session.add(notif)
    #     db.session.commit()
    # except (ImportError, Exception):
    #     pass
