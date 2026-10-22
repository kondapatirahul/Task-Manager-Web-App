# TaskNest API Contract

Base URL: `/api`

All API endpoints return JSON in a standardized envelope format:

### Success Response Envelope
```json
{
  "ok": true,
  "data": { ... },
  "message": "Optional human-readable confirmation message"
}
```

### Error Response Envelope
```json
{
  "ok": false,
  "error": "Human-readable error message"
}
```

---

## 1. Authentication (`/api/auth`)

| Method | Endpoint | Description | Request Body | Success Response | Error Codes |
|--------|----------|-------------|--------------|------------------|-------------|
| `POST` | `/api/auth/signup` | Register a new user | `{"email": "...", "password": "...", "full_name": "...", "username": "..."}` | `201 { "ok": true, "data": User, "message": "User registered successfully" }` | `400`, `409` |
| `POST` | `/api/auth/login` | Authenticate user & start session | `{"email": "...", "password": "...", "remember": true/false}` | `200 { "ok": true, "data": User, "message": "Logged in successfully" }` | `400`, `401` |
| `POST` | `/api/auth/logout` | Terminate session & log out | — | `200 { "ok": true, "message": "Logged out successfully" }` | `401` |
| `GET` | `/api/auth/me` | Retrieve authenticated user profile | — | `200 { "ok": true, "data": User }` | `401` |

> Note: `/api/auth/register` is supported as an alias for `/api/auth/signup`.

---

## 2. Tasks & Company Assignments (`/api/tasks`)

| Method | Endpoint | Description | Query Parameters / Body | Success Response | Error Codes |
|--------|----------|-------------|-------------------------|------------------|-------------|
| `GET` | `/api/tasks` | List accessible tasks with multi-factor filters | `q`, `scope`, `status`, `priority`, `category_id`, `team_id`, `assigned_to_id`, `due_before`, `due_after`, `sort` | `200 { "ok": true, "data": [Task, ...] }` | `401` |
| `POST` | `/api/tasks` | Create / assign a task with optional reference files | JSON or `multipart/form-data` with fields (`title`, `description`, `priority`, `status`, `team_id`, `assigned_to_id`, `start_date`, `due_date`, `category_id`, `acceptance_criteria`) and optional `files` / `reference_files` | `201 { "ok": true, "data": Task, "message": "Task created successfully" }` | `400`, `401`, `403`, `404` |
| `GET` | `/api/tasks/<id>` | Retrieve task by ID with full status history and collaboration counts | — | `200 { "ok": true, "data": Task }` | `401`, `404` |
| `PUT` | `/api/tasks/<id>` | Update an existing task (enforces field authorization) | `{"title": "...", "priority": "...", "status": "...", ...}` | `200 { "ok": true, "data": Task, "message": "Task updated successfully" }` | `400`, `401`, `403`, `404` |
| `DELETE` | `/api/tasks/<id>` | Delete a task and its stored attachments (manager/creator only) | — | `200 { "ok": true, "message": "Task deleted successfully" }` | `401`, `403`, `404` |
| `PATCH` | `/api/tasks/<id>/complete` | Toggle or set task completion | `{"status": "completed"}` *(optional body)* | `200 { "ok": true, "data": Task, "message": "Task status updated" }` | `400`, `401`, `403`, `404` |
| `POST` | `/api/tasks/<id>/submit` | Submit work with written summary & deliverable files | JSON or `multipart/form-data` with `notes` (summary) and optional deliverable `files` | `200 { "ok": true, "data": Task, "message": "Task submitted for review successfully" }` | `400`, `401`, `403`, `404` |
| `POST` | `/api/tasks/<id>/review` | Lead review: approve or request changes | `{"action": "approve" | "request_changes", "notes": "Feedback / sign-off notes..."}` | `200 { "ok": true, "data": Task, "message": "Task approved and completed" }` | `400`, `401`, `403`, `404` |

### Task Statuses:
- `todo` / `pending`: Initial open status.
- `in_progress`: Task actively being worked on.
- `blocked`: Task blocked by external dependencies.
- `in_review`: Employee has submitted work for Team Lead review.
- `changes_requested`: Team Lead requested modifications after review.
- `completed`: Approved and finished.

### Task Query Parameters:
- `q`: Full-text substring search across `title`, `description`, and `acceptance_criteria`.
- `scope`: `assigned_to_me`, `created_by_me`, `team`, or `all`.
- `status`: Filter by status (`todo`, `in_progress`, `blocked`, `in_review`, `changes_requested`, `completed`, `pending`).
- `priority`: `low`, `medium`, `high`.
- `category_id`: Category identifier.
- `team_id`: Team identifier.
- `assigned_to_id`: Assignee user identifier (or `me`).
- `due_before`, `due_after`: ISO Date strings `YYYY-MM-DD`.
- `sort`: `due_date_asc`, `due_date_desc`, `created_at_desc` (default), `created_at_asc`, `priority_desc`, `priority_asc`, `title_asc`.

### Authorization Rules:
1. **Employees**: Cannot assign tasks to other employees or teams. Can update status of assigned tasks (`in_progress`, `blocked`) and submit for review. Cannot modify protected fields (`title`, `priority`, `due_date`, `assigned_to_id`) or mark company tasks completed without lead approval.
2. **Team Leads**: Can assign tasks within their led teams and to team members. Cannot assign outside their authorized scope (returns 403). Can review submissions (approve or request changes).
3. **Admins**: Unrestricted organization-wide task management and review authority.

---

## 3. Categories (`/api/categories`)

| Method | Endpoint | Description | Request Body | Success Response | Error Codes |
|--------|----------|-------------|--------------|------------------|-------------|
| `GET` | `/api/categories` | List current user's categories | — | `200 { "ok": true, "data": [Category, ...] }` | `401` |
| `POST` | `/api/categories` | Create a new category | `{"name": "..."}` | `201 { "ok": true, "data": Category, "message": "Category created successfully" }` | `400`, `401`, `409` |
| `DELETE` | `/api/categories/<id>` | Safely delete category (unassigns associated tasks) | — | `200 { "ok": true, "message": "Category deleted and associated tasks unassigned successfully" }` | `401`, `404` |

---

## 4. Statistics (`/api/stats`)

| Method | Endpoint | Description | Success Response | Error Codes |
|--------|----------|-------------|------------------|-------------|
| `GET` | `/api/stats` | Real-time task statistics & counts | `200 { "ok": true, "data": Stats }` | `401` |

### Stats Data Model:
```json
{
  "total": 12,
  "pending": 8,
  "completed": 4,
  "overdue": 1,
  "due_today": 2,
  "high_priority": 3,
  "completion_rate": 33,
  "by_category": [
    { "id": 1, "name": "Work", "total": 6, "pending": 4 }
  ],
  "upcoming": [ ... ]
}
```
*Note: Overdue tasks are strictly defined as pending tasks whose `due_date` is earlier than today's local date.*

---

## 5. Employee Directory & Administration Endpoints

### 5.1 `GET /api/employees`
- **Description**: Query employee directory with multi-factor search and filtering.
- **Parameters**: `q` (keyword in name, username, email, job title), `department_id`, `team_id`, `role`, `status` (`active`, `inactive`, `all`), `organization_id`.
- **Response**: Array of employee profile objects.

### 5.2 `POST /api/employees`
- **Description**: Invite / create employee with secure activation credentials (Admin/HR only).
- **Body**: `{ "full_name": string, "email": string, "role": string, "department_id": int?, "team_ids": int[]?, "job_title": string?, "reports_to_id": int?, "password": string? }`
- **Response**: `201 Created` with employee record and `activation_token`.

### 5.3 `GET /api/employees/<id>`
- **Description**: Retrieve full employee profile with reporting hierarchy and task metrics.

### 5.4 `PUT /api/employees/<id>`
- **Description**: Update employee department, team memberships, role, and reporting manager (Admin/HR only).

### 5.5 `PATCH /api/employees/<id>/status`
- **Description**: Activate or safely deactivate employee account without deleting historical tasks or logs.
- **Body**: `{ "account_active": boolean }`

---

## 6. Organization & Department Endpoints

### 6.1 `GET /api/organizations`
- **Description**: List organizations accessible to user.

### 6.2 `POST /api/organizations`
- **Description**: Create new company organization (Admin/HR).
- **Body**: `{ "name": string, "description": string? }`

### 6.3 `GET /api/departments`
- **Description**: List departments for organization.

### 6.4 `POST /api/departments`
- **Description**: Create department within organization (Admin/HR).
- **Body**: `{ "name": string, "description": string?, "organization_id": int?, "head_id": int? }`

### 6.5 `DELETE /api/departments/<id>`
- **Description**: Safely delete department (unassigns members and teams without deleting them).

---

## 7. Teams Endpoints

### 7.1 `GET /api/teams`
- **Description**: List teams. Admin/HR view all in organization; Team Leads view only authorized teams.
- **Parameters**: `organization_id`, `department_id`, `q`.

### 7.2 `POST /api/teams`
- **Description**: Create team (Management: Admin, HR, Team Lead).
- **Body**: `{ "name": string, "description": string?, "department_id": int?, "lead_id": int? }`

### 7.3 `GET /api/teams/<id>`
- **Description**: Retrieve team details with members and tasks count (scoped to authorized teams for leads).

### 7.4 `POST /api/teams/<id>/members`
- **Description**: Add employee to team (Admin, HR, Team Lead).
- **Body**: `{ "user_id": int, "role": "member"|"lead" }`

### 7.5 `DELETE /api/teams/<id>/members/<user_id>`
- **Description**: Remove member from team.

### 7.6 `GET /api/teams/<id>/tasks`
- **Description**: List tasks assigned to this team.

### 7.7 `POST /api/teams/<id>/tasks`
- **Description**: Create task assigned to team and member.
- **Body**: `{ "title": string, "description": string?, "priority": string, "due_date": string?, "assigned_to_id": int? }`

### 7.8 `DELETE /api/teams/<id>`
- **Description**: Safely delete team (preserves assigned tasks by nullifying `team_id`).

---

## 8. Task Collaboration & Discussion (`/api/tasks/<task_id>/comments`)

Task-centered communication thread allowing authorized participants to discuss, ask questions, and share attachments.

| Method | Endpoint | Description | Request Body | Success Response | Error Codes |
|--------|----------|-------------|--------------|------------------|-------------|
| `GET` | `/api/tasks/<task_id>/comments` | Retrieve chronological discussion thread for task | — | `200 { "ok": true, "data": [Comment, ...] }` | `401`, `403`, `404` |
| `POST` | `/api/tasks/<task_id>/comments` | Post a message with optional file attachments | JSON (`{"content": "..."}`) or `multipart/form-data` with `content` string and multiple `files` | `201 { "ok": true, "data": Comment, "message": "Comment posted successfully" }` | `400`, `401`, `403`, `404` |

### Comment Data Model:
```json
{
  "id": 1,
  "task_id": 4,
  "user_id": 2,
  "author_name": "Jane Doe",
  "author_role": "employee",
  "content": "Updated the API contracts. @john_lead please take a look!",
  "mentions": [
    { "id": 1, "username": "john_lead", "full_name": "John Smith" }
  ],
  "attachments": [ ... ],
  "created_at": "2026-10-22T10:30:00Z",
  "updated_at": null
}
```

### Features:
- **@mentions**: Messages scan for `@username` patterns and return structured mention payloads for notification dispatch and UI badge rendering.
- **Audit Logging**: Important comments or messages with attachments automatically append an audit entry into `TaskStatusHistory`.

---

## 9. File Attachments & Private Storage (`/api/tasks/<task_id>/attachments`)

Secure file storage outside the database with strict validation, path traversal assertions, and authorized download/preview routes.

| Method | Endpoint | Description | Request Body / Query | Success Response | Error Codes |
|--------|----------|-------------|----------------------|------------------|-------------|
| `GET` | `/api/tasks/<task_id>/attachments` | List task reference attachments | Query: `type=reference` (optional) | `200 { "ok": true, "data": [Attachment, ...] }` | `401`, `403`, `404` |
| `POST` | `/api/tasks/<task_id>/attachments` | Upload reference files (Team Lead / Creator) | `multipart/form-data` with `files` or single `file` and optional `attachment_type="reference"` | `201 { "ok": true, "data": [Attachment, ...], "message": "Uploaded 1 attachment(s)" }` | `400`, `401`, `403`, `404` |
| `GET` | `/api/tasks/<task_id>/attachments/<id>/download` | Authenticated download attachment | — | Binary stream (`Content-Disposition: attachment; filename="original_name"`, `X-Content-Type-Options: nosniff`) | `401`, `403`, `404` |
| `GET` | `/api/tasks/<task_id>/attachments/<id>/preview` | Authenticated safe inline preview | — | Binary stream (`Content-Disposition: inline`, `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox`) | `401`, `403`, `404` |
| `DELETE` | `/api/tasks/<task_id>/attachments/<id>` | Delete attachment (Uploader / Manager) | — | `200 { "ok": true, "message": "Attachment deleted successfully" }` | `401`, `403`, `404` |

### Storage & Security Rules:
1. **Approved Formats**: PDF (`.pdf`), PNG (`.png`), JPEG (`.jpg`, `.jpeg`), DOCX (`.docx`), XLSX (`.xlsx`), Plain Text (`.txt`).
2. **File Size & Batch Limits**: Configurable up to 10 MB per file (`MAX_ATTACHMENT_SIZE`), maximum 5 files per message/upload (`MAX_ATTACHMENTS_PER_MESSAGE`), and 25 MB max request body (`MAX_CONTENT_LENGTH`).
3. **Magic Byte Signature Inspection**:
   - PDF: Starts with `%PDF-`
   - PNG: Starts with `\x89PNG\r\n\x1a\n`
   - JPEG: Starts with `\xff\xd8\xff`
   - DOCX / XLSX: ZIP magic bytes `PK\x03\x04`
   - TXT: Valid UTF-8 without binary null bytes (`\x00`)
4. **Storage Isolation**: Physical files reside in `instance/uploads/task_<task_id>/` with randomized UUID storage names (`uuid4().hex + '.' + ext`). Files are never served from the public static directory.
5. **Path Traversal Guard**: All resolved storage paths are asserted against `upload_root` via `os.path.commonpath([dest_path, upload_root]) == upload_root`.
6. **Download Authentication & Authorization**: Every download and preview verifies active session authentication and task read access (`can_user_view_task()`). Unauthenticated requests are rejected (401/403).

---

## 10. Work Submissions & Review History (`/api/tasks/<task_id>/submissions`)

Full cycle tracking for employee deliverables, lead reviews, and change requests.

| Method | Endpoint | Description | Request Body | Success Response | Error Codes |
|--------|----------|-------------|--------------|------------------|-------------|
| `GET` | `/api/tasks/<task_id>/submissions` | Retrieve all submission cycles and review decisions | — | `200 { "ok": true, "data": [Submission, ...] }` | `401`, `403`, `404` |
| `POST` | `/api/tasks/<task_id>/submit` | Submit work for review with notes & deliverables | `multipart/form-data` or JSON: `notes` (summary required), `files` (deliverables optional) | `200 { "ok": true, "data": Task, "message": "Task submitted for review successfully" }` | `400`, `401`, `403`, `404` |
| `POST` | `/api/tasks/<task_id>/review` | Review submission: approve or request changes | JSON: `action` (`"approve"` or `"request_changes"`), `notes` (feedback optional) | `200 { "ok": true, "data": Task, "message": "Task approved and completed" }` | `400`, `401`, `403`, `404` |

### Submission Data Model:
```json
{
  "id": 1,
  "task_id": 4,
  "submitted_by_id": 2,
  "submitted_by_name": "Jane Doe",
  "submitted_by_role": "employee",
  "summary": "Completed feature implementation, unit tests, and attached test report.",
  "status": "approved",
  "reviewed_by_id": 1,
  "reviewed_by_name": "John Smith",
  "reviewed_by_role": "team_lead",
  "reviewed_at": "2026-10-22T11:45:00Z",
  "review_feedback": "Excellent quality and test coverage. Approved!",
  "attachments": [
    {
      "id": 8,
      "original_filename": "test-report.pdf",
      "file_size_human": "1.2 MB",
      "file_extension": "pdf",
      "is_previewable": true,
      "download_url": "/api/tasks/4/attachments/8/download",
      "preview_url": "/api/tasks/4/attachments/8/preview"
    }
  ],
  "created_at": "2026-10-22T11:00:00Z"
}
```

---

## 11. M7 Notification System Integration Point

As the core in-app notifications system is scheduled for Milestone 7 (M7), task collaboration events are decoupled and routed through a dedicated notification service interface:

**Service Hook Location**: [`app.services.notifications.notify_task_collaboration_event`](file:///c:/Users/ASUS/OneDrive/Desktop/Task%20Manager/Task-Manager-Web-App/app/services/notifications.py)

### Collaboration Event Types Dispatched:
- `task_comment`: Dispatched when an authorized user posts a comment in the task thread. Notifies task assignee, creator, and extracted `@mentions`.
- `task_submission`: Dispatched when an employee submits work for review with deliverables. Notifies task creator and team leads.
- `task_review_approved`: Dispatched when a Team Lead approves the submission and marks the task completed. Notifies the submitting assignee.
- `task_review_changes_requested`: Dispatched when a Team Lead requests changes. Notifies the submitting assignee with feedback notes.
- `task_attachment_uploaded`: Dispatched when reference files are added to a task.

### Integration Contract:
When M7 notification models and tables (`Notification`, `NotificationRecipient`) are merged into `main`, update `notify_task_collaboration_event()` in `app/services/notifications.py`:
```python
# M7 Integration Point:
from app.models import Notification  # M7 model

notification = Notification(
    event_type=event_type,
    actor_id=actor.id if actor else None,
    task_id=task.id,
    data=metadata,
)
db.session.add(notification)
# Notify target user IDs:
# - Assignee: task.assigned_to_id
# - Creator: task.user_id
# - Mentioned users: metadata.get('mentioned_user_ids', [])
```
Until M7 is merged, the service logs events to application logging with complete metadata payload and gracefully handles absences without disrupting user workflows.


