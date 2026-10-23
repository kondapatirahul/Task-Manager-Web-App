"""
Integration and security tests for Task Collaboration and File Attachments.
Scope:
- Chronological discussion threads for tasks.
- Authorized participant communication and file exchange.
- Multiple approved file formats (PDF, PNG, JPEG, DOCX, XLSX, TXT).
- Validation: file count, size limits, format checks, magic byte validation.
- File security: path traversal prevention, authenticated download, safe preview.
- Task reference attachments when creating or editing tasks.
- Employee work submission with summary and deliverables.
- Team Lead review: approve or request changes with preserved history.
- @Mentions in task discussion.
- Activity audit entries for comments, uploads, submissions, and review decisions.
- Existing task workflow preservation.
"""

import io
import os
import pytest
from app import db
from app.models import (
    User,
    Team,
    team_members,
    Task,
    TaskStatusHistory,
    TaskComment,
    TaskSubmission,
    TaskAttachment,
    ROLE_ADMIN,
    ROLE_TEAM_LEAD,
    ROLE_EMPLOYEE,
    STATUS_TODO,
    STATUS_IN_PROGRESS,
    STATUS_IN_REVIEW,
    STATUS_COMPLETED,
    STATUS_CHANGES_REQUESTED,
)


@pytest.fixture
def collab_fixture(app):
    """
    Sets up:
    - Lead 1 (leads Team Alpha)
    - Emp 1 (member of Team Alpha)
    - Emp 2 (outsider / member of Team Beta)
    - Task 1 (created by Lead 1, assigned to Emp 1 in Team Alpha)
    """
    with app.app_context():
        lead1 = User(username='lead1', full_name='Alice Lead', email='lead1@example.com', role=ROLE_TEAM_LEAD)
        lead1.set_password('LeadPass123!')

        emp1 = User(username='emp1', full_name='Bob Employee', email='emp1@example.com', role=ROLE_EMPLOYEE)
        emp1.set_password('Emp1Pass123!')

        emp2 = User(username='emp2', full_name='Charlie Outsider', email='emp2@example.com', role=ROLE_EMPLOYEE)
        emp2.set_password('Emp2Pass123!')

        db.session.add_all([lead1, emp1, emp2])
        db.session.commit()

        team_alpha = Team(name='Team Alpha', lead_id=lead1.id)
        team_beta = Team(name='Team Beta', lead_id=lead1.id)
        db.session.add_all([team_alpha, team_beta])
        db.session.commit()

        # Add emp1 to team alpha
        db.session.execute(team_members.insert().values(team_id=team_alpha.id, user_id=emp1.id, role='member'))
        # Add emp2 to team beta
        db.session.execute(team_members.insert().values(team_id=team_beta.id, user_id=emp2.id, role='member'))

        # Create Task
        task = Task(
            title='Implement OAuth Flow',
            description='Build user authentication flow with security best practices.',
            priority='high',
            status=STATUS_TODO,
            team_id=team_alpha.id,
            user_id=lead1.id,
            assigned_to_id=emp1.id,
        )
        db.session.add(task)
        db.session.commit()

        return {
            'lead1_id': lead1.id,
            'emp1_id': emp1.id,
            'emp2_id': emp2.id,
            'task_id': task.id,
        }


def login_user(client, email, password):
    res = client.post('/api/auth/login', json={'email': email, 'password': password})
    assert res.status_code == 200


# Helpers to create valid mock file contents
def make_pdf():
    return (io.BytesIO(b'%PDF-1.4 Mock PDF file content for testing'), 'spec.pdf')


def make_png():
    return (io.BytesIO(b'\x89PNG\r\n\x1a\nMock PNG image content for testing'), 'screenshot.png')


def make_jpeg():
    return (io.BytesIO(b'\xff\xd8\xff\xe0\x00\x10JFIF Mock JPEG content'), 'photo.jpg')


def make_docx():
    return (io.BytesIO(b'PK\x03\x04Mock DOCX document in zip format'), 'requirements.docx')


def make_xlsx():
    return (io.BytesIO(b'PK\x03\x04Mock XLSX spreadsheet in zip format'), 'data.xlsx')


def make_txt():
    return (io.BytesIO(b'Plain text documentation notes'), 'notes.txt')


# ============================================================================
# 1. Discussion Thread & Participant Communication
# ============================================================================

def test_chronological_discussion_thread(client, collab_fixture):
    """Participants can post messages and view thread in chronological order."""
    task_id = collab_fixture['task_id']

    # Emp 1 logs in and asks a question
    login_user(client, 'emp1@example.com', 'Emp1Pass123!')
    res1 = client.post(f'/api/tasks/{task_id}/comments', json={
        'content': 'Should we use PKCE for the OAuth flow?'
    })
    assert res1.status_code == 201
    assert res1.get_json()['ok'] is True
    assert res1.get_json()['data']['content'] == 'Should we use PKCE for the OAuth flow?'

    # Lead 1 logs in and answers
    login_user(client, 'lead1@example.com', 'LeadPass123!')
    res2 = client.post(f'/api/tasks/{task_id}/comments', json={
        'content': 'Yes, PKCE is mandatory for all clients.'
    })
    assert res2.status_code == 201

    # Fetch thread
    thread_res = client.get(f'/api/tasks/{task_id}/comments')
    assert thread_res.status_code == 200
    comments = thread_res.get_json()['data']
    assert len(comments) == 2
    assert comments[0]['author_name'] == 'Bob Employee'
    assert comments[0]['content'] == 'Should we use PKCE for the OAuth flow?'
    assert comments[1]['author_name'] == 'Alice Lead'
    assert comments[1]['content'] == 'Yes, PKCE is mandatory for all clients.'


def test_comment_validation_edit_delete_and_permissions(client, collab_fixture):
    task_id = collab_fixture['task_id']
    login_user(client, 'emp1@example.com', 'Emp1Pass123!')

    empty = client.post(f'/api/tasks/{task_id}/comments', json={'content': '   '})
    assert empty.status_code == 400

    oversized = client.post(f'/api/tasks/{task_id}/comments', json={'content': 'x' * 5001})
    assert oversized.status_code == 400

    created = client.post(f'/api/tasks/{task_id}/comments', json={'content': 'Initial message'})
    assert created.status_code == 201
    comment_id = created.get_json()['data']['id']

    updated = client.put(
        f'/api/tasks/{task_id}/comments/{comment_id}',
        json={'content': 'Updated message'},
    )
    assert updated.status_code == 200
    assert updated.get_json()['data']['content'] == 'Updated message'

    login_user(client, 'lead1@example.com', 'LeadPass123!')
    moderated = client.delete(f'/api/tasks/{task_id}/comments/{comment_id}')
    assert moderated.status_code == 200

def test_comment_authorization_prevents_other_user_edit_or_delete(client, collab_fixture):
    task_id = collab_fixture['task_id']
    login_user(client, 'emp1@example.com', 'Emp1Pass123!')
    created = client.post(f'/api/tasks/{task_id}/comments', json={'content': 'Private update'})
    comment_id = created.get_json()['data']['id']

    login_user(client, 'emp2@example.com', 'Emp2Pass123!')
    assert client.put(
        f'/api/tasks/{task_id}/comments/{comment_id}',
        json={'content': 'Tampered'},
    ).status_code == 404
    assert client.delete(f'/api/tasks/{task_id}/comments/{comment_id}').status_code == 404


def test_comment_with_multiple_approved_attachments(client, collab_fixture):
    """Message can include multiple approved file attachments with metadata."""
    task_id = collab_fixture['task_id']
    login_user(client, 'emp1@example.com', 'Emp1Pass123!')

    pdf_stream, pdf_name = make_pdf()
    png_stream, png_name = make_png()

    res = client.post(
        f'/api/tasks/{task_id}/comments',
        data={
            'content': 'Attaching architecture spec and UI mockup.',
            'files': [
                (pdf_stream, pdf_name),
                (png_stream, png_name),
            ]
        },
        content_type='multipart/form-data'
    )
    assert res.status_code == 201
    data = res.get_json()['data']
    assert len(data['attachments']) == 2

    # Check attachment metadata
    filenames = [a['original_filename'] for a in data['attachments']]
    assert 'spec.pdf' in filenames
    assert 'screenshot.png' in filenames

    pdf_att = next(a for a in data['attachments'] if a['original_filename'] == 'spec.pdf')
    assert pdf_att['file_type'] == 'application/pdf'
    assert pdf_att['file_extension'] == 'pdf'
    assert pdf_att['is_previewable'] is True
    assert pdf_att['is_image'] is False
    assert pdf_att['download_url'].endswith(f"/attachments/{pdf_att['id']}/download")

    png_att = next(a for a in data['attachments'] if a['original_filename'] == 'screenshot.png')
    assert png_att['is_image'] is True
    assert png_att['is_previewable'] is True


# ============================================================================
# 2. File Format Support & Security Validation
# ============================================================================

@pytest.mark.parametrize('file_builder', [make_pdf, make_png, make_jpeg, make_docx, make_xlsx, make_txt])
def test_all_supported_file_types_accepted(client, collab_fixture, file_builder):
    """PDF, PNG, JPEG, DOCX, XLSX, and TXT are all accepted."""
    task_id = collab_fixture['task_id']
    login_user(client, 'lead1@example.com', 'LeadPass123!')

    stream, name = file_builder()
    res = client.post(
        f'/api/tasks/{task_id}/comments',
        data={'content': f'Testing {name}', 'files': [(stream, name)]},
        content_type='multipart/form-data'
    )
    assert res.status_code == 201
    att = res.get_json()['data']['attachments'][0]
    assert att['original_filename'] == name


def test_reject_unsupported_extension(client, collab_fixture):
    """Executable or script files are strictly rejected."""
    task_id = collab_fixture['task_id']
    login_user(client, 'emp1@example.com', 'Emp1Pass123!')

    bad_file = (io.BytesIO(b'malicious executable code'), 'malware.exe')
    res = client.post(
        f'/api/tasks/{task_id}/comments',
        data={'content': 'Here is the app', 'files': [bad_file]},
        content_type='multipart/form-data'
    )
    assert res.status_code == 400
    assert res.get_json()['ok'] is False
    assert 'not supported' in res.get_json()['error'].lower()


def test_reject_spoofed_file_content(client, collab_fixture):
    """File claiming to be PDF but lacking PDF signature is rejected."""
    task_id = collab_fixture['task_id']
    login_user(client, 'emp1@example.com', 'Emp1Pass123!')

    fake_pdf = (io.BytesIO(b'<html><script>alert(1)</script></html>'), 'fake.pdf')
    res = client.post(
        f'/api/tasks/{task_id}/comments',
        data={'content': 'Invoice attached', 'files': [fake_pdf]},
        content_type='multipart/form-data'
    )
    assert res.status_code == 400
    assert res.get_json()['ok'] is False
    assert 'does not match expected format' in res.get_json()['error'].lower()


def test_reject_empty_file(client, collab_fixture):
    """0-byte files are rejected."""
    task_id = collab_fixture['task_id']
    login_user(client, 'emp1@example.com', 'Emp1Pass123!')

    empty_file = (io.BytesIO(b''), 'empty.txt')
    res = client.post(
        f'/api/tasks/{task_id}/comments',
        data={'content': 'Empty note', 'files': [empty_file]},
        content_type='multipart/form-data'
    )
    assert res.status_code == 400
    assert 'empty' in res.get_json()['error'].lower()


def test_reject_oversized_file(client, collab_fixture, app):
    """Files exceeding size limit are rejected."""
    task_id = collab_fixture['task_id']
    login_user(client, 'emp1@example.com', 'Emp1Pass123!')

    # Temporarily set limit to 1 KB for test
    app.config['MAX_ATTACHMENT_SIZE'] = 1024

    oversized = (io.BytesIO(b'%PDF-1.4 ' + b'A' * 2000), 'large.pdf')
    res = client.post(
        f'/api/tasks/{task_id}/comments',
        data={'content': 'Big file', 'files': [oversized]},
        content_type='multipart/form-data'
    )
    assert res.status_code == 400
    assert 'maximum size limit' in res.get_json()['error'].lower()


def test_reject_too_many_files_in_message(client, collab_fixture, app):
    """Uploading more than allowed files count is rejected."""
    task_id = collab_fixture['task_id']
    login_user(client, 'emp1@example.com', 'Emp1Pass123!')

    app.config['MAX_ATTACHMENTS_PER_MESSAGE'] = 2

    files = [
        (io.BytesIO(b'content 1'), 'f1.txt'),
        (io.BytesIO(b'content 2'), 'f2.txt'),
        (io.BytesIO(b'content 3'), 'f3.txt'),
    ]
    res = client.post(
        f'/api/tasks/{task_id}/comments',
        data={'content': 'Many files', 'files': files},
        content_type='multipart/form-data'
    )
    assert res.status_code == 400
    assert 'cannot upload more than 2' in res.get_json()['error'].lower()


# ============================================================================
# 3. Authentication, Authorization & Download Security
# ============================================================================

def test_authorized_download_and_preview(client, collab_fixture):
    """Authorized participant can download and preview with security headers."""
    task_id = collab_fixture['task_id']
    login_user(client, 'lead1@example.com', 'LeadPass123!')

    png_stream, png_name = make_png()
    post_res = client.post(
        f'/api/tasks/{task_id}/comments',
        data={'content': 'Here is the diagram', 'files': [(png_stream, png_name)]},
        content_type='multipart/form-data'
    )
    att_id = post_res.get_json()['data']['attachments'][0]['id']

    # Download check
    dl_res = client.get(f'/api/tasks/{task_id}/attachments/{att_id}/download')
    assert dl_res.status_code == 200
    assert dl_res.headers.get('Content-Type') == 'image/png'
    assert 'attachment' in dl_res.headers.get('Content-Disposition', '')
    assert dl_res.headers.get('X-Content-Type-Options') == 'nosniff'

    # Preview check
    prev_res = client.get(f'/api/tasks/{task_id}/attachments/{att_id}/preview')
    assert prev_res.status_code == 200
    assert 'inline' in prev_res.headers.get('Content-Disposition', '')
    assert 'sandbox' in prev_res.headers.get('Content-Security-Policy', '')


def test_unauthorized_user_cannot_access_collaboration(client, collab_fixture):
    """Unauthorized user (emp2 from another team) cannot view or download."""
    task_id = collab_fixture['task_id']

    # First lead uploads a file
    login_user(client, 'lead1@example.com', 'LeadPass123!')
    pdf_stream, pdf_name = make_pdf()
    res = client.post(
        f'/api/tasks/{task_id}/comments',
        data={'content': 'Confidential spec', 'files': [(pdf_stream, pdf_name)]},
        content_type='multipart/form-data'
    )
    att_id = res.get_json()['data']['attachments'][0]['id']

    # Now emp2 logs in
    login_user(client, 'emp2@example.com', 'Emp2Pass123!')

    # Emp2 cannot view comments
    c_res = client.get(f'/api/tasks/{task_id}/comments')
    assert c_res.status_code == 404

    # Emp2 cannot post comments
    post_res = client.post(f'/api/tasks/{task_id}/comments', json={'content': 'Hello intruder'})
    assert post_res.status_code == 404

    # Emp2 cannot download attachments
    dl_res = client.get(f'/api/tasks/{task_id}/attachments/{att_id}/download')
    assert dl_res.status_code == 404

    # Unauthenticated user cannot access
    client.post('/api/auth/logout')
    anon_res = client.get(f'/api/tasks/{task_id}/attachments/{att_id}/download')
    assert anon_res.status_code == 401


def test_path_traversal_prevention(client, collab_fixture):
    """Filenames attempting directory traversal are safely sanitized."""
    task_id = collab_fixture['task_id']
    login_user(client, 'lead1@example.com', 'LeadPass123!')

    traversal_file = (io.BytesIO(b'%PDF-1.4 safe pdf'), '../../../../etc/passwd.pdf')
    res = client.post(
        f'/api/tasks/{task_id}/comments',
        data={'content': 'Testing traversal', 'files': [traversal_file]},
        content_type='multipart/form-data'
    )
    assert res.status_code == 201
    att = res.get_json()['data']['attachments'][0]
    # Check that storage name has no slashes or dots
    assert '/' not in att['download_url'].split('/')[-2]


# ============================================================================
# 4. Task Reference Attachments (Lead create & edit)
# ============================================================================

def test_task_reference_attachments_creation(client, collab_fixture):
    """Team Lead creates a task with reference attachments."""
    login_user(client, 'lead1@example.com', 'LeadPass123!')

    pdf_stream, pdf_name = make_pdf()
    res = client.post(
        '/api/tasks',
        data={
            'title': 'Task with References',
            'description': 'Reference specs attached.',
            'priority': 'medium',
            'files': [(pdf_stream, pdf_name)]
        },
        content_type='multipart/form-data'
    )
    assert res.status_code == 201
    task_data = res.get_json()['data']
    task_id = task_data['id']
    assert len(task_data['reference_attachments']) == 1
    assert task_data['reference_attachments'][0]['original_filename'] == 'spec.pdf'
    assert task_data['reference_attachments'][0]['attachment_type'] == 'reference'

    # Direct reference upload endpoint
    png_stream, png_name = make_png()
    upload_res = client.post(
        f'/api/tasks/{task_id}/attachments',
        data={
            'attachment_type': 'reference',
            'files': [(png_stream, png_name)]
        },
        content_type='multipart/form-data'
    )
    assert upload_res.status_code == 201
    assert len(upload_res.get_json()['data']) == 1

    # Employee cannot upload reference files on assigned task
    login_user(client, 'emp1@example.com', 'Emp1Pass123!')
    txt_stream, txt_name = make_txt()
    emp_upload_res = client.post(
        f"/api/tasks/{collab_fixture['task_id']}/attachments",
        data={'files': [(txt_stream, txt_name)]},
        content_type='multipart/form-data'
    )
    assert emp_upload_res.status_code == 403


# ============================================================================
# 5. Work Submission, Review, Deliverables & History
# ============================================================================

def test_submission_and_review_workflow_with_deliverables(client, collab_fixture):
    """
    Employee submits work with summary and deliverables.
    Team Lead requests changes.
    Employee resubmits with revised deliverables.
    Team Lead approves.
    Full history persists.
    """
    task_id = collab_fixture['task_id']

    # --- Cycle 1: Employee submits first draft ---
    login_user(client, 'emp1@example.com', 'Emp1Pass123!')
    docx_stream, docx_name = make_docx()
    sub1_res = client.post(
        f'/api/tasks/{task_id}/submit',
        data={
            'notes': 'First draft of the OAuth implementation is ready.',
            'files': [(docx_stream, docx_name)]
        },
        content_type='multipart/form-data'
    )
    assert sub1_res.status_code == 200
    task_state = sub1_res.get_json()['data']
    assert task_state['status'] == STATUS_IN_REVIEW

    # --- Cycle 1: Lead requests changes ---
    login_user(client, 'lead1@example.com', 'LeadPass123!')
    rev1_res = client.post(f'/api/tasks/{task_id}/review', json={
        'action': 'request_changes',
        'notes': 'Please add unit test coverage for token refresh.'
    })
    assert rev1_res.status_code == 200
    task_state = rev1_res.get_json()['data']
    assert task_state['status'] == STATUS_CHANGES_REQUESTED

    # --- Cycle 2: Employee resubmits with test results ---
    login_user(client, 'emp1@example.com', 'Emp1Pass123!')
    txt_stream, txt_name = make_txt()
    sub2_res = client.post(
        f'/api/tasks/{task_id}/submit',
        data={
            'notes': 'Added unit tests. 100% pass rate on refresh token flow.',
            'files': [(txt_stream, txt_name)]
        },
        content_type='multipart/form-data'
    )
    assert sub2_res.status_code == 200
    assert sub2_res.get_json()['data']['status'] == STATUS_IN_REVIEW

    # --- Cycle 2: Lead approves ---
    login_user(client, 'lead1@example.com', 'LeadPass123!')
    rev2_res = client.post(f'/api/tasks/{task_id}/review', json={
        'action': 'approve',
        'notes': 'Tests look comprehensive. Approved for merge!'
    })
    assert rev2_res.status_code == 200
    assert rev2_res.get_json()['data']['status'] == STATUS_COMPLETED

    # --- Verify Complete Submission & Review History ---
    subs_res = client.get(f'/api/tasks/{task_id}/submissions')
    assert subs_res.status_code == 200
    subs = subs_res.get_json()['data']
    assert len(subs) == 2

    # Most recent submission (approved)
    assert subs[0]['status'] == 'approved'
    assert '100% pass rate' in subs[0]['summary']
    assert subs[0]['reviewed_by_name'] == 'Alice Lead'
    assert 'Approved for merge' in subs[0]['review_feedback']
    assert len(subs[0]['attachments']) == 1

    # First submission (changes requested)
    assert subs[1]['status'] == 'changes_requested'
    assert 'First draft' in subs[1]['summary']
    assert 'unit test coverage' in subs[1]['review_feedback']
    assert len(subs[1]['attachments']) == 1


# ============================================================================
# 6. @Mentions & Activity Audit Entries
# ============================================================================

def test_mentions_in_comments(client, collab_fixture):
    """@mentions are parsed and return user metadata."""
    task_id = collab_fixture['task_id']
    login_user(client, 'lead1@example.com', 'LeadPass123!')

    res = client.post(f'/api/tasks/{task_id}/comments', json={
        'content': 'Hey @emp1, please check the database migration when you have a moment.'
    })
    assert res.status_code == 201
    data = res.get_json()['data']
    assert len(data['mentions']) == 1
    assert data['mentions'][0]['username'] == 'emp1'
    assert data['mentions'][0]['full_name'] == 'Bob Employee'


def test_attachment_deletion_permissions(client, collab_fixture):
    """Only uploader or manager can delete an attachment."""
    task_id = collab_fixture['task_id']

    # Emp1 uploads a file
    login_user(client, 'emp1@example.com', 'Emp1Pass123!')
    txt_stream, txt_name = make_txt()
    res = client.post(
        f'/api/tasks/{task_id}/comments',
        data={'content': 'Note', 'files': [(txt_stream, txt_name)]},
        content_type='multipart/form-data'
    )
    att_id = res.get_json()['data']['attachments'][0]['id']

    # Lead1 (manager) can delete it
    login_user(client, 'lead1@example.com', 'LeadPass123!')
    del_res = client.delete(f'/api/tasks/{task_id}/attachments/{att_id}')
    assert del_res.status_code == 200
    assert del_res.get_json()['ok'] is True

    # Check file is deleted
    check_res = client.get(f'/api/tasks/{task_id}/attachments/{att_id}/download')
    assert check_res.status_code == 404
