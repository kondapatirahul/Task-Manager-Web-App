/* Read-only operational data quality report with filters and CSV export. */
(() => {
  "use strict";
  const root = document.getElementById("ops-data-quality");
  if (!root) return;
  const byId = (id) => document.getElementById(id);
  const state = {modules:[], findings:[], filtered:[]};
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  async function load() {
    const button = byId("dq-refresh");
    button.disabled = true;
    byId("dq-status").textContent = "Scanning records…";
    try {
      const response = await fetch("/api/operations/analytics/data-quality", {credentials:"same-origin",cache:"no-store",headers:{"Accept":"application/json"}});
      const payload = await response.json();
      if (!response.ok || payload.ok === false) throw new Error(payload.error || "Quality report failed.");
      state.modules = payload.data.modules || [];
      state.findings = payload.data.findings || [];
      byId("dq-findings").textContent = Number(payload.data.total_findings || 0).toLocaleString();
      byId("dq-modules").textContent = String(state.modules.length);
      byId("dq-records").textContent = state.modules.reduce((sum,item)=>sum+item.records_scanned,0).toLocaleString();
      byId("dq-affected").textContent = String(state.modules.filter((item)=>item.finding_count>0).length);
      byId("dq-status").textContent = `Report completed · ${new Date().toLocaleTimeString()}`;
      renderModules();
      renderFindings();
    } catch (error) {
      byId("dq-status").textContent = "Report failed";
      const toast = byId("dq-toast"); toast.textContent = error.message; toast.classList.add("show","error");
    } finally {button.disabled = false;}
  }
  function renderModules() {
    const sorted = [...state.modules].sort((a,b)=>b.finding_count-a.finding_count);
    byId("dq-modules-rows").innerHTML = sorted.map((item)=>`<tr><td><strong>${esc(item.title)}</strong><div class="ops-record-key">${esc(item.module)}</div></td><td>${item.records_scanned}</td><td><span class="ops-badge ${item.finding_count?"priority-high":"status-approved"}">${item.finding_count}</span></td><td>${(item.top_fields||[]).slice(0,4).map((field)=>`${esc(field.field)} (${field.count})`).join("<br>")||"No findings"}</td><td><a class="ops-button small" href="/operations/${encodeURIComponent(item.module)}">Open</a></td></tr>`).join("") || '<tr><td colspan="5">No operational modules found.</td></tr>';
  }
  function renderFindings() {
    const query = byId("dq-search").value.trim().toLowerCase();
    const module = byId("dq-module-filter").value;
    state.filtered = state.findings.filter((item) => (!module || item.module===module) &&
      (!query || [item.module,item.record_key,item.title,item.field,item.message].some((value)=>String(value||"").toLowerCase().includes(query))));
    byId("dq-visible-count").textContent = `${state.filtered.length} shown`;
    byId("dq-finding-rows").innerHTML = state.filtered.slice(0,500).map((item)=>`<tr><td>${esc(item.module)}</td><td><strong>${esc(item.record_key)}</strong><div class="ops-record-key">${esc(item.title)}</div></td><td><span class="ops-badge">${esc(item.status)}</span></td><td><code>${esc(item.field)}</code></td><td>${esc(item.message)}</td></tr>`).join("") || '<tr><td colspan="5"><div class="ops-empty"><strong>No matching findings</strong><p>Run the report or change filters to inspect other records.</p></div></td></tr>';
  }
  byId("dq-refresh")?.addEventListener("click",load);
  byId("dq-search")?.addEventListener("input",renderFindings);
  byId("dq-module-filter")?.addEventListener("change",renderFindings);
  load();
})();
