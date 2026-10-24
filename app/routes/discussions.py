"""
Task Discussions, Secure Attachments, Work Submissions, and Review API routes.
"""
import os
import uuid
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from flask import Blueprint, request, current_app, send_file, abort
from flask_login import current_user, login_required
from app import db
from app.models import (
    Task, TaskMessage, TaskAttachment, WorkSubmission, User,
    STATUS_IN_REVIEW, STATUS_COMPLETED, STATUS_CHANGES_REQUESTED,
    ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_TEAM_LEAD
)
from app.routes.utils import (
    api_success, api_error, active_account_required,
    log_audit, send_notification
)

discussions_bp = Blueprint('discussions', __name__, url_prefix='/api')

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'docx', 'xlsx', 'txt'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16 MB limit


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def user_can_access_task(task, user):
    """Check if the user has authorization to view/participate in this task."""
    if user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        return True
    if task.user_id == user.id or task.creator_id == user.id or task.assignee_id == user.id:
        return True
    if user.is_team_lead and (task.team_id == user.team_id or task.creator_id == user.id):
        return True
    return False


# ── Task Discussion Messages ───────────────────────────────────────────────────

@discussions_bp.route('/tasks/<int:task_id>/messages', methods=['GET', 'POST'])
@login_required
@active_account_required
def task_messages(task_id):
    task = Task.query.get_or_404(task_id)
    if not user_can_access_task(task, current_user):
        return api_error('You do not have permission to access this task thread.', 403)

    if request.method == 'GET':
        msgs = TaskMessage.query.filter_by(task_id=task.id).order_by(TaskMessage.created_at.asc()).all()
        return api_success([m.to_dict() for m in msgs])

    # POST message
    data = request.get_json(silent=True) or request.form
    content = (data.get('content') or '').strip()
    if not content:
        return api_error('Message content cannot be empty.', 400)
    if len(content) > 5000:
        return api_error('Message must be 5000 characters or fewer.', 400)

    msg = TaskMessage(task_id=task.id, user_id=current_user.id, content=content)
    db.session.add(msg)
    db.session.flush()
    uploaded = request.files.get('file')
    if uploaded and uploaded.filename:
        if not allowed_file(uploaded.filename):
            db.session.rollback()
            return api_error(f"File extension not permitted. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}", 400)
        filename = secure_filename(uploaded.filename)
        uploaded.seek(0, os.SEEK_END); size = uploaded.tell(); uploaded.seek(0)
        if size > MAX_FILE_SIZE:
            db.session.rollback(); return api_error('File exceeds maximum allowed size of 16MB.', 400)
        ext = filename.rsplit('.', 1)[1].lower()
        upload_dir = os.path.join(current_app.instance_path, 'uploads'); os.makedirs(upload_dir, exist_ok=True)
        saved_path = os.path.join(upload_dir, f"{uuid.uuid4().hex}.{ext}")
        uploaded.save(saved_path)
        db.session.add(TaskAttachment(task_id=task.id, message_id=msg.id, user_id=current_user.id, filename=filename, file_path=saved_path, file_size=size, content_type=uploaded.content_type))
    db.session.commit()

    # Notify counterparty (if sender is assignee, notify creator; else notify assignee)
    recipient_id = task.creator_id if current_user.id == task.assignee_id else task.assignee_id
    if recipient_id and recipient_id != current_user.id:
        send_notification(
            recipient_id,
            f'New message on "{task.title}"',
            f"{current_user.full_name or current_user.username}: {content[:80]}",
            f"/tasks?task_id={task.id}",
            'task_message'
        )

    log_audit('task_message_posted', 'Task', task.id, f'Posted message on task {task.id}')
    return api_success(msg.to_dict(), message='Message posted.', status_code=201)


@discussions_bp.route('/tasks/<int:task_id>/messages/<int:message_id>', methods=['DELETE'])
@login_required
@active_account_required
def delete_task_message(task_id, message_id):
    msg = TaskMessage.query.filter_by(id=message_id, task_id=task_id).first_or_404()
    if msg.user_id != current_user.id and not current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN):
        return api_error('You can only delete your own messages.', 403)

    db.session.delete(msg)
    db.session.commit()
    return api_success(message='Message deleted.')


# ── File Uploads & Secure Download ─────────────────────────────────────────────

@discussions_bp.route('/tasks/<int:task_id>/attachments', methods=['POST'])
@login_required
@active_account_required
def upload_attachment(task_id):
    task = Task.query.get_or_404(task_id)
    if not user_can_access_task(task, current_user):
        return api_error('Unauthorized to attach files to this task.', 403)

    if 'file' not in request.files:
        return api_error('No file part provided in request.', 400)

    file = request.files['file']
    if not file or file.filename == '':
        return api_error('No file selected.', 400)

    if not allowed_file(file.filename):
        return api_error(
            f"File extension not permitted. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            400
        )

    orig_filename = secure_filename(file.filename)
    ext = orig_filename.rsplit('.', 1)[1].lower() if '.' in orig_filename else ''
    unique_name = f"{uuid.uuid4().hex}.{ext}"

    # Target directory in instance/uploads
    upload_dir = os.path.join(current_app.instance_path, 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    saved_path = os.path.join(upload_dir, unique_name)

    file.seek(0, os.SEEK_END)
    size = file.tell()
    if size > MAX_FILE_SIZE:
        return api_error('File exceeds maximum allowed size of 16MB.', 400)
    file.seek(0)

    file.save(saved_path)

    message_id = request.form.get('message_id')
    submission_id = request.form.get('submission_id')

    attachment = TaskAttachment(
        task_id=task.id,
        message_id=int(message_id) if message_id else None,
        submission_id=int(submission_id) if submission_id else None,
        user_id=current_user.id,
        filename=orig_filename,
        file_path=saved_path,
        file_size=size,
        content_type=file.content_type
    )
    db.session.add(attachment)
    db.session.commit()

    log_audit('file_uploaded', 'Task', task.id, f'Uploaded {orig_filename} ({size} bytes)')
    return api_success(attachment.to_dict(), message='File uploaded successfully.', status_code=201)


@discussions_bp.route('/files/<int:file_id>/download', methods=['GET'])
@login_required
@active_account_required
def download_attachment(file_id):
    attachment = TaskAttachment.query.get_or_404(file_id)
    task = Task.query.get_or_404(attachment.task_id)

    if not user_can_access_task(task, current_user):
        return api_error('You do not have authorization to view or download this file.', 403)

    if not os.path.isfile(attachment.file_path):
        return api_error('File not found on storage layer.', 404)

    return send_file(
        attachment.file_path,
        as_attachment=True,
        download_name=attachment.filename,
        mimetype=attachment.content_type or 'application/octet-stream'
    )


# ── Work Submissions & Reviews ────────────────────────────────────────────────

@discussions_bp.route('/tasks/<int:task_id>/submissions', methods=['GET', 'POST'])
@login_required
@active_account_required
def task_submissions(task_id):
    task = Task.query.get_or_404(task_id)
    if not user_can_access_task(task, current_user):
        return api_error('Unauthorized to view task submissions.', 403)

    if request.method == 'GET':
        subs = WorkSubmission.query.filter_by(task_id=task.id).order_by(WorkSubmission.created_at.desc()).all()
        return api_success([s.to_dict() for s in subs])

    # POST work submission
    data = request.get_json(silent=True) or request.form
    notes = (data.get('notes') or data.get('message') or '').strip()
    if not notes:
        return api_error('Submission notes/summary are required.', 400)

    sub = WorkSubmission(
        task_id=task.id,
        user_id=current_user.id,
        notes=notes,
        status='submitted'
    )
    db.session.add(sub)

    # Transition task state to in_review
    task.status = STATUS_IN_REVIEW
    db.session.commit()

    # Link any attachment IDs passed
    attachment_ids = data.get('attachment_ids') or []
    if isinstance(attachment_ids, list):
        for att_id in attachment_ids:
            att = TaskAttachment.query.filter_by(id=att_id, task_id=task.id).first()
            if att:
                att.submission_id = sub.id
        db.session.commit()

    # Notify reviewer / lead / creator
    reviewer_id = task.creator_id or task.user_id
    if reviewer_id and reviewer_id != current_user.id:
        send_notification(
            reviewer_id,
            f'Work Submitted for Review: "{task.title}"',
            f"{current_user.full_name or current_user.username} submitted deliverables for your review.",
            f"/tasks?task_id={task.id}",
            'submission_review'
        )

    log_audit('work_submitted', 'Task', task.id, f'Submitted work for task {task.title}')
    return api_success(sub.to_dict(), message='Work submitted for review.', status_code=201)


@discussions_bp.route('/tasks/<int:task_id>/submissions/<int:submission_id>/review', methods=['POST'])
@login_required
@active_account_required
def review_submission(task_id, submission_id):
    task = Task.query.get_or_404(task_id)
    sub = WorkSubmission.query.filter_by(id=submission_id, task_id=task.id).first_or_404()

    # Submitter or assignee cannot approve their own work
    if current_user.id == sub.user_id:
        return api_error('Employees cannot approve their own work.', 403)
    if task.assignee_id and current_user.id == task.assignee_id:
        return api_error('Employees cannot approve their own work.', 403)

    # Must be lead/creator or admin to review
    can_review = (
        current_user.has_role(ROLE_SUPER_ADMIN, ROLE_ADMIN) or
        current_user.id == task.creator_id
    )
    if not can_review and current_user.is_team_lead:
        led_teams = [t.id for t in Team.query.filter_by(lead_id=current_user.id).all()]
        if current_user.team_id and current_user.team_id not in led_teams:
            led_teams.append(current_user.team_id)
        if task.team_id in led_teams:
            can_review = True
        elif task.assignee_id:
            from app.models import TeamMember, User
            if TeamMember.query.filter(TeamMember.team_id.in_(led_teams), TeamMember.user_id == task.assignee_id).first():
                can_review = True
            elif User.query.filter(User.id == task.assignee_id, User.team_id.in_(led_teams)).first():
                can_review = True

    if not can_review:
        return api_error('Permission denied to review task submissions.', 403)

    data = request.get_json(silent=True) or {}
    decision = (data.get('decision') or '').strip().lower()
    review_notes = (data.get('review_notes') or '').strip()

    if decision not in ('approve', 'approved', 'request_changes', 'changes_requested'):
        return api_error("Decision must be either 'approve' or 'request_changes'.", 400)

    now = datetime.now(timezone.utc)
    sub.reviewed_by = current_user.id
    sub.reviewed_at = now
    sub.review_notes = review_notes

    old_status = task.status
    if decision in ('approve', 'approved'):
        sub.status = 'approved'
        task.status = STATUS_COMPLETED
        task.completed_at = now
        task.progress = 100
        msg_title = f'Submission Approved: "{task.title}"'
        msg_body = f'Your submission for "{task.title}" was approved by {current_user.full_name or current_user.username}.'
        from app.models import TaskStatusHistory
        db.session.add(TaskStatusHistory(
            task_id=task.id,
            changed_by_id=current_user.id,
            old_status=old_status,
            new_status=STATUS_COMPLETED,
            comment=f"Submission approved: {review_notes}" if review_notes else "Submission approved"
        ))
    else:
        sub.status = 'changes_requested'
        task.status = STATUS_CHANGES_REQUESTED
        task.completed_at = None
        msg_title = f'Changes Requested: "{task.title}"'
        msg_body = f'Changes were requested on "{task.title}": {review_notes[:100]}'
        from app.models import TaskStatusHistory
        db.session.add(TaskStatusHistory(
            task_id=task.id,
            changed_by_id=current_user.id,
            old_status=old_status,
            new_status=STATUS_CHANGES_REQUESTED,
            comment=f"Changes requested: {review_notes}" if review_notes else "Changes requested"
        ))

    db.session.commit()

    # Notify submitter
    if sub.user_id != current_user.id:
        send_notification(
            sub.user_id,
            msg_title,
            msg_body,
            f"/tasks?task_id={task.id}",
            'submission_review'
        )

    log_audit('submission_reviewed', 'Task', task.id, f'Review decision: {sub.status}')
    return api_success(sub.to_dict(), message=f'Submission review recorded: {sub.status}')
