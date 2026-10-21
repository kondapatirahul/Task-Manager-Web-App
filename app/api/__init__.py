"""
API package for Task Manager Web Application.
Exports the tasks blueprint (M4).
"""

from app.api.tasks import tasks_bp, configure_task_api_dependencies

__all__ = ["tasks_bp", "configure_task_api_dependencies"]
