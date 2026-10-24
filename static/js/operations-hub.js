/* Cross-workspace operational metrics. */
(() => {
  "use strict";
  const root = document.getElementById("ops-hub");
  if (!root) return;
  const byId = (id) => document.getElementById(id);
  const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
  async function load() {
    const button = byId("ops-hub-refresh");
    if (button) button.disabled = true;
    try {
      const response = await fetch("/api/operations/modules", {
        headers: {"Accept": "application/json"},
        credentials: "same-origin",
        cache: "no-store"
      });
      const payload = await response.json();
      if (!response.ok || payload.ok === false) throw new Error(payload.error || "Could not load metrics.");
      const modules = payload.data?.items || [];
      let total = 0;
      let open = 0;
      let attention = 0;
      modules.forEach((module) => {
        const metrics = module.metrics || {};
        total += metrics.total || 0;
        open += metrics.open || 0;
        const card = root.querySelector(`[data-module="${CSS.escape(module.key)}"]`);
        if (!card) return;
        card.querySelector('[data-metric="total"]').textContent = String(metrics.total || 0);
        card.querySelector('[data-metric="open"]').textContent = String(metrics.open || 0);
        const closed = Math.max(0, (metrics.total || 0) - (metrics.open || 0));
        const percent = metrics.total ? Math.round(closed / metrics.total * 100) : 0;
        card.querySelector("[data-progress]").style.width = `${percent}%`;
        card.querySelector("[data-module-status]").textContent = metrics.total ? `${percent}% terminal or closed` : "No records yet";
        attention += Object.entries(metrics.statuses || {}).reduce((sum, [status, count]) => {
          return sum + (["critical", "blocked", "failed", "rejected"].includes(status) ? count : 0);
        }, 0);
      });
      byId("hub-records").textContent = total.toLocaleString();
      byId("hub-open").textContent = open.toLocaleString();
      byId("hub-attention").textContent = attention.toLocaleString();
    } catch (error) {
      const notice = document.createElement("div");
      notice.className = "ops-alert";
      notice.textContent = error.message;
      root.prepend(notice);
    } finally {
      if (button) button.disabled = false;
    }
  }
  byId("ops-hub-refresh")?.addEventListener("click", load);
  document.addEventListener("DOMContentLoaded", load);
  load();
})();
