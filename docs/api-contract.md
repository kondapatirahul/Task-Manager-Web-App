# API Contract

Base URL: `/api`

## Auth
| Method | Endpoint | Body | Response |
|--------|----------|------|----------|
| POST | `/auth/register` | `{username, email, password}` | `201 {message}` |
| POST | `/auth/login` | `{email, password}` | `200 {message, user}` |
| GET | `/auth/me` | — | `200 {id, username, email}` |
| POST | `/auth/logout` | — | `200 {message}` |

Login uses a Flask session cookie. Task, category, stats, and current-user endpoints
require an authenticated session and return `401 {error}` otherwise.

API errors use the JSON shape `{ "error": "message" }`. Invalid JSON or field
values return `400`, an unsupported content type returns `415`, a duplicate
registration returns `409`, and missing or inaccessible resources return `404`.
Unsupported methods return `405`. Unexpected server errors return
`500 { "error": "Internal server error" }`; implementation details are not
included in responses.

## Tasks
| Method | Endpoint | Body | Response |
|--------|----------|------|----------|
| GET | `/tasks` | — | `200 [task]` |
| POST | `/tasks` | `{title, description?, status?, priority?, category_id?}` | `201 {id, title}` |
| PUT | `/tasks/:id` | `{title?, description?, status?, priority?, category_id?}` | `200 {message}` |
| DELETE | `/tasks/:id` | — | `200 {message}` |

## Categories
| Method | Endpoint | Body | Response |
|--------|----------|------|----------|
| GET | `/categories` | — | `200 [category]` |
| POST | `/categories` | `{name}` | `201 {id, name}` |
| DELETE | `/categories/:id` | — | `200 {message}` |

## Stats
| Method | Endpoint | Response |
|--------|----------|----------|
| GET | `/stats` | `200 {total, pending, in_progress, done, high_priority}` |
