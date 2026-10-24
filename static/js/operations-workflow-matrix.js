/* Filter the generated workflow reference without changing server policy. */
(() => {
  "use strict";
  const root=document.getElementById("ops-workflow-matrix");
  if(!root)return;
  const cards=[...root.querySelectorAll("[data-matrix-module]")];
  const input=document.getElementById("matrix-search");
  const count=document.getElementById("matrix-count");
  function filter() {
    const q=(input.value||"").trim().toLowerCase();
    let visible=0;
    cards.forEach((card)=>{
      const match=!q||card.textContent.toLowerCase().includes(q)||card.dataset.matrixModule.includes(q);
      card.hidden=!match;
      if(match)visible+=1;
    });
    count.textContent=`${visible} workflow(s)`;
  }
  input?.addEventListener("input",filter);
  document.getElementById("matrix-expand")?.addEventListener("click",()=>cards.filter((card)=>!card.hidden).forEach((card)=>{card.open=true;}));
  document.getElementById("matrix-collapse")?.addEventListener("click",()=>cards.forEach((card)=>{card.open=false;}));
  filter();
})();
