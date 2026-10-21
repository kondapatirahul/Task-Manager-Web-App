"""
Unit tests for app/api/validators.py.
"""

from datetime import date
import unittest

from app.api.validators import parse_iso_date, validate_task_payload


class TestValidators(unittest.TestCase):
    def test_parse_iso_date_valid_ymd(self):
        is_valid, parsed, err = parse_iso_date("2026-10-25")
        self.assertTrue(is_valid)
        self.assertEqual(parsed, date(2026, 10, 25))
        self.assertIsNone(err)

    def test_parse_iso_date_valid_iso_timestamp(self):
        is_valid, parsed, err = parse_iso_date("2026-10-25T14:30:00")
        self.assertTrue(is_valid)
        self.assertEqual(parsed, date(2026, 10, 25))
        self.assertIsNone(err)

    def test_parse_iso_date_none_and_empty(self):
        is_valid, parsed, err = parse_iso_date(None)
        self.assertTrue(is_valid)
        self.assertIsNone(parsed)

        is_valid, parsed, err = parse_iso_date("   ")
        self.assertTrue(is_valid)
        self.assertIsNone(parsed)

    def test_parse_iso_date_invalid(self):
        is_valid, parsed, err = parse_iso_date("not-a-date")
        self.assertFalse(is_valid)
        self.assertIsNone(parsed)
        self.assertIn("valid ISO date string", err)

        is_valid, parsed, err = parse_iso_date(12345)
        self.assertFalse(is_valid)
        self.assertIn("valid ISO date string", err)

    def test_validate_task_payload_valid_full(self):
        data = {
            "title": "Build API",
            "description": "Complete M4 endpoints",
            "priority": "HIGH",
            "status": "PENDING",
            "due_date": "2026-11-01",
            "category_id": 3,
        }
        is_valid, err, cleaned = validate_task_payload(data)
        self.assertTrue(is_valid)
        self.assertIsNone(err)
        self.assertEqual(cleaned["title"], "Build API")
        self.assertEqual(cleaned["description"], "Complete M4 endpoints")
        self.assertEqual(cleaned["priority"], "high")
        self.assertEqual(cleaned["status"], "pending")
        self.assertEqual(cleaned["due_date"], date(2026, 11, 1))
        self.assertEqual(cleaned["category_id"], 3)

    def test_validate_task_payload_defaults(self):
        data = {"title": "Minimal Task"}
        is_valid, err, cleaned = validate_task_payload(data)
        self.assertTrue(is_valid)
        self.assertIsNone(err)
        self.assertEqual(cleaned["priority"], "medium")
        self.assertEqual(cleaned["status"], "pending")
        self.assertIsNone(cleaned["due_date"])
        self.assertIsNone(cleaned["category_id"])
        self.assertIsNone(cleaned["description"])

    def test_validate_task_payload_missing_title(self):
        is_valid, err, _ = validate_task_payload({})
        self.assertFalse(is_valid)
        self.assertEqual(err, "Title is required")

    def test_validate_task_payload_empty_title(self):
        is_valid, err, _ = validate_task_payload({"title": "   "})
        self.assertFalse(is_valid)
        self.assertIn("cannot be empty", err)

    def test_validate_task_payload_title_too_long(self):
        is_valid, err, _ = validate_task_payload({"title": "a" * 151})
        self.assertFalse(is_valid)
        self.assertIn("exceeds maximum length", err)

    def test_validate_task_payload_invalid_priority(self):
        is_valid, err, _ = validate_task_payload({"title": "Task", "priority": "urgent"})
        self.assertFalse(is_valid)
        self.assertIn("Priority must be one of", err)

    def test_validate_task_payload_invalid_status(self):
        is_valid, err, _ = validate_task_payload({"title": "Task", "status": "in_progress"})
        self.assertFalse(is_valid)
        self.assertIn("Status must be one of", err)

    def test_validate_task_payload_invalid_category_id(self):
        for bad_cat in ["five", -1, 0, True, 2.5]:
            is_valid, err, _ = validate_task_payload({"title": "Task", "category_id": bad_cat})
            self.assertFalse(is_valid, f"Expected invalid for {bad_cat}")
            self.assertIn("positive integer or null", err)

    def test_validate_task_payload_non_dict(self):
        is_valid, err, _ = validate_task_payload("a string")
        self.assertFalse(is_valid)
        self.assertIn("must be a valid JSON object", err)


if __name__ == "__main__":
    unittest.main()
