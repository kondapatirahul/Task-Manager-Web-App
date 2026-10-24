/* Render domain runbooks from the same server-side definitions used by APIs. */
(() => {
  "use strict";
  const root = document.getElementById("ops-playbooks");
  if (!root) return;
  const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  async function getPlaybook(key) {
    const response = await fetch(`/api/operations/${encodeURIComponent(key)}/playbook`, {
      credentials:"same-origin", cache:"no-store", headers:{"Accept":"application/json"}
    });
    const payload = await response.json();
    if (!response.ok || payload.ok === false) throw new Error(payload.error || "Could not load runbook.");
    return payload.data;
  }
  function render(playbook) {
    const card = root.querySelector(`[data-playbook="${CSS.escape(playbook.key)}"]`);
    if (!card) return;
    const target = card.querySelector("[data-playbook-body]");
    const phases = (playbook.phases || []).map((phase) => `<section class="ops-playbook-phase"><h3>${escape(phase.name)}</h3><ul>${phase.actions.map((action) => `<li>${escape(action)}</li>`).join("")}</ul></section>`).join("");
    const roles = (playbook.roles || []).map((role) => `<span class="ops-chip">${escape(role)}</span>`).join("");
    const evidence = (playbook.evidence || []).map((item) => `<span>${escape(item)}</span>`).join("");
    const kpis = (playbook.kpis || []).map((item) => `<li>${escape(item)}</li>`).join("");
    const escalation = Object.entries(playbook.escalation || {}).map(([level, message]) => `<div class="ops-kv"><dt>${escape(level)}</dt><dd>${escape(message)}</dd></div>`).join("");
    const summary = playbook.summary || {};
    target.innerHTML = `<p class="ops-muted">${escape(playbook.objective)}</p><button class="ops-button small" type="button" data-copy-playbook="${escape(playbook.key)}">Copy runbook text</button><div class="ops-section-label">Accountable roles</div><div class="ops-playbook-evidence">${roles}</div><div class="ops-section-label">Phases and actions (${summary.actions || 0})</div>${phases}<div class="ops-section-label">Evidence to preserve</div><div class="ops-playbook-evidence">${evidence}</div><div class="ops-section-label">Escalation guidance</div>${escalation}<div class="ops-section-label">Suggested indicators</div><ul class="ops-guidance-list">${kpis}</ul>`;
  }
  async function loadAll() {
    const cards = [...root.querySelectorAll("[data-playbook]")];
    await Promise.all(cards.map(async (card) => {
      try {render(await getPlaybook(card.dataset.playbook));}
      catch (error) {card.querySelector("[data-playbook-body]").textContent = error.message;}
    }));
  }
  function filterPlaybooks() {
    const query = (document.getElementById("playbook-search")?.value || "").trim().toLowerCase();
    let visible = 0;
    root.querySelectorAll("[data-playbook]").forEach((card) => {
      const matches = !query || card.textContent.toLowerCase().includes(query) || card.dataset.playbook.includes(query);
      card.hidden = !matches;
      if (matches) visible += 1;
    });
    const count = document.getElementById("playbook-filter-count");
    if (count) count.textContent = `${visible} runbook(s)`;
  }
  root.querySelectorAll("[data-playbook]").forEach((card) => {
    card.addEventListener("toggle", async () => {
      if (!card.open || card.dataset.loaded) return;
      card.dataset.loaded = "true";
      try {render(await getPlaybook(card.dataset.playbook));}
      catch (error) {card.querySelector("[data-playbook-body]").textContent = error.message;}
    });
  });
  document.getElementById("playbook-search")?.addEventListener("input", filterPlaybooks);
  document.getElementById("playbook-print")?.addEventListener("click", () => window.print());
  root.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-copy-playbook]");
    if (!button) return;
    const card = button.closest("[data-playbook]");
    const text = card?.innerText || "";
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied";
    } catch (_error) {
      button.textContent = "Select text to copy";
    }
    window.setTimeout(() => {button.textContent = "Copy runbook text";}, 1800);
  });
  document.getElementById("playbook-expand-all")?.addEventListener("click", () => root.querySelectorAll("details").forEach((item) => {item.open = true;}));
  document.getElementById("playbook-collapse-all")?.addEventListener("click", () => root.querySelectorAll("details").forEach((item) => {item.open = false;}));
  loadAll();
})();
