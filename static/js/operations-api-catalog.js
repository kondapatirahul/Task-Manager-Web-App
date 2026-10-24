/* Searchable API route catalog and endpoint-path copying. */
(() => {
  "use strict";
  const root=document.getElementById("ops-api-catalog");
  if(!root)return;
  const byId=(id)=>document.getElementById(id);
  const rows=[...root.querySelectorAll("#api-catalog-rows tr")];
  function filter(){
    const query=byId("api-catalog-search").value.trim().toLowerCase();
    const method=byId("api-catalog-method").value;
    let visible=0,read=0,write=0;
    rows.forEach((row)=>{
      const matches=(!query||row.dataset.apiSearch.toLowerCase().includes(query))&&(!method||row.dataset.apiMethod===method);
      row.hidden=!matches;
      if(matches){visible+=1;if(row.dataset.apiMethod==="GET")read+=1;else write+=1;}
    });
    byId("api-catalog-visible").textContent=String(visible);
    byId("api-catalog-read").textContent=String(read);
    byId("api-catalog-write").textContent=String(write);
    byId("api-catalog-count").textContent=`${visible} endpoint(s)`;
  }
  async function copy(value){
    try{
      await navigator.clipboard.writeText(value);
      byId("api-catalog-toast").textContent=`Copied ${value}`;
    }catch(_error){
      const textarea=document.createElement("textarea");textarea.value=value;textarea.setAttribute("readonly","");textarea.style.position="fixed";textarea.style.opacity="0";document.body.appendChild(textarea);textarea.select();
      const copied=document.execCommand("copy");textarea.remove();
      byId("api-catalog-toast").textContent=copied?`Copied ${value}`:"Copy unavailable; select the endpoint text manually.";
    }
    byId("api-catalog-toast").classList.add("show");
    clearTimeout(copy.timer);copy.timer=setTimeout(()=>byId("api-catalog-toast").classList.remove("show"),2800);
  }
  byId("api-catalog-search")?.addEventListener("input",filter);
  byId("api-catalog-method")?.addEventListener("change",filter);
  byId("api-catalog-reset")?.addEventListener("click",()=>{byId("api-catalog-search").value="";byId("api-catalog-method").value="";filter();});
  byId("api-catalog-rows")?.addEventListener("click",(event)=>{const button=event.target.closest("[data-copy-endpoint]");if(button)copy(button.dataset.copyEndpoint);});
  byId("api-copy-curl")?.addEventListener("click",()=>{
    const token=document.querySelector('meta[name="csrf-token"]')?.content||"REPLACE_WITH_CSRF_TOKEN";
    const body={title:"Public API elevated error rate",summary:"Errors increased after deployment.",priority:"high",service:"Public API",environment:"production",impact:"high",urgency:"high",reported_by:"Monitoring"};
    const command=`curl -X POST "${window.location.origin}/api/operations/incidents" \\\n  -H "Content-Type: application/json" \\\n  -H "X-CSRFToken: ${token}" \\\n  -H "Accept: application/json" \\\n  --data '${JSON.stringify(body)}'`;
    copy(command);
  });
  filter();
})();
