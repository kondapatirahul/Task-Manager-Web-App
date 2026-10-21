# API Contract

Base URL: `/api`

## Auth
| Method | Endpoint | Body | Response |
|--------|----------|------|----------|
| POST | `/auth/register` | `{username, email, password}` | `201 {message}` |
| POST | `/auth/login` | `{email, password}` | `200 {message, user}` |
| POST | `/auth/logout` | — | `200 {message}` |

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
