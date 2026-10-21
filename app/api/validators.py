"""
Request payload validators for Task REST API (M4).

Follows team schema specifications:
- Statuses: 'pending', 'completed' (pending confirmation with M2)
- Priorities: 'low', 'medium', 'high' (pending confirmation with M2)
- Title: Required non-empty string, max length 150 (pending confirmation with M2)
- Due date: Optional ISO 8601 string (YYYY-MM-DD or ISO timestamp)
- Category ID: Optional positive integer
"""

from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

VALID_STATUSES = {"pending", "completed"}
VALID_PRIORITIES = {"low", "medium", "high"}
VALID_SORT_FIELDS = {"due_date", "priority", "created_at"}
MAX_TITLE_LENGTH = 150


def parse_iso_date(value: Any) -> Tuple[bool, Optional[date], Optional[str]]:
    """
    Parse an ISO date string (YYYY-MM-DD) or ISO datetime string.
    Returns (is_valid, parsed_date, error_message).
    """
    if value is None:
        return True, None, None

    if not isinstance(value, str):
        return False, None, "Due date must be a valid ISO date string (e.g. YYYY-MM-DD)"

    value_str = value.strip()
    if not value_str:
        return True, None, None

    try:
        if len(value_str) == 10:
            parsed = date.fromisoformat(value_str)
            return True, parsed, None
        parsed = datetime.fromisoformat(value_str).date()
        return True, parsed, None
    except ValueError:
        return False, None, "Due date must be a valid ISO date string (e.g. YYYY-MM-DD)"


def validate_task_payload(data: Any, is_partial: bool = False) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Validate task payload for POST / PUT requests.
    Returns (is_valid, error_message, cleaned_data).
    """
    if not isinstance(data, dict):
        return False, "Request body must be a valid JSON object", {}

    cleaned: Dict[str, Any] = {}

    # 1. Title validation
    if "title" in data:
        raw_title = data["title"]
        if not isinstance(raw_title, str):
            return False, "Title must be a string", {}
        title = raw_title.strip()
        if not title:
            return False, "Title is required and cannot be empty", {}
        if len(title) > MAX_TITLE_LENGTH:
            return False, f"Title exceeds maximum length of {MAX_TITLE_LENGTH} characters", {}
        cleaned["title"] = title
    elif not is_partial:
        return False, "Title is required", {}

    # 2. Description validation (optional)
    if "description" in data:
        raw_desc = data["description"]
        if raw_desc is not None and not isinstance(raw_desc, str):
            return False, "Description must be a string or null", {}
        cleaned["description"] = raw_desc.strip() if isinstance(raw_desc, str) else None
    elif not is_partial:
        cleaned["description"] = None

    # 3. Priority validation
    if "priority" in data:
        raw_priority = data["priority"]
        if not isinstance(raw_priority, str):
            return False, f"Priority must be one of: {', '.join(sorted(VALID_PRIORITIES))}", {}
        priority = raw_priority.strip().lower()
        if priority not in VALID_PRIORITIES:
            return False, f"Priority must be one of: {', '.join(sorted(VALID_PRIORITIES))}", {}
        cleaned["priority"] = priority
    elif not is_partial:
        cleaned["priority"] = "medium"

    # 4. Status validation
    if "status" in data:
        raw_status = data["status"]
        if not isinstance(raw_status, str):
            return False, f"Status must be one of: {', '.join(sorted(VALID_STATUSES))}", {}
        status = raw_status.strip().lower()
        if status not in VALID_STATUSES:
            return False, f"Status must be one of: {', '.join(sorted(VALID_STATUSES))}", {}
        cleaned["status"] = status
    elif not is_partial:
        cleaned["status"] = "pending"

    # 5. Due date validation
    if "due_date" in data:
        valid_date, parsed_date, date_err = parse_iso_date(data["due_date"])
        if not valid_date:
            return False, date_err, {}
        cleaned["due_date"] = parsed_date
    elif not is_partial:
        cleaned["due_date"] = None

    # 6. Category ID validation
    if "category_id" in data:
        raw_cat = data["category_id"]
        if raw_cat is not None:
            if not isinstance(raw_cat, int) or isinstance(raw_cat, bool) or raw_cat <= 0:
                return False, "Category ID must be a positive integer or null", {}
            cleaned["category_id"] = raw_cat
        else:
            cleaned["category_id"] = None
    elif not is_partial:
        cleaned["category_id"] = None

    return True, None, cleaned


def validate_task_query_params(params: Any) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Validate query parameters for GET /api/tasks.
    Supported parameters:
    - q: string (optional, search in title and description)
    - status: 'pending' | 'completed' (optional)
    - priority: 'low' | 'medium' | 'high' (optional)
    - category_id: positive integer (optional)
    - due_before: YYYY-MM-DD date string (optional)
    - sort: 'due_date' | 'priority' | 'created_at' (optional)

    Returns:
        (is_valid, error_message, cleaned_params)
    """
    if not hasattr(params, "get"):
        return False, "Query parameters must be a key-value mapping", {}

    cleaned: Dict[str, Any] = {}

    # 1. Search query (q)
    q_val = params.get("q")
    if q_val is not None:
        if not isinstance(q_val, str):
            return False, "Search query 'q' must be a string", {}
        q_cleaned = q_val.strip()
        if q_cleaned:
            cleaned["q"] = q_cleaned

    # 2. Status filter
    status_val = params.get("status")
    if status_val is not None:
        if not isinstance(status_val, str):
            return False, f"Invalid status filter. Allowed values: {', '.join(sorted(VALID_STATUSES))}", {}
        status_clean = status_val.strip().lower()
        if status_clean not in VALID_STATUSES:
            return False, f"Invalid status filter. Allowed values: {', '.join(sorted(VALID_STATUSES))}", {}
        cleaned["status"] = status_clean

    # 3. Priority filter
    priority_val = params.get("priority")
    if priority_val is not None:
        if not isinstance(priority_val, str):
            return False, f"Invalid priority filter. Allowed values: {', '.join(sorted(VALID_PRIORITIES))}", {}
        priority_clean = priority_val.strip().lower()
        if priority_clean not in VALID_PRIORITIES:
            return False, f"Invalid priority filter. Allowed values: {', '.join(sorted(VALID_PRIORITIES))}", {}
        cleaned["priority"] = priority_clean

    # 4. Category ID filter
    cat_val = params.get("category_id")
    if cat_val is not None and str(cat_val).strip() != "":
        if isinstance(cat_val, bool):
            return False, "category_id must be a positive integer", {}
        try:
            cat_int = int(cat_val)
            if cat_int <= 0:
                return False, "category_id must be a positive integer", {}
            cleaned["category_id"] = cat_int
        except (ValueError, TypeError):
            return False, "category_id must be a positive integer", {}

    # 5. Due before filter (strictly YYYY-MM-DD)
    due_val = params.get("due_before")
    if due_val is not None and str(due_val).strip() != "":
        if not isinstance(due_val, str):
            return False, "due_before must be a valid date in YYYY-MM-DD format", {}
        due_str = due_val.strip()
        if len(due_str) != 10:
            return False, "due_before must be a valid date in YYYY-MM-DD format", {}
        try:
            parsed_date = date.fromisoformat(due_str)
            cleaned["due_before"] = parsed_date
        except ValueError:
            return False, "due_before must be a valid date in YYYY-MM-DD format", {}

    # 6. Sort parameter
    sort_val = params.get("sort")
    if sort_val is not None and str(sort_val).strip() != "":
        if not isinstance(sort_val, str):
            return False, f"Invalid sort parameter. Allowed values: {', '.join(sorted(VALID_SORT_FIELDS))}", {}
        sort_clean = sort_val.strip().lower()
        if sort_clean not in VALID_SORT_FIELDS:
            return False, f"Invalid sort parameter. Allowed values: {', '.join(sorted(VALID_SORT_FIELDS))}", {}
        cleaned["sort"] = sort_clean

    return True, None, cleaned
