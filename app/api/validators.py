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
