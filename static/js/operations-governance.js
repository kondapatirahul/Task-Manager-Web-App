/* Governance center combines existing control, approval, aging, and audit feeds. */
(() => {
  "use strict";
  const root = document.getElementById("ops-governance");
  if (!root) return;
  const byId = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g,(c)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const when = (v) => {const d=new Date(v);return v&&!Number.isNaN(d.getTime())?d.toLocaleString():"—";};
  async function get(url) {
    const response=await fetch(url,{credentials:"same-origin",cache:"no-store",headers:{"Accept":"application/json"}});
    const payload=await response.json();
    if(!response.ok||payload.ok===false)throw new Error(payload.error||"Governance request failed.");
    return payload.data;
  }
  function metric(id,value){byId(id).textContent=Number(value||0).toLocaleString();}
  function renderControls(data) {
    const modules=data.by_module||[];
    byId("gov-control-modules").innerHTML=modules.map((item)=>`<div class="ops-module-analytic">
      <div class="ops-module-analytic-top"><a href="/operations/${encodeURIComponent(item.module)}">${esc(item.module)}</a><span>${item.control_pass_rate}% passed</span></div>
      <div class="ops-progress ${item.critical_failures?"danger":""}"><span style="width:${item.control_pass_rate}%"></span></div>
      <div class="ops-module-analytic-foot"><span>${item.records} records</span><span>${item.critical_failures} critical failures</span></div>
    </div>`).join("")||'<p class="ops-muted">No records to assess.</p>';
    const blocked=data.blocked_records||[];
    byId("gov-blocked-count").textContent=`${blocked.length} listed`;
    byId("gov-blocked-list").innerHTML=blocked.slice(0,15).map((item)=>`<div class="ops-event"><div class="ops-event-title">${esc(item.record_key)} · ${esc(item.module)}</div><div class="ops-event-message">${item.critical_failures} critical control failure(s), readiness ${item.readiness_percent}%</div><div class="ops-event-time">Status: ${esc(item.status)} · ID ${item.record_id}</div></div>`).join("")||'<p class="ops-muted">No critical control blockers.</p>';
    metric("gov-critical",data.summary?.critical_failures);
    metric("gov-blocked",data.summary?.blocked_records);
  }
  function renderApprovals(data) {
    metric("gov-pending",data.summary?.pending);
    const mine=data.mine||[];
    byId("gov-approval-queue").innerHTML=mine.slice(0,15).map((item)=>`<div class="ops-event"><div class="ops-event-title">${esc(item.stage_key.replaceAll("_"," "))}</div><div class="ops-event-message">Record #${item.record_id} · waiting since ${when(item.created_at)}</div></div>`).join("")||'<p class="ops-muted">No approvals are assigned to your account.</p>';
  }
  function renderOverdue(data) {
    const rows=data.overdue||[];
    metric("gov-overdue",data.overdue_count);
    byId("gov-overdue-count").textContent=`${rows.length} listed`;
    byId("gov-overdue-list").innerHTML=rows.slice(0,15).map((item)=>`<div class="ops-event"><div class="ops-event-title">${esc(item.key)} · ${esc(item.module)}</div><div class="ops-event-message">${esc(item.title)}</div><div class="ops-event-time">${item.days_overdue} day(s) overdue · ${esc(item.priority)} priority</div></div>`).join("")||'<p class="ops-muted">No overdue records.</p>';
  }
  function renderActivity(data) {
    byId("gov-activity").innerHTML=(data.items||[]).map((item)=>`<div class="ops-event"><div class="ops-event-title">${esc(item.event_type.replaceAll("_"," "))} · record #${item.record_id}</div><div class="ops-event-message">${esc(item.message||"No note")}</div><div class="ops-event-time">User #${item.actor_id} · ${when(item.created_at)}</div></div>`).join("")||'<p class="ops-muted">No activity recorded yet.</p>';
  }
  async function load() {
    const button=byId("gov-refresh");button.disabled=true;
    try {
      const [controls,approvals,aging,activity]=await Promise.all([
        get("/api/operations/analytics/controls"),
        get("/api/operations/analytics/approvals"),
        get("/api/operations/analytics/aging"),
        get("/api/operations/analytics/activity?limit=50")
      ]);
      renderControls(controls);renderApprovals(approvals);renderOverdue(aging);renderActivity(activity);
    } catch(error) {
      byId("gov-toast").textContent=error.message;byId("gov-toast").classList.add("show","error");
    } finally {button.disabled=false;}
  }
  byId("gov-refresh")?.addEventListener("click",load);
  load();
})();
