/* Administrative policy editor with explicit numeric and role validation. */
(() => {
  "use strict";
  const root = document.getElementById("ops-policies");
  if (!root) return;
  const byId = (id) => document.getElementById(id);
  const modules = window.TASKNEST_POLICY_MODULES || {};
  const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const state = {policies:[], byModule:new Map()};
  async function request(url, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("Accept","application/json");
    if (options.body !== undefined) headers.set("Content-Type","application/json");
    if (options.method && options.method !== "GET") headers.set("X-CSRFToken", token);
    const response = await fetch(url,{...options,headers,credentials:"same-origin",cache:"no-store",body:options.body===undefined?undefined:JSON.stringify(options.body)});
    const payload = await response.json();
    if (!response.ok || payload.ok === false) throw new Error(payload.error || "Request failed.");
    return payload.data;
  }
  function toast(message, error = false) {
    const element = byId("policy-toast");
    element.textContent = message;
    element.classList.toggle("error",error);
    element.classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => element.classList.remove("show"),3500);
  }
  function render() {
    const tbody = byId("policy-rows");
    const keys = Object.keys(modules);
    byId("policy-count").textContent = `${state.policies.length} configured`;
    tbody.innerHTML = keys.map((key) => {
      const module = modules[key];
      const policy = state.byModule.get(key);
      return `<tr><td><strong>${esc(module.title)}</strong><div class="ops-record-key">${esc(key)}</div></td>
        <td>${policy ? policy.acknowledgement_minutes : "Default"}</td>
        <td>${policy ? policy.resolution_minutes : "Default"}</td>
        <td>${policy ? policy.escalation_minutes : "Default"}</td>
        <td>${policy ? (policy.high_risk_requires_approval ? "Required" : "Optional") : "Default"}</td>
        <td><span class="ops-badge ${policy && policy.active ? "status-approved" : ""}">${policy ? (policy.active ? "Active" : "Inactive") : "Not customized"}</span></td>
        <td><button class="ops-button small" type="button" data-edit-policy="${esc(key)}">${policy ? "Edit" : "Configure"}</button></td></tr>`;
    }).join("");
  }
  async function load() {
    const result = await request("/api/operations/policies");
    state.policies = result.items || [];
    state.byModule = new Map(state.policies.map((item) => [item.module_key,item]));
    render();
  }
  function open(key) {
    const policy = state.byModule.get(key);
    byId("policy-module").value = key;
    byId("policy-modal-title").textContent = `Policy · ${modules[key]?.title || key}`;
    byId("policy-ack").value = policy?.acknowledgement_minutes ?? 240;
    byId("policy-resolution").value = policy?.resolution_minutes ?? 4320;
    byId("policy-escalation").value = policy?.escalation_minutes ?? 1440;
    byId("policy-owner-role").value = policy?.default_owner_role ?? "team_lead";
    byId("policy-escalation-role").value = policy?.escalation_role ?? "admin";
    byId("policy-high-risk").checked = policy?.high_risk_requires_approval ?? true;
    byId("policy-evidence").checked = policy?.evidence_required_for_close ?? false;
    byId("policy-active").checked = policy?.active ?? true;
    byId("policy-notes").value = policy?.policy_notes ?? "";
    byId("policy-error").classList.remove("show");
    byId("policy-modal").classList.add("open");
  }
  function close() {byId("policy-modal").classList.remove("open");}
  async function save(event) {
    event.preventDefault();
    const values = ["policy-ack","policy-resolution","policy-escalation"].map((id) => Number(byId(id).value));
    if (values.some((value) => !Number.isInteger(value) || value < 0 || value > 525600)) {
      byId("policy-error").textContent = "Targets must be whole minutes between 0 and 525600.";
      byId("policy-error").classList.add("show");
      return;
    }
    const key = byId("policy-module").value;
    const body = {
      acknowledgement_minutes: values[0], resolution_minutes: values[1], escalation_minutes: values[2],
      default_owner_role: byId("policy-owner-role").value,
      escalation_role: byId("policy-escalation-role").value,
      high_risk_requires_approval: byId("policy-high-risk").checked,
      evidence_required_for_close: byId("policy-evidence").checked,
      active: byId("policy-active").checked,
      policy_notes: byId("policy-notes").value
    };
    byId("policy-save").disabled = true;
    try {
      await request(`/api/operations/policies/${encodeURIComponent(key)}`,{method:"PUT",body});
      close();
      await load();
      toast("Policy saved.");
    } catch (error) {
      byId("policy-error").textContent = error.message;
      byId("policy-error").classList.add("show");
    } finally {
      byId("policy-save").disabled = false;
    }
  }
  tbodyListener();
  function tbodyListener() {
    byId("policy-rows").addEventListener("click",(event) => {
      const button = event.target.closest("[data-edit-policy]");
      if (button) open(button.dataset.editPolicy);
    });
  }
  byId("policy-refresh")?.addEventListener("click",() => load().catch((e) => toast(e.message,true)));
  byId("policy-close")?.addEventListener("click",close);
  byId("policy-cancel")?.addEventListener("click",close);
  byId("policy-modal")?.addEventListener("click",(event) => {if (event.target.id === "policy-modal") close();});
  byId("policy-form")?.addEventListener("submit",save);
  document.addEventListener("keydown",(event) => {if (event.key === "Escape") close();});
  load().catch((error) => toast(error.message,true));
})();
