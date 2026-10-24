# TaskNest Audit Log API

The administrative audit API exposes a read-only, organization-scoped view of recorded application events.

## Authorization

All endpoints require an authenticated, active account with the `admin` or `super_admin` role. Regular employees and team leads receive `403 Forbidden`. Administrators see only events associated with their organization; a super administrator can query across organizations. Administrators without an organization assignment are limited to unassigned organization events.

## List events

`GET /api/audit-logs`

Optional query parameters:

| Parameter | Meaning | Validation |
|---|---|---|
| `page` | One-based page number | Integer >= 1 |
| `page_size` | Rows per page | Integer from 1 to 200; default 50 |
| `action` | Exact event action | Up to 100 characters |
| `entity_type` | Exact entity type | Up to 50 characters |
| `user_id` | Actor user ID | Positive integer |
| `start_date` | Inclusive start date | `YYYY-MM-DD` |
| `end_date` | Inclusive end date | `YYYY-MM-DD` |

Results are ordered newest-first and include `items`, `pagination`, and normalized `filters` inside the standard API envelope. Invalid filters return `400` with a descriptive error. Date ranges with a start after the end are rejected.

## Export CSV

`GET /api/audit-logs/export.csv`

Uses the same filters and authorization scope. Exports up to 10,000 rows; larger exports return `413` and require a narrower filter. Text fields are escaped against spreadsheet formula injection. The export includes event IDs, timestamps, organization and actor IDs, actor name, action, entity, details, and IP address.

## Operational notes

- Audit events are read-only through these endpoints; event creation stays in the application's audit helper.
- The export limit prevents unbounded in-memory CSV generation.
- Database migrations should be used for future schema changes; do not merge live SQLite database files as a substitute for migrations.
