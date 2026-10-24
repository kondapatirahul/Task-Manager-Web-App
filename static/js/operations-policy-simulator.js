/* Read-only scenario analysis for operational SLA thresholds. */
(() => {
  "use strict";
  const root=document.getElementById("ops-policy-simulator");
  if(!root)return;
  const byId=(id)=>document.getElementById(id);
  const esc=(v)=>String(v??"").replace(/[&<>"']/g,(c)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  function number(id){return Number(byId(id).textContent.replaceAll(",",""))||0;}
  async function run(){
    const button=byId("sim-run");
    const target=Number(byId("sim-target").value);
    if(!Number.isInteger(target)||target<0||target>525600){toast("Target must be a whole number between 0 and 525600.",true);return;}
    const params=new URLSearchParams({target_minutes:String(target),event_type:byId("sim-event-type").value});
    if(byId("sim-module").value)params.set("module",byId("sim-module").value);
    button.disabled=true;
    try{
      const response=await fetch(`/api/operations/analytics/policy-simulation?${params}`,{credentials:"same-origin",cache:"no-store",headers:{"Accept":"application/json"}});
      const payload=await response.json();
      if(!response.ok||payload.ok===false)throw new Error(payload.error||"Simulation failed.");
      const data=payload.data;
      byId("sim-samples").textContent=Number(data.sample_count).toLocaleString();
      byId("sim-within").textContent=Number(data.within_target).toLocaleString();
      byId("sim-outside").textContent=Number(data.outside_target).toLocaleString();
      byId("sim-compliance").textContent=data.compliance_percent===null?"—":`${data.compliance_percent}%`;
      byId("sim-target-label").textContent=`${data.target_minutes} minutes`;
      byId("sim-median").textContent=data.median_elapsed_minutes===null?"—":`${data.median_elapsed_minutes} minutes`;
      byId("sim-p90").textContent=data.p90_elapsed_minutes===null?"—":`${data.p90_elapsed_minutes} minutes`;
      byId("sim-note").textContent=byId("sim-context").value.trim()||"No note provided.";
      const rows=data.by_module||[];
      byId("sim-module-results").innerHTML=rows.map((item)=>{
        const total=item.samples||0;
        const percent=total?Math.round(item.within_target/total*100):0;
        return `<div class="ops-module-analytic"><div class="ops-module-analytic-top"><strong>${esc(item.title)}</strong><span>${percent}% within target</span></div><div class="ops-progress ${percent<70?"warning":""}"><span style="width:${percent}%"></span></div><div class="ops-module-analytic-foot"><span>${item.within_target} within</span><span>${item.outside_target} outside</span></div></div>`;
      }).join("")||'<p class="ops-muted">No elapsed-time samples match this scope. Record SLA events before using the simulator.</p>';
      toast("Scenario simulation completed.");
    }catch(error){toast(error.message,true);}
    finally{button.disabled=false;}
  }
  function toast(message,error=false){const el=byId("sim-toast");el.textContent=message;el.classList.toggle("error",error);el.classList.add("show");clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.classList.remove("show"),3500);}
  byId("sim-run")?.addEventListener("click",run);
  byId("sim-module")?.addEventListener("change",run);
  byId("sim-event-type")?.addEventListener("change",run);
  byId("sim-target")?.addEventListener("keydown",(event)=>{if(event.key==="Enter")run();});
  run();
})();
