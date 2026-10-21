# Database Schema

## users
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PK |
| username | VARCHAR(80) | UNIQUE, NOT NULL |
| email | VARCHAR(120) | UNIQUE, NOT NULL |
| password_hash | VARCHAR(256) | NOT NULL |

## categories
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PK |
| name | VARCHAR(50) | NOT NULL |
| user_id | INTEGER | FK → users.id |

## tasks
| Column | Type | Constraints |
|--------|------|-------------|
| id | INTEGER | PK |
| title | VARCHAR(200) | NOT NULL |
| description | TEXT | |
| status | VARCHAR(20) | default: pending |
| priority | VARCHAR(10) | default: medium |
| due_date | DATETIME | |
| created_at | DATETIME | default: now |
| user_id | INTEGER | FK → users.id |
| category_id | INTEGER | FK → categories.id |
