/* Leadership analytics: workload, aging, approvals, and activity feed. */
(() => {
  "use strict";
  const root = document.getElementById("ops-analytics");
  if (!root) return;
  const byId = (id) => document.getElementById(id);
  const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const date = (value) => {
    if (!value) return "—";
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? escape(value) : d.toLocaleDateString();
  };
  const dt = (value) => {
    if (!value) return "—";
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? escape(value) : d.toLocaleString();
  };
  async function get(url) {
    const response = await fetch(url, {credentials:"same-origin",headers:{"Accept":"application/json"},cache:"no-store"});
    const payload = await response.json();
    if (!response.ok || payload.ok === false) throw new Error(payload.error || "Report request failed.");
    return payload.data;
  }
  function metric(id, value) {
    if (byId(id)) byId(id).textContent = Number(value || 0).toLocaleString();
  }
  function renderModules(modules) {
    const target = byId("an-modules");
    if (!modules.length) {target.innerHTML = '<div class="ops-empty"><strong>No records yet</strong><p>Create operational records to populate this report.</p></div>';return;}
    const max = Math.max(...modules.map((m) => m.total), 1);
    target.innerHTML = modules.map((m) => `<div class="ops-module-analytic">
      <div class="ops-module-analytic-top"><a href="/operations/${encodeURIComponent(m.key)}">${escape(m.title)}</a><span>${m.open} open · ${m.overdue} overdue</span></div>
      <div class="ops-progress"><span style="width:${Math.round(m.total/max*100)}%"></span></div>
      <div class="ops-module-analytic-foot"><span>${m.total} total</span><span>${m.total?Math.round(m.open/m.total*100):0}% active</span></div>
    </div>`).join("");
  }
  function renderAging(buckets) {
    const target = byId("an-aging");
    const order = ["0-2 days","3-7 days","8-14 days","15-30 days","31+ days"];
    const max = Math.max(...order.map((key) => buckets[key] || 0), 1);
    target.innerHTML = order.map((key) => `<div class="ops-aging-row"><div><span>${escape(key)}</span><strong>${buckets[key] || 0}</strong></div><div class="ops-progress ${(key==="31+ days")?"warning":""}"><span style="width:${Math.round((buckets[key]||0)/max*100)}%"></span></div></div>`).join("");
  }
  function renderOverdue(items) {
    byId("an-overdue-count").textContent = `${items.length} shown`;
    const target = byId("an-overdue-rows");
    if (!items.length) {target.innerHTML='<tr><td colspan="6"><div class="ops-empty"><strong>No overdue records</strong><p>Active records with past due dates will appear here.</p></div></td></tr>';return;}
    target.innerHTML = items.map((item) => `<tr><td><a class="ops-record-title" href="/operations/${encodeURIComponent(item.module)}">${escape(item.title)}</a><div class="ops-record-key">${escape(item.key)}</div></td><td>${escape(item.module)}</td><td><span class="ops-badge">${escape(item.status)}</span></td><td><span class="ops-badge priority-${escape(item.priority)}">${escape(item.priority)}</span></td><td>${date(item.due_date)}</td><td><strong>${item.days_overdue}</strong></td></tr>`).join("");
  }
  function renderApprovals(data) {
    const target = byId("an-approval-list");
    const items = data.mine || [];
    if (!items.length) {target.innerHTML='<div class="ops-empty"><strong>No approvals assigned to you</strong><p>Approval tasks will appear here when a manager assigns you as an approver.</p></div>';return;}
    target.innerHTML = items.map((item) => `<div class="ops-side-item"><span class="ops-side-dot"></span><div><div class="ops-side-title">${escape(item.stage_key.replaceAll("_"," "))}</div><div class="ops-side-meta">Record #${item.record_id} · assigned ${dt(item.created_at)}</div></div></div>`).join("");
  }
  function renderActivity(items) {
    const target = byId("an-activity");
    if (!items.length) {target.innerHTML='<div class="ops-empty"><strong>No recent activity</strong><p>Changes and comments will appear here.</p></div>';return;}
    target.innerHTML = items.map((item) => `<div class="ops-event"><div class="ops-event-title">${escape(item.event_type.replaceAll("_"," "))} · Record #${item.record_id}</div><div class="ops-event-message">${escape(item.message || "No message")}</div><div class="ops-event-time">User #${item.actor_id} · ${dt(item.created_at)}</div></div>`).join("");
  }
  function renderControls(data) {
    const summary = data.summary || {};
    const target = byId("an-controls-summary");
    const blockedTarget = byId("an-controls-blocked");
    target.innerHTML = `<div class="ops-control-summary-grid">
      <div><span>Control pass rate</span><strong>${summary.control_pass_rate ?? 100}%</strong></div>
      <div><span>Critical failures</span><strong>${summary.critical_failures || 0}</strong></div>
      <div><span>Review-ready records</span><strong>${summary.review_ready_records || 0}</strong></div>
      <div><span>Blocked records</span><strong>${summary.blocked_records || 0}</strong></div>
    </div><div class="ops-section-label">By module</div>${(data.by_module || []).map((item) => `<div class="ops-module-analytic"><div class="ops-module-analytic-top"><a href="/operations/${encodeURIComponent(item.module)}">${escape(item.module)}</a><span>${item.control_pass_rate}% passed</span></div><div class="ops-progress ${item.critical_failures ? "danger" : ""}"><span style="width:${item.control_pass_rate}%"></span></div><div class="ops-module-analytic-foot"><span>${item.critical_failures} critical failure(s)</span><span>${item.overdue_records} overdue</span></div></div>`).join("")}`;
    const blocked = data.blocked_records || [];
    if (!blocked.length) {
      blockedTarget.innerHTML = '<div class="ops-empty"><strong>No critical control blockers</strong><p>Records with unresolved critical controls will be listed here.</p></div>';
      return;
    }
    blockedTarget.innerHTML = blocked.slice(0,10).map((item) => `<div class="ops-event"><div class="ops-event-title">${escape(item.record_key)} · ${escape(item.module)}</div><div class="ops-event-message">${escape(item.critical_failures)} critical control(s) missing · readiness ${escape(item.readiness_percent)}%</div><div class="ops-event-time">${escape(item.status)} · Record ID ${item.record_id}</div></div>`).join("");
  }

  async function load() {
    const button = byId("analytics-refresh");
    button.disabled = true;
    try {
      const [overview, aging, approvals, activity, controls] = await Promise.all([
        get("/api/operations/analytics/overview"),
        get("/api/operations/analytics/aging"),
        get("/api/operations/analytics/approvals"),
        get("/api/operations/analytics/activity?limit=30"),
        get("/api/operations/analytics/controls")
      ]);
      metric("an-total", overview.totals.records);
      metric("an-open", overview.totals.open);
      metric("an-overdue", overview.totals.overdue);
      metric("an-approvals", approvals.summary.pending);
      renderModules(overview.modules || []);
      renderAging(aging.aging_buckets || {});
      renderOverdue(aging.overdue || []);
      renderApprovals(approvals);
      renderActivity(activity.items || []);
      renderControls(controls);
    } catch (error) {
      const toast = byId("an-toast");
      toast.textContent = error.message;
      toast.classList.add("show","error");
    } finally {
      button.disabled = false;
    }
  }
  byId("analytics-refresh")?.addEventListener("click", load);
  byId("analytics-export")?.addEventListener("click", async () => {
    try {
      const overview = await get("/api/operations/analytics/overview");
      const csvRows = [["module","total","open","overdue"], ...(overview.modules || []).map((m) => [m.key,m.total,m.open,m.overdue])];
      const csv = csvRows.map((row) => row.map((cell) => {
        const text = String(cell ?? "");
        const safe = /^[=+\-@\t\r]/.test(text) ? "'" + text : text;
        return `"${safe.replaceAll('"','""')}"`;
      }).join(",")).join("\r\n");
      const url = URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));
      const link = document.createElement("a");
      link.href = url; link.download = "tasknest-operations-summary.csv"; link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      const toast = byId("an-toast"); toast.textContent = error.message; toast.classList.add("show","error");
    }
  });
  load();
})();
