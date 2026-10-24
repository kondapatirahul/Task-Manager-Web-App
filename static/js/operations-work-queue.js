/* Cross-module queue with filtered selection and atomic bulk owner assignment. */
(() => {
  "use strict";
  const root=document.getElementById("ops-work-queue");
  if(!root)return;
  const byId=(id)=>document.getElementById(id);
  const state={page:1,size:50,total:0,pages:0,items:[],selected:new Set(),timer:null};
  const esc=(v)=>String(v??"").replace(/[&<>"']/g,(c)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const fmtDate=(v)=>{if(!v)return "—";const d=new Date(v);return Number.isNaN(d.getTime())?esc(v):d.toLocaleDateString();};
  const token=()=>document.querySelector('meta[name="csrf-token"]')?.content||"";
  async function get(url,options={}) {
    const headers=new Headers(options.headers||{});headers.set("Accept","application/json");
    if(options.body!==undefined){headers.set("Content-Type","application/json");headers.set("X-CSRFToken",token());}
    const response=await fetch(url,{...options,headers,credentials:"same-origin",cache:"no-store",body:options.body===undefined?undefined:JSON.stringify(options.body)});
    const payload=await response.json();
    if(!response.ok||payload.ok===false)throw new Error(payload.error||"Queue request failed.");
    return payload.data;
  }
  function toast(message,error=false){const el=byId("wq-toast");el.textContent=message;el.classList.toggle("error",error);el.classList.add("show");clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.classList.remove("show"),3500);}
  function queryString(){
    const p=new URLSearchParams({page:String(state.page),page_size:String(state.size)});
    const q=byId("wq-search").value.trim();if(q)p.set("q",q);
    if(byId("wq-module").value)p.set("module",byId("wq-module").value);
    if(byId("wq-priority").value)p.set("priority",byId("wq-priority").value);
    if(byId("wq-only-overdue").checked)p.set("overdue","1");
    if(byId("wq-only-unassigned").checked)p.set("unassigned","1");
    return p.toString();
  }
  function render(){
    const tbody=byId("wq-rows");
    if(!state.items.length){tbody.innerHTML='<tr><td colspan="9"><div class="ops-empty"><strong>No work in this view</strong><p>Change filters or check back after new operational records are created.</p></div></td></tr>';}
    else tbody.innerHTML=state.items.map((item)=>`<tr><td><input type="checkbox" data-wq-select="${item.id}" ${state.selected.has(item.id)?"checked":""} aria-label="Select ${esc(item.key)}"></td>
      <td><strong>${esc(item.key)}</strong><div class="ops-record-key">${esc(item.title)}</div></td>
      <td><a href="/operations/${encodeURIComponent(item.module)}">${esc(item.module_title)}</a></td>
      <td><span class="ops-badge">${esc(item.status)}</span></td><td><span class="ops-badge priority-${esc(item.priority)}">${esc(item.priority)}</span></td>
      <td>${item.owner_id?`User #${item.owner_id}`:"Unassigned"}</td><td>${fmtDate(item.due_date)}</td>
      <td>${item.overdue_days?`<span class="ops-badge priority-high">${item.overdue_days}d late</span>`:"—"}</td>
      <td><a class="ops-button small" href="/operations/${encodeURIComponent(item.module)}">Open</a></td></tr>`).join("");
    byId("wq-total").textContent=state.total.toLocaleString();
    byId("wq-selected").textContent=state.selected.size.toLocaleString();
    byId("wq-overdue").textContent=state.items.filter((item)=>item.overdue_days>0).length.toLocaleString();
    byId("wq-unassigned").textContent=state.items.filter((item)=>item.unassigned).length.toLocaleString();
    byId("wq-count-label").textContent=`${state.items.length} on this page`;
    byId("wq-pagination").textContent=`Page ${state.page} of ${Math.max(state.pages,1)} · ${state.total} records`;
    byId("wq-prev").disabled=state.page<=1;byId("wq-next").disabled=state.page>=state.pages;
    const enabled=state.selected.size>0;
    byId("wq-assign").disabled=!enabled||!byId("wq-owner-id").value;
    byId("wq-unassign").disabled=!enabled;
    const checks=[...document.querySelectorAll("[data-wq-select]")];
    byId("wq-select-all").checked=checks.length>0&&checks.every((item)=>item.checked);
    byId("wq-select-all").indeterminate=checks.some((item)=>item.checked)&&!byId("wq-select-all").checked;
  }
  async function load(){
    byId("wq-refresh").disabled=true;
    try{
      const result=await get(`/api/operations/work-queue?${queryString()}`);
      state.items=result.items||[];state.total=result.pagination?.total||0;state.pages=result.pagination?.pages||0;
      render();
    }catch(error){toast(error.message,true);}
    finally{byId("wq-refresh").disabled=false;}
  }
  async function loadSummary() {
    try {
      const data = await get("/api/operations/work-queue/summary");
      byId("wq-global-open").textContent = Number(data.open || 0).toLocaleString();
      byId("wq-global-overdue").textContent = Number(data.overdue || 0).toLocaleString();
      byId("wq-global-unassigned").textContent = Number(data.unassigned || 0).toLocaleString();
      byId("wq-global-critical").textContent = Number(data.critical || 0).toLocaleString();
      byId("wq-summary-updated").textContent = `Updated ${new Date(data.generated_at).toLocaleTimeString()}`;
      byId("wq-module-summary").innerHTML = (data.by_module || []).map((item) =>
        `<span class="ops-chip">${esc(item.title)}: ${item.open || 0} open</span>`
      ).join("");
    } catch (error) {
      byId("wq-summary-updated").textContent = error.message;
    }
  }
  async function assign(ownerId){
    const ids=[...state.selected];
    if(!ids.length)return;
    if(!window.confirm(`${ownerId===null?"Unassign":"Assign"} ${ids.length} selected record(s)?`))return;
    try{
      const result=await get("/api/operations/work-queue/assign",{method:"POST",body:{ids,owner_id:ownerId}});
      state.selected.clear();toast(`${result.updated} record(s) updated.`);await load();
    }catch(error){toast(error.message,true);}
  }
  function filterChanged(){state.page=1;state.selected.clear();load();}
  byId("wq-refresh")?.addEventListener("click",()=>{load();loadSummary();});
  byId("wq-search")?.addEventListener("input",()=>{clearTimeout(state.timer);state.timer=setTimeout(filterChanged,250);});
  ["wq-module","wq-priority","wq-only-overdue","wq-only-unassigned"].forEach((id)=>byId(id)?.addEventListener("change",filterChanged));
  byId("wq-prev")?.addEventListener("click",()=>{state.page=Math.max(1,state.page-1);load();});
  byId("wq-next")?.addEventListener("click",()=>{state.page=Math.min(state.pages,state.page+1);load();});
  byId("wq-owner-id")?.addEventListener("input",render);
  byId("wq-assign")?.addEventListener("click",()=>{const id=Number(byId("wq-owner-id").value);if(Number.isInteger(id)&&id>0)assign(id);else toast("Enter a valid active user ID.",true);});
  byId("wq-suggest-owner")?.addEventListener("click",async()=>{
    try{
      const result=await get("/api/operations/work-queue/recommend-owner");
      if(!result.recommended){toast(result.reason||"No owner recommendation available.",true);return;}
      byId("wq-owner-id").value=String(result.recommended.user_id);
      render();
      toast(`Suggested User #${result.recommended.user_id} with ${result.recommended.open_records} open record(s).`);
    }catch(error){toast(error.message,true);}
  });
  byId("wq-unassign")?.addEventListener("click",()=>assign(null));
  byId("wq-select-all")?.addEventListener("change",(event)=>{state.items.forEach((item)=>event.target.checked?state.selected.add(item.id):state.selected.delete(item.id));render();});
  byId("wq-rows")?.addEventListener("change",(event)=>{const checkbox=event.target.closest("[data-wq-select]");if(!checkbox)return;const id=Number(checkbox.dataset.wqSelect);checkbox.checked?state.selected.add(id):state.selected.delete(id);render();});
  load();
  loadSummary();
})();
