/* SLA event analytics based on explicitly recorded clock events. */
(() => {
  "use strict";
  const root=document.getElementById("ops-sla-report");
  if(!root)return;
  const byId=(id)=>document.getElementById(id);
  const esc=(v)=>String(v??"").replace(/[&<>"']/g,(c)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const when=(v)=>{const d=new Date(v);return v&&!Number.isNaN(d.getTime())?d.toLocaleString():"—";};
  async function load(){
    const button=byId("sla-refresh");button.disabled=true;
    const params=new URLSearchParams();
    if(byId("sla-module").value)params.set("module",byId("sla-module").value);
    if(byId("sla-event-type").value)params.set("event_type",byId("sla-event-type").value);
    try{
      const response=await fetch(`/api/operations/analytics/sla?${params}`,{credentials:"same-origin",cache:"no-store",headers:{"Accept":"application/json"}});
      const payload=await response.json();
      if(!response.ok||payload.ok===false)throw new Error(payload.error||"SLA report failed.");
      const data=payload.data;
      byId("sla-events").textContent=Number(data.events||0).toLocaleString();
      byId("sla-breaches").textContent=Number(data.breaches||0).toLocaleString();
      byId("sla-acknowledged").textContent=Number(data.acknowledged||0).toLocaleString();
      byId("sla-resolved").textContent=Number(data.resolved||0).toLocaleString();
      byId("sla-cap").textContent=`Up to ${data.row_cap} events`;
      byId("sla-module-rows").innerHTML=(data.modules||[]).map((m)=>`<tr><td><a href="/operations/${encodeURIComponent(m.module)}">${esc(m.title)}</a></td><td>${m.events}</td><td>${m.breaches}</td><td>${m.acknowledged}</td><td>${m.resolved}</td><td>${m.within_target}</td><td>${m.elapsed_minutes.toLocaleString()}</td></tr>`).join("")||'<tr><td colspan="7">No SLA events recorded.</td></tr>';
      byId("sla-event-rows").innerHTML=(data.items||[]).map((item)=>`<tr><td><span class="ops-badge ${item.event_type==="breached"?"priority-critical":""}">${esc(item.event_type)}</span></td><td><strong>${esc(item.record_key)}</strong><div class="ops-record-key">${esc(item.record_title)}</div></td><td>${esc(item.module)}</td><td>${item.target_minutes} min</td><td>${item.elapsed_minutes} min</td><td><span class="ops-badge ${item.variance_minutes>0?"priority-high":"status-approved"}">${item.variance_minutes>0?"+":""}${item.variance_minutes} min</span></td><td>${esc(item.reason)}</td><td>${when(item.occurred_at)}</td></tr>`).join("")||'<tr><td colspan="8">No SLA events recorded.</td></tr>';
    }catch(error){const toast=byId("sla-toast");toast.textContent=error.message;toast.classList.add("show","error");}
    finally{button.disabled=false;}
  }
  byId("sla-refresh")?.addEventListener("click",load);
  byId("sla-module")?.addEventListener("change",load);
  byId("sla-event-type")?.addEventListener("change",load);
  load();
})();
