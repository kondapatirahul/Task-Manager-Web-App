"""Domain policies for the TaskNest operational workspaces.

Each domain owns field validation and status transitions. Shared persistence and
HTTP mechanics live elsewhere so the business rules remain independently testable.
"""
from .incidents import validate_incidents, transition_incidents
from .changes import validate_changes, transition_changes
from .quality import validate_quality, transition_quality
from .capacity import validate_capacity, transition_capacity
from .lifecycle import validate_lifecycle, transition_lifecycle
from .data_governance import validate_data_governance, transition_data_governance
from .procurement import validate_procurement, transition_procurement
from .baselines import validate_baselines, transition_baselines
from .releases import validate_releases, transition_releases

DOMAIN_POLICIES = {
    "incidents": (validate_incidents, transition_incidents),
    "changes": (validate_changes, transition_changes),
    "quality": (validate_quality, transition_quality),
    "capacity": (validate_capacity, transition_capacity),
    "lifecycle": (validate_lifecycle, transition_lifecycle),
    "data-governance": (validate_data_governance, transition_data_governance),
    "procurement": (validate_procurement, transition_procurement),
    "baselines": (validate_baselines, transition_baselines),
    "releases": (validate_releases, transition_releases),
}
