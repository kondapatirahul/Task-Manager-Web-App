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
| `POST` | `/api/tasks` | Create / assign a task | `{"title": "...", "description": "...", "priority": "...", "status": "...", "team_id": 1, "assigned_to_id": 2, "start_date": "YYYY-MM-DD", "due_date": "YYYY-MM-DD", "category_id": 1, "acceptance_criteria": "..."}` | `201 { "ok": true, "data": Task, "message": "Task created successfully" }` | `400`, `401`, `403`, `404` |
| `GET` | `/api/tasks/<id>` | Retrieve task by ID with full status history | — | `200 { "ok": true, "data": Task }` | `401`, `404` |
| `PUT` | `/api/tasks/<id>` | Update an existing task (enforces field authorization) | `{"title": "...", "priority": "...", "status": "...", ...}` | `200 { "ok": true, "data": Task, "message": "Task updated successfully" }` | `400`, `401`, `403`, `404` |
| `DELETE` | `/api/tasks/<id>` | Delete a task (manager/creator only) | — | `200 { "ok": true, "message": "Task deleted successfully" }` | `401`, `403`, `404` |
| `PATCH` | `/api/tasks/<id>/complete` | Toggle or set task completion | `{"status": "completed"}` *(optional body)* | `200 { "ok": true, "data": Task, "message": "Task status updated" }` | `400`, `401`, `403`, `404` |
| `POST` | `/api/tasks/<id>/submit` | Submit work for review (assignee employee) | `{"notes": "Summary of work completed..."}` | `200 { "ok": true, "data": Task, "message": "Task submitted for review successfully" }` | `401`, `403`, `404` |
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

