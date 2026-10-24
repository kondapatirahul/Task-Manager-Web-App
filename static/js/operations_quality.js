/* Domain-specific validation and operational guidance: QA Test Management. */
(() => {
  "use strict";
  const config = window.TASKNEST_OPERATIONS;
  if (!config || config.module !== "quality") return;
  const byId = (id) => document.getElementById(id);
  const fieldRules = [('test_type', 'Select test type.'), ('test_environment', 'Select environment.'), ('steps', 'Write reproducible test steps.'), ('expected_result', 'Expected result is required.')];
  function collectDomainValues() {
    const values = {};
    config.fields.forEach((name) => {
      const element = byId(`field-${name}`);
      if (!element) return;
      values[name] = element.type === "checkbox" ? element.checked : element.value.trim();
    });
    return values;
  }
  function validateDomain(data) {
    const fieldErrors = {};
    fieldRules.forEach(([name, message]) => {
      if (data[name] === undefined || data[name] === null || data[name] === "") fieldErrors[name] = message;
    });
    if (data.planned_start && data.planned_end && data.planned_end < data.planned_start) fieldErrors.planned_end = "End date must not precede start date.";
    if (data.period_start && data.period_end && data.period_end < data.period_start) fieldErrors.period_end = "Period end must not precede period start.";
    if (data.quantity !== undefined && data.quantity !== "" && Number(data.quantity) <= 0) fieldErrors.quantity = "Quantity must be greater than zero.";
    if (data.unit_cost !== undefined && data.unit_cost !== "" && Number(data.unit_cost) < 0) fieldErrors.unit_cost = "Unit cost cannot be negative.";
    if (data.planned_hours !== undefined && data.planned_hours !== "" && Number(data.planned_hours) < 0) fieldErrors.planned_hours = "Planned hours cannot be negative.";
    if (data.available_hours !== undefined && data.available_hours !== "" && Number(data.available_hours) < 0) fieldErrors.available_hours = "Available hours cannot be negative.";
    if (data.employee_email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(data.employee_email)) fieldErrors.employee_email = "Enter a valid email address.";
    return fieldErrors;
  }
  function updateDomainPanel() {
    const data = collectDomainValues();
    let advice = "";
    let detail = "";
    const criteria=[data.preconditions,data.steps,data.expected_result,data.test_environment,data.test_type]; const score=Math.round(criteria.filter(Boolean).length/criteria.length*100); advice=data.result==='failed'?'Record actual result and link a reproducible defect.':data.result==='blocked'?'Document blocker, owner, and restart condition.':'Preserve build version and execution evidence.'; detail=`Test design completeness: ${score}%.`;
    const panel = byId("ops-banner");
    if (panel) {
      panel.innerHTML = `<span aria-hidden="true">ⓘ</span><div><strong>QA Test Management helper</strong><br>${escapeHtml(advice)}<br><span style="font-size:11px;opacity:.85">${escapeHtml(detail)}</span></div>`;
      panel.classList.remove("success", "info");
      panel.classList.add("info");
    }
  }
  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[character]));
  }
  function renderLivePreview() {
    const data = collectDomainValues();
    const target = byId("ops-readiness-result");
    if (!target) return;
    const errors = validateDomain(data);
    const count = Object.keys(errors).length;
    target.innerHTML = `<div class="ops-alert ${count ? "info" : "success"}" style="margin-top:12px"><div><strong>${count ? `${count} local check(s) need attention` : "Local checks passed"}</strong><br>${count ? escapeHtml(Object.values(errors).slice(0, 3).join(" ")) : "Server-side rules will validate again when you save."}</div></div>`;
  }
  window.TaskNestDomainBeforeSave = (data) => {
    const fieldErrors = validateDomain(data);
    if (Object.keys(fieldErrors).length) return {ok: false, message: "Complete the domain-specific fields.", fields: fieldErrors};
    return {ok: true};
  };
  window.TaskNestDomainTools = {
    collect: collectDomainValues,
    validate: validateDomain,
    refresh: updateDomainPanel,
    preview: renderLivePreview
  };
  document.addEventListener("DOMContentLoaded", () => {
    config.fields.forEach((name) => {
      const element = byId(`field-${name}`);
      if (element) {
        element.addEventListener("input", updateDomainPanel);
        element.addEventListener("change", updateDomainPanel);
      }
    });
    byId("ops-readiness")?.addEventListener("click", renderLivePreview);
    updateDomainPanel();
  });
})();
