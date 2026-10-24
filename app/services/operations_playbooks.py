"""Operational runbooks, evidence standards, and escalation guidance.

These playbooks are defaults, not substitutes for an organization's approved policy.
They provide consistent, actionable checklists for operational records.
"""
from copy import deepcopy

PLAYBOOKS = {
    "incidents": {
        "title": "Incident response runbook",
        "objective": "Restore service safely, reduce customer impact, and preserve a clear timeline.",
        "roles": ["Incident commander", "Technical lead", "Communications lead", "Service owner"],
        "phases": [
            {"name": "Detect and declare", "actions": ["Confirm user or monitoring signal", "Record detection time and affected service", "Estimate impact and urgency", "Assign incident commander for high or critical events"]},
            {"name": "Triage and contain", "actions": ["Identify scope and affected regions", "Capture a known-good baseline", "Choose a reversible mitigation", "Communicate status and next update time"]},
            {"name": "Resolve and validate", "actions": ["Verify recovery using service indicators", "Confirm customer-facing workflows", "Record root cause and corrective actions", "Keep incident open if monitoring is unstable"]},
            {"name": "Learn and prevent", "actions": ["Write a blameless timeline", "Identify detection and response gaps", "Assign preventive actions with owners", "Share the post-incident review with stakeholders"]},
        ],
        "evidence": ["Detection timestamp", "Impact statement", "Mitigation record", "Recovery validation", "Root-cause notes"],
        "escalation": {"critical": "Page incident commander immediately and open a response bridge.", "high": "Notify service owner and team lead; agree next update within 30 minutes.", "medium": "Assign a triage owner and update the record during the current shift.", "low": "Track in queue and reassess if impact grows."},
        "kpis": ["Time to acknowledge", "Time to mitigate", "Time to recover", "Repeat incident rate"],
    },
    "changes": {
        "title": "Change control runbook",
        "objective": "Make changes with explicit risk ownership, tested rollback, and auditable approvals.",
        "roles": ["Requester", "Service owner", "Change approver", "Implementer", "Verifier"],
        "phases": [
            {"name": "Request", "actions": ["Describe the change and business reason", "Identify impacted services and users", "Define implementation and rollback plans", "Propose a maintenance window"]},
            {"name": "Assess", "actions": ["Rate impact, likelihood, and blast radius", "Check dependencies and freeze windows", "Confirm test plan and evidence", "Determine required approvers"]},
            {"name": "Authorize", "actions": ["Obtain approvals before implementation", "Confirm communication and support coverage", "Verify rollback owner and trigger criteria", "Record the approved window"]},
            {"name": "Implement and review", "actions": ["Follow the approved steps", "Capture start, finish, and deviations", "Verify service health", "Close with outcome and follow-up actions"]},
        ],
        "evidence": ["Implementation plan", "Rollback plan", "Test evidence", "Approver decisions", "Post-change verification"],
        "escalation": {"critical": "Require senior review and explicit rollback readiness.", "high": "Require service-owner approval and a documented impact analysis.", "medium": "Use standard review and verify tests before scheduling.", "low": "Use the approved standard-change catalogue where applicable."},
        "kpis": ["Change success rate", "Emergency change rate", "Rollback rate", "Change-caused incidents"],
    },
    "quality": {
        "title": "Quality assurance runbook",
        "objective": "Make test results reproducible and defects actionable across environments.",
        "roles": ["Test author", "Test executor", "Quality lead", "Defect owner"],
        "phases": [
            {"name": "Design", "actions": ["State the requirement and test objective", "Define preconditions and test data", "Write deterministic steps", "Describe observable expected results"]},
            {"name": "Prepare", "actions": ["Select environment and build version", "Confirm access and dependencies", "Check test data privacy", "Record any known environment limitation"]},
            {"name": "Execute", "actions": ["Capture actual result for each run", "Attach logs or screenshots", "Link failed tests to defects", "Mark blocked tests with the dependency"]},
            {"name": "Report", "actions": ["Summarize pass, fail, blocked, and skipped counts", "Review coverage gaps", "Retest fixes and regression paths", "Archive evidence for the release"]},
        ],
        "evidence": ["Requirement reference", "Reproducible steps", "Build identifier", "Execution result", "Defect or evidence link"],
        "escalation": {"critical": "Stop release recommendation when critical test failures remain.", "high": "Notify quality lead and release manager for failed regression coverage.", "medium": "Assign defects and agree retest dates.", "low": "Record technical debt and test automation opportunities."},
        "kpis": ["Pass rate", "Defect escape rate", "Flaky test rate", "Requirement coverage"],
    },
    "capacity": {
        "title": "Capacity planning runbook",
        "objective": "Align committed demand with realistic availability, skills, and contingency.",
        "roles": ["Team lead", "Resource planner", "Project owner", "Delivery manager"],
        "phases": [
            {"name": "Forecast demand", "actions": ["List committed deliverables and dates", "Estimate effort by skill and role", "Include support and operational load", "Record assumptions and confidence"]},
            {"name": "Calculate supply", "actions": ["Subtract leave, holidays, and non-project work", "Use net available hours", "Check critical skill availability", "Avoid assuming 100 percent productive time"]},
            {"name": "Resolve constraints", "actions": ["Identify overload and single points of failure", "Negotiate scope or sequencing", "Propose temporary capacity or training", "Record decisions and residual risks"]},
            {"name": "Review forecast", "actions": ["Compare planned and actual demand", "Refresh when scope changes", "Track utilization trend", "Publish the next planning horizon"]},
        ],
        "evidence": ["Planning period", "Available hours", "Demand estimate", "Skill assumptions", "Mitigation decision"],
        "escalation": {"critical": "Escalate committed delivery at risk to delivery leadership.", "high": "Agree re-prioritization before accepting new work.", "medium": "Review capacity in the next team planning session.", "low": "Track spare capacity for maintenance and improvement work."},
        "kpis": ["Utilization", "Forecast variance", "Unplanned work share", "Delivery predictability"],
    },
    "lifecycle": {
        "title": "Employee lifecycle runbook",
        "objective": "Coordinate employee changes consistently while protecting identity and access.",
        "roles": ["Employee manager", "HR partner", "IT service owner", "Facilities or equipment owner"],
        "phases": [
            {"name": "Initiate", "actions": ["Verify identity and effective date", "Identify manager and HR owner", "Select onboarding, transfer, role change, or offboarding", "Limit notes to necessary employment information"]},
            {"name": "Plan", "actions": ["Assign equipment and training tasks", "Identify systems and groups affected", "Coordinate payroll and directory updates", "Set due dates and accountable owners"]},
            {"name": "Execute", "actions": ["Complete required checklist items", "Verify least-privilege access", "Record equipment handover or return", "Communicate completion to the manager"]},
            {"name": "Close", "actions": ["Confirm all required controls", "Review outstanding access", "Store required records under retention policy", "Close with exceptions documented"]},
        ],
        "evidence": ["Manager confirmation", "Effective date", "Access review", "Equipment handover", "HR completion check"],
        "escalation": {"critical": "Escalate missed offboarding access revocation immediately.", "high": "Escalate start-date blockers that prevent employee readiness.", "medium": "Assign incomplete onboarding tasks to their functional owners.", "low": "Track optional training and employee-experience improvements."},
        "kpis": ["Time to productivity", "Onboarding completion", "Access removal timeliness", "Checklist exception rate"],
    },
    "data-governance": {
        "title": "Data access review runbook",
        "objective": "Grant only necessary access for a documented purpose and a bounded period.",
        "roles": ["Requester", "Data owner", "Privacy reviewer", "Security reviewer", "System administrator"],
        "phases": [
            {"name": "Request", "actions": ["Identify dataset and requester", "Describe specific business purpose", "Choose classification and least privilege", "Set an expiry date"]},
            {"name": "Review", "actions": ["Confirm legal basis and purpose limitation", "Assess data sensitivity and access level", "Check separation-of-duties constraints", "Obtain data-owner and security approval where required"]},
            {"name": "Provision", "actions": ["Use approved identity and group controls", "Record provisioned role and timestamp", "Confirm logging and monitoring", "Notify requester of permitted use"]},
            {"name": "Revalidate or revoke", "actions": ["Review access before expiry", "Renew only with fresh justification", "Revoke access when no longer required", "Record evidence of removal"]},
        ],
        "evidence": ["Business purpose", "Data classification", "Approver decision", "Expiry date", "Provisioning or revocation evidence"],
        "escalation": {"critical": "Pause provisioning for restricted data with unresolved approval gaps.", "high": "Require privacy and security review before granting write or admin access.", "medium": "Obtain data-owner approval and schedule periodic review.", "low": "Keep access read-only and expiry-bound where practical."},
        "kpis": ["Expired access removed", "Review completion rate", "Over-privileged access findings", "Approval lead time"],
    },
    "procurement": {
        "title": "Procurement control runbook",
        "objective": "Make purchasing decisions transparent, justified, budget-aware, and receivable.",
        "roles": ["Requester", "Budget owner", "Procurement reviewer", "Finance approver", "Receiving owner"],
        "phases": [
            {"name": "Request", "actions": ["Describe need and business outcome", "Specify quantity, unit cost, and currency", "Identify supplier and delivery date", "Provide budget code and justification"]},
            {"name": "Review", "actions": ["Check budget availability", "Collect quotes where required", "Review security and license terms for software", "Route according to spend authority"]},
            {"name": "Order", "actions": ["Record purchase-order reference", "Confirm delivery and service acceptance criteria", "Track supplier commitments", "Record changes to price or quantity"]},
            {"name": "Receive and reconcile", "actions": ["Confirm received quantity and quality", "Compare invoice against order", "Resolve variances before close", "Store warranty and contract references"]},
        ],
        "evidence": ["Business justification", "Supplier quote", "Budget approval", "Purchase reference", "Receiving confirmation"],
        "escalation": {"critical": "Escalate urgent supply risk with explicit authority and documented exception.", "high": "Require finance review and competitive quote evidence.", "medium": "Confirm budget owner and purchasing policy.", "low": "Use approved suppliers and standard catalogue items."},
        "kpis": ["Purchase cycle time", "Invoice variance", "Supplier on-time delivery", "Policy exception rate"],
    },
    "baselines": {
        "title": "Portfolio baseline governance",
        "objective": "Keep scope, schedule, and cost commitments controlled and explainable.",
        "roles": ["Project manager", "Portfolio owner", "Finance partner", "Change approver"],
        "phases": [
            {"name": "Establish", "actions": ["Define included and excluded scope", "Set start, finish, and milestones", "Capture cost assumptions and currency", "Define acceptance criteria"]},
            {"name": "Review", "actions": ["Validate dates and estimates", "Confirm dependencies and constraints", "Check funding and resource assumptions", "Obtain project and portfolio sign-off"]},
            {"name": "Control", "actions": ["Compare actuals to approved baseline", "Document variance and forecast impact", "Reference approved change requests", "Avoid overwriting prior baselines"]},
            {"name": "Supersede", "actions": ["Explain why the baseline changes", "Capture before-and-after values", "Obtain approval for the new version", "Retain history for reporting"]},
        ],
        "evidence": ["Approved scope", "Schedule baseline", "Cost estimate", "Assumptions", "Change reference"],
        "escalation": {"critical": "Escalate forecast breach beyond tolerance to portfolio governance.", "high": "Require a recovery plan and approved change reference.", "medium": "Record variance owner and next review date.", "low": "Continue routine monitoring and trend analysis."},
        "kpis": ["Schedule variance", "Cost variance", "Scope change rate", "Forecast accuracy"],
    },
    "releases": {
        "title": "Release readiness runbook",
        "objective": "Deploy with evidence, ownership, observability, and a tested recovery path.",
        "roles": ["Release manager", "QA lead", "Service owner", "Deployment operator", "Incident commander"],
        "phases": [
            {"name": "Plan", "actions": ["Identify version and release scope", "Publish release notes", "Reference approved change record", "Set the deployment window and communication plan"]},
            {"name": "Verify", "actions": ["Confirm test evidence matches release candidate", "Check known defects and compatibility", "Verify rollback or recovery steps", "Confirm monitoring dashboards and alerts"]},
            {"name": "Deploy", "actions": ["Record deployment start and operator", "Follow the selected deployment strategy", "Watch health indicators and smoke tests", "Stop or rollback when guardrails are breached"]},
            {"name": "Stabilize", "actions": ["Verify service health after deployment", "Communicate outcome to stakeholders", "Track incidents and follow-up actions", "Close only after the observation window"]},
        ],
        "evidence": ["Release notes", "Test report", "Change approval", "Rollback plan", "Monitoring result"],
        "escalation": {"critical": "Stop deployment or invoke rollback if critical health guardrails fail.", "high": "Require explicit release-manager approval and on-call coverage.", "medium": "Complete smoke tests and monitor the agreed window.", "low": "Record deployment outcome and cleanup tasks."},
        "kpis": ["Deployment frequency", "Change failure rate", "Mean time to restore", "Release lead time"],
    },
}


def get_playbook(module_key):
    """Return a copy so callers cannot mutate process-wide policy defaults."""
    playbook = PLAYBOOKS.get(module_key)
    return deepcopy(playbook) if playbook else None


def list_playbooks():
    """Return a lightweight index suitable for workspace navigation."""
    return [
        {"key": key, "title": value["title"], "objective": value["objective"],
         "phase_count": len(value["phases"]), "role_count": len(value["roles"]),
         "evidence_count": len(value["evidence"])}
        for key, value in PLAYBOOKS.items()
    ]


def summarize_playbook(playbook):
    """Flatten runbook structure into a compact checklist for UI and exports."""
    if not playbook:
        return {"actions": 0, "evidence": 0, "phases": []}
    phases = []
    action_count = 0
    for phase in playbook["phases"]:
        actions = list(phase.get("actions", []))
        action_count += len(actions)
        phases.append({"name": phase["name"], "actions": actions, "action_count": len(actions)})
    return {"actions": action_count, "evidence": len(playbook.get("evidence", [])), "phases": phases}


def response_sla(module_key, priority):
    """Return default operational response targets; organizations may override them."""
    if module_key == "incidents":
        from app.services.operations_domains.incidents import incident_sla_targets
        return incident_sla_targets(priority)
    if module_key == "changes":
        return {"assessment_minutes": 1440 if priority in {"low", "medium"} else 240,
                "approval_required": True}
    if module_key == "quality":
        return {"triage_minutes": 480 if priority in {"low", "medium"} else 120,
                "critical_failure_blocks_release": True}
    if module_key == "data-governance":
        return {"review_minutes": 2880 if priority in {"low", "medium"} else 480,
                "expiry_required": True}
    if module_key == "procurement":
        return {"review_minutes": 4320 if priority in {"low", "medium"} else 720,
                "spend_controls_required": True}
    if module_key == "releases":
        return {"readiness_review_minutes": 1440 if priority in {"low", "medium"} else 240,
                "rollback_evidence_required": True}
    return {"review_minutes": 2880, "owner_assignment_required": True}


def readiness_checklist(module_key, payload):
    """Return domain required-field completeness with stable field identifiers."""
    from app.services.operations_domains import DOMAIN_POLICIES
    if module_key not in DOMAIN_POLICIES:
        return None
    validator, _ = DOMAIN_POLICIES[module_key]
    normalized, errors = validator(payload or {}, partial=False)
    fields = []
    for key, message in errors.items():
        fields.append({"field": key, "complete": False, "message": message})
    module = __import__("app.services.operations_domains." + module_key.replace("-", "_"),
                        fromlist=["REQUIRED_FIELDS"])
    for key in module.REQUIRED_FIELDS:
        if key not in errors:
            fields.append({"field": key, "complete": True, "message": ""})
    complete = sum(1 for item in fields if item["complete"])
    return {"items": fields, "complete": complete, "total": len(fields),
            "percent": round(complete / len(fields) * 100) if fields else 100,
            "ready": not errors}
