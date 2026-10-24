/* Shared interaction controller for TaskNest operational workspaces.
 * Domain-specific policy remains on the server; client validation is an ergonomic layer.
 */
(() => {
  "use strict";

  const config = window.TASKNEST_OPERATIONS;
  if (!config || !config.module) return;

  const state = {
    page: 1,
    pageSize: 25,
    total: 0,
    pages: 0,
    records: [],
    currentRecord: null,
    loading: false,
    query: "",
    status: "",
    priority: "",
    debounce: null,
    lastFocus: null,
    selectedIds: new Set(),
  };

  const byId = (id) => document.getElementById(id);
  const root = byId("ops-workspace");
  const modulePath = `/api/operations/${encodeURIComponent(config.module)}`;
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');
  const csrfToken = () => csrfMeta ? csrfMeta.content : "";

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[character]);
  }

  function safeDate(value) {
    if (!value) return "—";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return escapeHtml(value);
    return parsed.toLocaleDateString(undefined, {year: "numeric", month: "short", day: "numeric"});
  }

  function safeDateTime(value) {
    if (!value) return "—";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return escapeHtml(value);
    return parsed.toLocaleString(undefined, {dateStyle: "medium", timeStyle: "short"});
  }

  function showToast(message, isError = false) {
    const toast = byId("ops-toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.toggle("error", Boolean(isError));
    toast.classList.add("show");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 3600);
  }

  function setLoading(loading) {
    state.loading = Boolean(loading);
    ["ops-refresh", "ops-create", "ops-export", "ops-save-record", "ops-save-draft"].forEach((id) => {
      const element = byId(id);
      if (element) element.disabled = state.loading;
    });
    if (root) root.setAttribute("aria-busy", String(state.loading));
  }

  async function api(url, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    if (options.body !== undefined) headers.set("Content-Type", "application/json");
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      headers.set("X-CSRFToken", csrfToken());
    }
    const response = await fetch(url, {
      ...options,
      method,
      headers,
      credentials: "same-origin",
      cache: "no-store",
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    const contentType = response.headers.get("content-type") || "";
    let payload;
    if (contentType.includes("application/json")) {
      payload = await response.json();
    } else {
      const text = await response.text();
      payload = {ok: response.ok, error: text || response.statusText};
    }
    if (!response.ok || payload.ok === false) {
      const error = new Error(payload.error || `Request failed (${response.status}).`);
      error.status = response.status;
      error.fields = payload.fields || {};
      throw error;
    }
    return payload.data === undefined ? payload : payload.data;
  }

  function queryString() {
    const params = new URLSearchParams({
      page: String(state.page),
      page_size: String(state.pageSize),
    });
    if (state.query) params.set("q", state.query);
    if (state.status) params.set("status", state.status);
    if (state.priority) params.set("priority", state.priority);
    return params.toString();
  }

  function statusClass(status) {
    return `status-${String(status || "unknown").toLowerCase().replace(/[^a-z0-9_-]/g, "")}`;
  }

  function priorityClass(priority) {
    return `priority-${String(priority || "medium").toLowerCase().replace(/[^a-z0-9_-]/g, "")}`;
  }

  function renderRows(items) {
    const tbody = byId("ops-record-rows");
    if (!tbody) return;
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="7"><div class="ops-empty">
        <strong>No records found</strong><p>Try changing your filters or create a new ${escapeHtml(config.title.toLowerCase())} record.</p>
        <button class="ops-button small primary" type="button" data-action="create">Create record</button>
      </div></td></tr>`;
      return;
    }
    tbody.innerHTML = items.map((record) => `
      <tr data-record-id="${record.id}">
        <td><input type="checkbox" data-select-record="${record.id}" aria-label="Select ${escapeHtml(record.key)}" ${state.selectedIds.has(record.id) ? "checked" : ""}></td>
        <td>
          <a class="ops-record-title" href="#" data-action="open" data-id="${record.id}">${escapeHtml(record.title)}</a>
          <div class="ops-record-key">${escapeHtml(record.key)}</div>
        </td>
        <td><span class="ops-badge ${statusClass(record.status)}">${escapeHtml(String(record.status).replaceAll("_", " "))}</span></td>
        <td><span class="ops-badge ${priorityClass(record.priority)}">${escapeHtml(record.priority)}</span></td>
        <td>${record.owner_id ? `User #${escapeHtml(record.owner_id)}` : '<span class="ops-muted">Unassigned</span>'}</td>
        <td>${safeDate(record.due_date)}</td>
        <td>${safeDateTime(record.updated_at)}</td>
        <td><button class="ops-button small" type="button" data-action="open" data-id="${record.id}" aria-label="Open ${escapeHtml(record.key)}">Open</button></td>
      </tr>`).join("");
    updateSelectionUi();
  }

  function renderStatusSummary(statuses = {}) {
    const target = byId("ops-status-summary");
    if (!target) return;
    const entries = Object.entries(statuses).sort((a, b) => b[1] - a[1]);
    if (!entries.length) {
      target.innerHTML = `<div class="ops-empty"><strong>No status data yet</strong><p>Record counts appear here after records are created.</p></div>`;
      return;
    }
    const max = Math.max(...entries.map((entry) => entry[1]), 1);
    target.innerHTML = entries.map(([status, count]) => `
      <div class="ops-side-item">
        <div style="width:100%">
          <div style="display:flex;justify-content:space-between;gap:12px;margin-bottom:7px">
            <span class="ops-side-title">${escapeHtml(status.replaceAll("_", " "))}</span>
            <strong>${count}</strong>
          </div>
          <div class="ops-progress"><span style="width:${Math.round(count / max * 100)}%"></span></div>
        </div>
      </div>`).join("");
  }

  function renderRecent(items = []) {
    const target = byId("ops-recent");
    if (!target) return;
    if (!items.length) {
      target.innerHTML = `<div class="ops-empty"><strong>Nothing recent</strong><p>Updates will appear after someone edits a record.</p></div>`;
      return;
    }
    target.innerHTML = items.map((record) => `
      <div class="ops-side-item">
        <span class="ops-side-dot"></span>
        <div style="min-width:0">
          <button class="ops-record-title" type="button" data-action="open" data-id="${record.id}" style="border:0;background:none;padding:0;text-align:left">${escapeHtml(record.title)}</button>
          <div class="ops-side-meta">${escapeHtml(record.key)} · ${safeDateTime(record.updated_at)}</div>
        </div>
      </div>`).join("");
  }

  function renderMetrics(metrics = {}, dueSoon = null, overdue = null) {
    const total = metrics.total ?? state.total;
    const statuses = metrics.statuses || {};
    const terminal = new Set(["closed", "completed", "cancelled", "rejected", "released", "retired", "superseded"]);
    const open = metrics.open ?? Object.entries(statuses).reduce((sum, [key, value]) => sum + (terminal.has(key) ? 0 : value), 0);
    if (byId("metric-total")) byId("metric-total").textContent = total.toLocaleString();
    if (byId("metric-open")) byId("metric-open").textContent = open.toLocaleString();
    if (byId("metric-overdue")) byId("metric-overdue").textContent = overdue === null ? "—" : overdue.toLocaleString();
    if (byId("metric-due-soon")) byId("metric-due-soon").textContent = dueSoon === null ? "—" : dueSoon.toLocaleString();
    renderStatusSummary(statuses);
  }

  async function loadRecords() {
    if (state.loading) return;
    setLoading(true);
    try {
      const [pageData, dashboard] = await Promise.all([
        api(`${modulePath}?${queryString()}`),
        api(`${modulePath}/dashboard`).catch(() => null),
      ]);
      state.records = pageData.items || [];
      state.total = pageData.pagination?.total || 0;
      state.pages = pageData.pagination?.pages || 0;
      renderRows(state.records);
      renderMetrics(
        pageData.metrics || dashboard?.metrics || {},
        dashboard?.due_soon ?? null,
        dashboard?.overdue ?? null
      );
      if (dashboard) renderRecent(dashboard.recent || []);
      if (byId("ops-result-count")) byId("ops-result-count").textContent = `${state.total.toLocaleString()} records`;
      if (byId("ops-pagination-label")) {
        byId("ops-pagination-label").textContent = `Page ${state.page} of ${Math.max(state.pages, 1)} · ${state.total} records`;
      }
      if (byId("ops-prev")) byId("ops-prev").disabled = state.page <= 1;
      if (byId("ops-next")) byId("ops-next").disabled = state.page >= state.pages;
    } catch (error) {
      renderRows([]);
      showToast(error.message || "Could not load records.", true);
      if (byId("ops-record-rows")) {
        byId("ops-record-rows").innerHTML = `<tr><td colspan="8"><div class="ops-empty"><strong>Unable to load records</strong><p>${escapeHtml(error.message)}</p><button class="ops-button small" type="button" data-action="refresh">Try again</button></div></td></tr>`;
      }
    } finally {
      setLoading(false);
    }
  }

  async function loadDashboard() {
    try {
      const data = await api(`${modulePath}/dashboard`);
      renderMetrics(data.metrics || {}, data.due_soon, data.overdue);
      renderRecent(data.recent || []);
    } catch (error) {
      console.warn("Operational dashboard unavailable:", error.message);
    }
  }

  function fieldValue(field) {
    const element = byId(`field-${field}`);
    if (!element) return undefined;
    if (element.type === "checkbox") return element.checked;
    const value = element.value;
    if (element.type === "number" && value !== "") return Number(value);
    return value === "" ? null : value;
  }

  function collectForm() {
    const data = {
      title: byId("field-title")?.value.trim() || "",
      priority: byId("field-priority")?.value || "medium",
      summary: byId("field-summary")?.value || "",
      owner_id: byId("field-owner")?.value || null,
      due_date: byId("field-due-date")?.value || null,
    };
    config.fields.forEach((field) => {
      const value = fieldValue(field);
      if (value !== undefined) data[field] = value;
    });
    if (data.owner_id !== null && data.owner_id !== "") data.owner_id = Number(data.owner_id);
    if (data.owner_id === "") data.owner_id = null;
    return data;
  }

  function populateForm(record = null) {
    const fields = record?.fields || {};
    const data = {...fields, ...record};
    const put = (id, value) => {
      const element = byId(id);
      if (!element) return;
      if (element.type === "checkbox") element.checked = Boolean(value);
      else element.value = value ?? "";
    };
    put("ops-record-id", record?.id || "");
    put("ops-record-version", record?.version || "");
    put("field-title", record?.title || "");
    put("field-priority", record?.priority || "medium");
    put("field-summary", record?.summary || "");
    put("field-owner", record?.owner_id || "");
    put("field-due-date", record?.due_date || "");
    config.fields.forEach((field) => put(`field-${field}`, data[field]));
    if (byId("ops-modal-title")) {
      byId("ops-modal-title").textContent = record ? `Edit ${config.title.toLowerCase()} record` : `Create ${config.title.toLowerCase()} record`;
    }
    clearFormError();
  }

  function openModal(record = null) {
    state.lastFocus = document.activeElement;
    populateForm(record);
    byId("ops-edit-modal")?.classList.add("open");
    document.body.style.overflow = "hidden";
    window.setTimeout(() => byId("field-title")?.focus(), 20);
  }

  function closeModal() {
    byId("ops-edit-modal")?.classList.remove("open");
    document.body.style.overflow = "";
    if (state.lastFocus && typeof state.lastFocus.focus === "function") state.lastFocus.focus();
  }

  function clearFormError() {
    const target = byId("ops-form-error");
    if (target) {
      target.classList.remove("show");
      target.textContent = "";
    }
    document.querySelectorAll("[aria-invalid='true']").forEach((element) => element.removeAttribute("aria-invalid"));
  }

  function showFormError(message, fields = {}) {
    const target = byId("ops-form-error");
    if (!target) return;
    const fieldMessages = Object.entries(fields).map(([key, value]) => `${key.replaceAll("_", " ")}: ${value}`).join(" · ");
    target.textContent = [message, fieldMessages].filter(Boolean).join(" ");
    target.classList.add("show");
    Object.keys(fields).forEach((field) => {
      const element = byId(`field-${field}`);
      if (element) element.setAttribute("aria-invalid", "true");
    });
    target.scrollIntoView({behavior: "smooth", block: "nearest"});
  }

  async function saveRecord(asDraft = false) {
    clearFormError();
    const data = collectForm();
    if (!data.title) {
      showFormError("Title is required.");
      byId("field-title")?.focus();
      return;
    }
    if (typeof window.TaskNestDomainBeforeSave === "function") {
      const result = window.TaskNestDomainBeforeSave(data, {asDraft, record: state.currentRecord});
      if (result && result.ok === false) {
        showFormError(result.message || "Check the domain fields.", result.fields || {});
        return;
      }
    }
    const id = byId("ops-record-id")?.value;
    const version = byId("ops-record-version")?.value;
    if (id && version) data.version = Number(version);
    if (asDraft) data.status = "draft";
    setLoading(true);
    try {
      let record;
      if (id) record = await api(`${modulePath}/${id}`, {method: "PATCH", body: data});
      else record = await api(modulePath, {method: "POST", body: data});
      closeModal();
      showToast(id ? "Record updated." : "Record created.");
      state.page = 1;
      await loadRecords();
      if (record?.id && !id) await openRecord(record.id);
    } catch (error) {
      showFormError(error.message, error.fields || {});
    } finally {
      setLoading(false);
    }
  }

  function renderDetailFields(record) {
    const target = byId("ops-detail-fields");
    if (!target) return;
    const fields = record.fields || {};
    const base = [
      ["Reference", record.key], ["Status", record.status], ["Priority", record.priority],
      ["Owner", record.owner_id ? `User #${record.owner_id}` : "Unassigned"],
      ["Due date", safeDate(record.due_date)], ["Created", safeDateTime(record.created_at)],
      ["Last updated", safeDateTime(record.updated_at)], ["Version", record.version],
    ];
    const domain = Object.entries(fields);
    target.innerHTML = `<div class="ops-two-col"><div>${base.map(([key, value]) => `<dl class="ops-kv"><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd></dl>`).join("")}</div><div>${domain.map(([key, value]) => `<dl class="ops-kv"><dt>${escapeHtml(key.replaceAll("_", " "))}</dt><dd>${escapeHtml(typeof value === "object" ? JSON.stringify(value) : value ?? "—")}</dd></dl>`).join("")}</div></div>`;
  }

  function renderEvents(events = []) {
    const target = byId("ops-event-list");
    if (!target) return;
    if (!events.length) {
      target.innerHTML = `<div class="ops-empty"><strong>No activity yet</strong><p>Comments and workflow changes will be recorded here.</p></div>`;
      return;
    }
    target.innerHTML = events.map((event) => `
      <div class="ops-event">
        <div class="ops-event-title">${escapeHtml(event.event_type.replaceAll("_", " "))}${event.from_status ? ` · ${escapeHtml(event.from_status)} → ${escapeHtml(event.to_status)}` : ""}</div>
        <div class="ops-event-message">${escapeHtml(event.message || "No additional message.")}</div>
        <div class="ops-event-time">User #${escapeHtml(event.actor_id)} · ${safeDateTime(event.created_at)}</div>
      </div>`).join("");
  }

  function renderTransitions(record) {
    const target = byId("ops-transition-actions");
    if (!target) return;
    const terminals = new Set(["closed", "completed", "cancelled", "rejected", "released", "retired", "superseded"]);
    const suggestions = {
      draft: ["submitted", "review", "planning", "ready"],
      new: ["triaged", "cancelled"],
      triaged: ["investigating", "mitigated", "cancelled"],
      submitted: ["assessed", "manager_review", "privacy_review", "security_review", "rejected"],
      assessed: ["approved", "rejected"],
      approved: ["scheduled", "active", "ordered", "deploying", "provisioned"],
      scheduled: ["implementing", "cancelled"],
      implementing: ["verified", "released", "rejected"],
      running: ["passed", "failed", "blocked"],
      failed: ["running", "retired"],
      blocked: ["running", "retired"],
      active: ["completed", "reviewed", "superseded"],
      investigating: ["mitigated", "resolved"],
      mitigated: ["investigating", "resolved"],
      resolved: ["closed", "investigating"],
      released: ["closed"],
      rejected: ["draft"],
    };
    let options = suggestions[record.status] || [];
    options = options.filter((status) => config.statuses.includes(status));
    if (terminals.has(record.status)) options = suggestions[record.status] || [];
    target.innerHTML = options.length ? options.map((status) =>
      `<button class="ops-button small" type="button" data-transition="${escapeHtml(status)}">${escapeHtml(status.replaceAll("_", " "))}</button>`
    ).join("") : `<span class="ops-muted">No suggested transitions from this status.</span>`;
  }

  async function openRecord(id) {
    try {
      const record = await api(`${modulePath}/${id}`);
      state.currentRecord = record;
      byId("ops-detail-title").textContent = record.title;
      byId("ops-detail-subtitle").textContent = `${record.key} · ${record.status.replaceAll("_", " ")}`;
      renderDetailFields(record);
      renderEvents(record.events || []);
      renderTransitions(record);
      renderReadinessInline(record);
      byId("ops-detail")?.classList.add("open");
      await loadDetailExtras(record);
      document.body.style.overflow = "hidden";
    } catch (error) {
      showToast(error.message || "Could not open record.", true);
    }
  }

  function renderReadinessInline(record) {
    const target = byId("ops-detail-readiness");
    if (!target) return;
    const fields = record.fields || {};
    const checks = config.fields.map((field) => ({field, complete: fields[field] !== undefined && fields[field] !== null && fields[field] !== ""}));
    const done = checks.filter((item) => item.complete).length;
    const percent = checks.length ? Math.round(done / checks.length * 100) : 100;
    target.innerHTML = `<p class="ops-muted">${done} of ${checks.length} module fields populated</p><div class="ops-progress ${percent < 40 ? "warning" : ""}"><span style="width:${percent}%"></span></div>`;
  }

  async function loadDetailExtras(record) {
    const base = `${modulePath}/${record.id}`;
    const results = await Promise.allSettled([
      api(`${base}/checklist`), api(`${base}/approvals`),
      api(`${base}/links`), api(`${base}/assessment`),
      api(`${base}/sla`), api(`${base}/attachments`)
    ]);
    const [checklistResult, approvalResult, linksResult, assessmentResult, slaResult, attachmentResult] = results;
    if (checklistResult.status === "fulfilled") renderChecklist(checklistResult.value);
    else if (byId("ops-checklist-items")) byId("ops-checklist-items").textContent = checklistResult.reason.message;
    if (approvalResult.status === "fulfilled") renderApprovals(approvalResult.value);
    else if (byId("ops-approval-items")) byId("ops-approval-items").textContent = approvalResult.reason.message;
    if (linksResult.status === "fulfilled") renderLinks(linksResult.value);
    else if (byId("ops-linked-records")) byId("ops-linked-records").textContent = linksResult.reason.message;
    if (assessmentResult.status === "fulfilled") renderAssessment(assessmentResult.value);
    else if (byId("ops-server-assessment")) byId("ops-server-assessment").textContent = assessmentResult.reason.message;
    if (slaResult.status === "fulfilled") renderSlaHistory(slaResult.value);
    else if (byId("ops-sla-events")) byId("ops-sla-events").textContent = slaResult.reason.message;
    if (attachmentResult.status === "fulfilled") renderAttachments(attachmentResult.value);
    else if (byId("ops-attachment-items")) byId("ops-attachment-items").textContent = attachmentResult.reason.message;
  }

  function renderChecklist(data) {
    const target = byId("ops-checklist-items");
    if (!target) return;
    const items = data.items || [];
    if (!items.length) {
      target.innerHTML = '<p class="ops-muted">No saved checklist items. Add the review steps that matter for this record.</p>';
      return;
    }
    target.innerHTML = `<p class="ops-muted">${data.summary?.required_completed || 0} of ${data.summary?.required || 0} required items complete</p>` +
      items.map((item) => `<div class="ops-saved-check">
        <label class="ops-check ${item.completed ? "done" : ""}">
          <input type="checkbox" data-checklist-toggle="${item.id}" ${item.completed ? "checked" : ""}>
          <span>${escapeHtml(item.title)}${item.required ? ' <strong>*</strong>' : ''}</span>
        </label>
        ${item.description ? `<p class="ops-muted">${escapeHtml(item.description)}</p>` : ""}
        ${item.evidence_reference ? `<p class="ops-side-meta">Evidence: ${escapeHtml(item.evidence_reference)}</p>` : ""}
      </div>`).join("");
  }

  function renderApprovals(data) {
    const target = byId("ops-approval-items");
    if (!target) return;
    const items = data.items || [];
    if (!items.length) {
      target.innerHTML = '<p class="ops-muted">No explicit approval assignments.</p>';
      return;
    }
    target.innerHTML = items.map((item) => `<div class="ops-event">
      <div class="ops-event-title">${escapeHtml(item.stage_key.replaceAll("_", " "))} · User #${item.approver_id}</div>
      <div class="ops-event-message">Decision: ${escapeHtml(item.decision)}</div>
      ${item.decision_note ? `<div class="ops-event-message">${escapeHtml(item.decision_note)}</div>` : ""}
      ${item.decision === "pending" ? `<div class="ops-status-bar" style="margin-top:8px"><button class="ops-button small" type="button" data-approval-decision="${item.id}" data-decision="approved">Approve</button><button class="ops-button small danger" type="button" data-approval-decision="${item.id}" data-decision="rejected">Reject</button></div>` : ""}
    </div>`).join("");
  }

  function renderLinks(data) {
    const target = byId("ops-linked-records");
    if (!target) return;
    const items = data.items || [];
    if (!items.length) {
      target.innerHTML = '<p class="ops-muted">No linked records. Link a related incident, change, test, or release for traceability.</p>';
      return;
    }
    target.innerHTML = items.map((item) => {
      const outgoing = item.source_record_id === state.currentRecord?.id;
      const otherKey = outgoing ? item.target_key : item.source_key;
      const otherModule = outgoing ? item.target_module : item.source_module;
      return `<div class="ops-event"><div class="ops-event-title">${escapeHtml(item.link_type.replaceAll("_", " "))}</div>
        <div class="ops-event-message">${escapeHtml(otherKey || "Record")} · ${escapeHtml(otherModule || "module")}</div>
        ${item.note ? `<div class="ops-event-message">${escapeHtml(item.note)}</div>` : ""}
        <div class="ops-event-time">Relationship #${item.id}</div></div>`;
    }).join("");
  }

  function renderAssessment(data) {
    const target = byId("ops-server-assessment");
    const secondary = byId("ops-domain-assessment");
    if (!target && !secondary) return;
    const items = Object.entries(data).filter(([key, value]) =>
      !["record", "assessed_at"].includes(key) && (typeof value !== "object" || value === null)
    );
    const html = `<div class="ops-assessment-grid">${items.map(([key, value]) =>
      `<div class="ops-assessment-item"><span>${escapeHtml(key.replaceAll("_", " "))}</span><strong>${escapeHtml(typeof value === "boolean" ? (value ? "Yes" : "No") : value ?? "—")}</strong></div>`
    ).join("")}</div><p class="ops-side-meta">Calculated ${safeDateTime(data.assessed_at)} by server policy.</p>`;
    if (target) target.innerHTML = html;
    if (secondary) secondary.innerHTML = html;
    const recommendationTarget = byId("ops-domain-recommendations");
    if (recommendationTarget) {
      const recommendations = data.recommendations || [];
      recommendationTarget.innerHTML = recommendations.length ? recommendations.map((item) =>
        `<div class="ops-recommendation"><span class="ops-badge priority-${escapeHtml(item.priority)}">${escapeHtml(item.priority)}</span><div><strong>${escapeHtml(item.action)}</strong><div class="ops-side-meta">${escapeHtml(item.key)}</div></div></div>`
      ).join("") : '<p class="ops-muted">No additional actions suggested by the current domain policy.</p>';
    }
  }

  function renderSlaHistory(data) {
    const target = byId("ops-sla-events");
    if (!target) return;
    const items = data.items || [];
    if (!items.length) {
      target.innerHTML = '<p class="ops-muted">No SLA events have been recorded for this record.</p>';
      return;
    }
    target.innerHTML = items.map((item) => `<div class="ops-event">
      <div class="ops-event-title">${escapeHtml(item.event_type.replaceAll("_", " "))}</div>
      <div class="ops-event-message">Target ${item.target_minutes} min · elapsed ${item.elapsed_minutes} min</div>
      ${item.reason ? `<div class="ops-event-message">${escapeHtml(item.reason)}</div>` : ""}
      <div class="ops-event-time">${safeDateTime(item.occurred_at)} · User #${item.actor_id}</div>
    </div>`).join("");
  }

  function renderAttachments(data) {
    const target = byId("ops-attachment-items");
    if (!target) return;
    const items = data.items || [];
    if (!items.length) {
      target.innerHTML = '<p class="ops-muted">No evidence metadata registered. Only register object keys from a configured private storage adapter.</p>';
      return;
    }
    target.innerHTML = items.map((item) => `<div class="ops-event">
      <div class="ops-event-title">${escapeHtml(item.display_name)}</div>
      <div class="ops-event-message">${escapeHtml(item.evidence_type)} · ${escapeHtml(item.content_type)} · ${Number(item.byte_size || 0).toLocaleString()} bytes</div>
      <div class="ops-event-time">SHA-256 ${escapeHtml(item.sha256_digest || "not supplied")} · ${safeDateTime(item.created_at)}</div>
    </div>`).join("");
  }

  async function createSlaEvent(event) {
    event.preventDefault();
    if (!state.currentRecord) return;
    const body = {
      event_type: byId("ops-sla-event-type").value,
      target_minutes: Number(byId("ops-sla-target").value || 0),
      elapsed_minutes: Number(byId("ops-sla-elapsed").value || 0),
      reason: byId("ops-sla-reason").value.trim()
    };
    try {
      await api(`${modulePath}/${state.currentRecord.id}/sla`, {method: "POST", body});
      byId("ops-sla-reason").value = "";
      await loadDetailExtras(state.currentRecord);
      showToast("SLA event recorded.");
    } catch (error) {
      showToast(error.message, true);
    }
  }

  async function registerAttachment(event) {
    event.preventDefault();
    if (!state.currentRecord) return;
    const body = {
      display_name: byId("ops-attachment-name").value.trim(),
      storage_key: byId("ops-attachment-key").value.trim(),
      evidence_type: byId("ops-attachment-type").value,
      byte_size: Number(byId("ops-attachment-size").value || 0),
      content_type: byId("ops-attachment-content-type").value.trim()
    };
    try {
      await api(`${modulePath}/${state.currentRecord.id}/attachments`, {method: "POST", body});
      byId("ops-attachment-name").value = "";
      byId("ops-attachment-key").value = "";
      byId("ops-attachment-size").value = "0";
      await loadDetailExtras(state.currentRecord);
      showToast("Evidence metadata registered.");
    } catch (error) {
      showToast(error.message, true);
    }
  }

  async function addChecklistItem(event) {
    event.preventDefault();
    if (!state.currentRecord) return;
    const title = byId("ops-checklist-title")?.value.trim();
    if (!title) return;
    try {
      await api(`${modulePath}/${state.currentRecord.id}/checklist`, {
        method: "POST",
        body: {title, required: byId("ops-checklist-required")?.checked ?? true}
      });
      byId("ops-checklist-title").value = "";
      await loadDetailExtras(state.currentRecord);
      showToast("Checklist item added.");
    } catch (error) {
      showToast(error.message, true);
    }
  }

  async function toggleChecklistItem(itemId, completed) {
    if (!state.currentRecord) return;
    try {
      await api(`${modulePath}/${state.currentRecord.id}/checklist/${itemId}`, {
        method: "PATCH", body: {completed}
      });
      await loadDetailExtras(state.currentRecord);
      showToast(completed ? "Checklist item completed." : "Checklist item reopened.");
    } catch (error) {
      showToast(error.message, true);
      await loadDetailExtras(state.currentRecord);
    }
  }

  async function assignApproval(event) {
    event.preventDefault();
    if (!state.currentRecord) return;
    const stage_key = byId("ops-approval-stage")?.value.trim();
    const approver_id = Number(byId("ops-approval-user")?.value);
    try {
      await api(`${modulePath}/${state.currentRecord.id}/approvals`, {
        method: "POST", body: {stage_key, approver_id}
      });
      byId("ops-approval-stage").value = "";
      byId("ops-approval-user").value = "";
      await loadDetailExtras(state.currentRecord);
      showToast("Approval assigned.");
    } catch (error) {
      showToast(error.message, true);
    }
  }

  async function decideApproval(approvalId, decision) {
    if (!state.currentRecord) return;
    let decision_note = "";
    if (decision === "rejected") {
      decision_note = window.prompt("Reason for rejection (required):", "") || "";
      if (!decision_note.trim()) {
        showToast("A rejection reason is required.", true);
        return;
      }
    } else if (!window.confirm("Record approval decision?")) return;
    try {
      await api(`${modulePath}/${state.currentRecord.id}/approvals/${approvalId}/decision`, {
        method: "POST", body: {decision, decision_note}
      });
      await loadDetailExtras(state.currentRecord);
      showToast("Approval decision recorded.");
    } catch (error) {
      showToast(error.message, true);
    }
  }

  async function linkRecord(event) {
    event.preventDefault();
    if (!state.currentRecord) return;
    const target_record_id = Number(byId("ops-link-target")?.value);
    const link_type = byId("ops-link-type")?.value || "relates_to";
    if (!target_record_id) {
      showToast("Enter a target record ID.", true);
      return;
    }
    try {
      await api(`${modulePath}/${state.currentRecord.id}/links`, {
        method: "POST", body: {target_record_id, link_type}
      });
      byId("ops-link-target").value = "";
      await loadDetailExtras(state.currentRecord);
      showToast("Records linked.");
    } catch (error) {
      showToast(error.message, true);
    }
  }

  function closeDetail() {
    byId("ops-detail")?.classList.remove("open");
    document.body.style.overflow = "";
  }

  async function transitionRecord(status) {
    const record = state.currentRecord;
    if (!record) return;
    const confirmation = `Move ${record.key} from ${record.status.replaceAll("_", " ")} to ${status.replaceAll("_", " ")}?`;
    if (!window.confirm(confirmation)) return;
    const comment = window.prompt("Optional transition note (leave blank if none):", "") || "";
    try {
      const updated = await api(`${modulePath}/${record.id}/transition`, {
        method: "POST", body: {status, comment}
      });
      state.currentRecord = updated;
      showToast("Workflow transition saved.");
      await openRecord(record.id);
      await loadRecords();
    } catch (error) {
      showToast(error.message || "Transition was rejected.", true);
    }
  }

  async function postComment(event) {
    event.preventDefault();
    if (!state.currentRecord) return;
    const message = byId("ops-comment-text")?.value.trim();
    if (!message) {
      showToast("Enter a comment first.", true);
      return;
    }
    try {
      await api(`${modulePath}/${state.currentRecord.id}/comments`, {method: "POST", body: {message}});
      byId("ops-comment-text").value = "";
      await openRecord(state.currentRecord.id);
      showToast("Comment added.");
    } catch (error) {
      showToast(error.message, true);
    }
  }

  async function duplicateRecord() {
    if (!state.currentRecord) return;
    try {
      const duplicate = await api(`${modulePath}/${state.currentRecord.id}/duplicate`, {method: "POST", body: {}});
      showToast(`Created ${duplicate.key}.`);
      closeDetail();
      await loadRecords();
      await openRecord(duplicate.id);
    } catch (error) {
      showToast(error.message, true);
    }
  }

  async function archiveRecord() {
    if (!state.currentRecord) return;
    if (!window.confirm(`Archive ${state.currentRecord.key}? It will disappear from the active register.`)) return;
    try {
      await api(`${modulePath}/${state.currentRecord.id}`, {method: "DELETE"});
      closeDetail();
      showToast("Record archived.");
      await loadRecords();
    } catch (error) {
      showToast(error.message, true);
    }
  }

  async function refreshHistory() {
    if (!state.currentRecord) return;
    try {
      const result = await api(`${modulePath}/${state.currentRecord.id}/history?limit=250`);
      renderEvents(result.items || []);
      showToast("Activity history refreshed.");
    } catch (error) {
      showToast(error.message, true);
    }
  }

  async function runReadiness() {
    const target = byId("ops-readiness-result");
    if (target) target.innerHTML = `<div class="ops-skeleton" style="margin-top:12px"></div>`;
    try {
      const result = await api(`${modulePath}/readiness`);
      if (target) {
        target.innerHTML = `<div class="ops-alert ${result.ready === result.total ? "success" : "info"}" style="margin-top:12px"><div><strong>${result.ready} of ${result.total} records ready</strong><br>Records with missing required fields need review before their next transition.</div></div>`;
      }
      showToast("Readiness report complete.");
    } catch (error) {
      if (target) target.textContent = error.message;
      showToast(error.message, true);
    }
  }

  function exportCsv() {
    const link = document.createElement("a");
    link.href = `${modulePath}/export.csv`;
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  function updateSelectionUi() {
    const selected = state.selectedIds.size;
    if (byId("ops-selected-count")) byId("ops-selected-count").textContent = `${selected} selected`;
    if (byId("ops-bulk-apply")) byId("ops-bulk-apply").disabled = selected === 0 || !byId("ops-bulk-status")?.value;
    if (byId("ops-bulk-update")) byId("ops-bulk-update").disabled = selected === 0 ||
      (!byId("ops-bulk-priority")?.value && !byId("ops-bulk-due-date")?.value);
    const checkboxes = [...document.querySelectorAll("[data-select-record]")];
    if (byId("ops-select-all")) {
      byId("ops-select-all").checked = checkboxes.length > 0 && checkboxes.every((item) => item.checked);
      byId("ops-select-all").indeterminate = checkboxes.some((item) => item.checked) && !byId("ops-select-all").checked;
    }
  }

  async function applyBulkTransition() {
    const status = byId("ops-bulk-status")?.value;
    const ids = [...state.selectedIds];
    if (!status || !ids.length) {
      showToast("Select records and a target status first.", true);
      return;
    }
    if (!window.confirm(`Move ${ids.length} record(s) to "${status.replaceAll("_", " ")}"? The server validates every transition before changing any record.`)) return;
    try {
      const result = await api(`${modulePath}/bulk-transition`, {
        method: "POST", body: {ids, status}
      });
      state.selectedIds.clear();
      showToast(`${result.updated} record(s) updated.`);
      await loadRecords();
      await loadDashboard();
    } catch (error) {
      showToast(error.message || "Bulk transition failed; no records were changed.", true);
    }
  }

  async function applyBulkFieldUpdate() {
    const ids = [...state.selectedIds];
    const body = {};
    const priority = byId("ops-bulk-priority")?.value;
    const dueDate = byId("ops-bulk-due-date")?.value;
    if (priority) body.priority = priority;
    if (dueDate) body.due_date = dueDate;
    if (!ids.length || !Object.keys(body).length) {
      showToast("Select records and at least one field to update.", true);
      return;
    }
    if (!window.confirm(`Update ${Object.keys(body).join(" and ")} for ${ids.length} selected record(s)?`)) return;
    try {
      const result = await api(`${modulePath}/bulk-update`, {method: "POST", body: {...body, ids}});
      state.selectedIds.clear();
      if (byId("ops-bulk-priority")) byId("ops-bulk-priority").value = "";
      if (byId("ops-bulk-due-date")) byId("ops-bulk-due-date").value = "";
      showToast(`${result.updated} record(s) updated.`);
      await loadRecords();
      await loadDashboard();
    } catch (error) {
      showToast(error.message || "Bulk update failed; no records were changed.", true);
    }
  }

  async function importCsvFile(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".csv")) {
      showToast("Choose a .csv file.", true);
      return;
    }
    if (file.size > 2_000_000) {
      showToast("CSV must be 2 MB or smaller.", true);
      return;
    }
    const form = new FormData();
    form.append("file", file);
    try {
      const response = await fetch(`${modulePath}/import.csv`, {
        method: "POST",
        body: form,
        credentials: "same-origin",
        cache: "no-store",
        headers: {"X-CSRFToken": csrfToken(), "Accept": "application/json"}
      });
      const payload = await response.json();
      if (!response.ok || payload.ok === false) {
        const rowErrors = (payload.rows || []).slice(0, 5).map((row) => `Row ${row.row}: ${Object.values(row.fields || {}).join(", ")}`).join(" | ");
        throw new Error([payload.error || "Import failed.", rowErrors].filter(Boolean).join(" "));
      }
      showToast(`${payload.data?.created || 0} record(s) imported.`);
      state.page = 1;
      await loadRecords();
      await loadDashboard();
    } catch (error) {
      showToast(error.message || "CSV import failed.", true);
    } finally {
      if (byId("ops-import-file")) byId("ops-import-file").value = "";
    }
  }

  function clearFilters() {
    state.page = 1;
    state.query = "";
    state.status = "";
    state.priority = "";
    if (byId("ops-search")) byId("ops-search").value = "";
    if (byId("ops-status-filter")) byId("ops-status-filter").value = "";
    if (byId("ops-priority-filter")) byId("ops-priority-filter").value = "";
    loadRecords();
  }

  function applyFilters() {
    state.page = 1;
    state.query = byId("ops-search")?.value.trim() || "";
    state.status = byId("ops-status-filter")?.value || "";
    state.priority = byId("ops-priority-filter")?.value || "";
    loadRecords();
  }

  function debounceFilters() {
    window.clearTimeout(state.debounce);
    state.debounce = window.setTimeout(applyFilters, 250);
  }

  async function loadWorkspaceGuidance() {
    const playbookTarget = byId("ops-module-playbook");
    const policyTarget = byId("ops-module-policy");
    const results = await Promise.allSettled([
      api(`${modulePath}/playbook`),
      api(`/api/operations/policies/effective/${encodeURIComponent(config.module)}?priority=medium`)
    ]);
    if (playbookTarget) {
      const result = results[0];
      if (result.status !== "fulfilled") {
        playbookTarget.textContent = result.reason.message;
      } else {
        const data = result.value;
        const phases = (data.phases || []).map((phase) => `<div class="ops-event"><div class="ops-event-title">${escapeHtml(phase.name)}</div><div class="ops-event-message">${escapeHtml(phase.actions.slice(0, 3).join(" · "))}</div></div>`).join("");
        const evidence = (data.evidence || []).map((item) => `<span class="ops-chip">${escapeHtml(item)}</span>`).join("");
        playbookTarget.innerHTML = `<p class="ops-muted">${escapeHtml(data.objective)}</p>${phases}<div class="ops-section-label">Evidence</div><div class="ops-playbook-evidence">${evidence}</div>`;
      }
    }
    if (policyTarget) {
      const result = results[1];
      if (result.status !== "fulfilled") {
        policyTarget.textContent = result.reason.message;
      } else {
        const data = result.value;
        const policy = data.custom_policy;
        const sla = data.default_sla || {};
        const items = policy ? [
          ["Acknowledgement target", `${policy.acknowledgement_minutes} min`],
          ["Resolution target", `${policy.resolution_minutes} min`],
          ["Escalation target", `${policy.escalation_minutes} min`],
          ["Evidence required", policy.evidence_required_for_close ? "Yes" : "No"],
          ["High-risk approval", policy.high_risk_requires_approval ? "Required" : "Not required"],
          ["Policy state", policy.active ? "Active" : "Inactive"]
        ] : Object.entries(sla).map(([key, value]) => [key.replaceAll("_", " "), typeof value === "object" ? JSON.stringify(value) : value]);
        policyTarget.innerHTML = `<p class="ops-muted">${policy ? "Organization-specific policy is active for this module." : "No custom policy found; platform defaults are shown."}</p>${items.map(([key, value]) => `<dl class="ops-kv"><dt>${escapeHtml(key)}</dt><dd>${escapeHtml(value)}</dd></dl>`).join("")}`;
      }
    }
  }

  function bindEvents() {
    byId("ops-create")?.addEventListener("click", () => openModal());
    byId("ops-refresh")?.addEventListener("click", () => {loadRecords(); loadDashboard();});
    byId("ops-export")?.addEventListener("click", exportCsv);
    byId("ops-import-trigger")?.addEventListener("click", () => byId("ops-import-file")?.click());
    byId("ops-import-file")?.addEventListener("change", (event) => importCsvFile(event.target.files?.[0]));
    byId("ops-bulk-status")?.addEventListener("change", updateSelectionUi);
    byId("ops-bulk-apply")?.addEventListener("click", applyBulkTransition);
    byId("ops-bulk-priority")?.addEventListener("change", updateSelectionUi);
    byId("ops-bulk-due-date")?.addEventListener("change", updateSelectionUi);
    byId("ops-bulk-update")?.addEventListener("click", applyBulkFieldUpdate);
    byId("ops-select-all")?.addEventListener("change", (event) => {
      document.querySelectorAll("[data-select-record]").forEach((checkbox) => {
        checkbox.checked = event.target.checked;
        const id = Number(checkbox.dataset.selectRecord);
        if (checkbox.checked) state.selectedIds.add(id); else state.selectedIds.delete(id);
      });
      updateSelectionUi();
    });
    byId("ops-clear-filters")?.addEventListener("click", clearFilters);
    byId("ops-search")?.addEventListener("input", debounceFilters);
    byId("ops-status-filter")?.addEventListener("change", applyFilters);
    byId("ops-priority-filter")?.addEventListener("change", applyFilters);
    byId("ops-prev")?.addEventListener("click", () => {state.page = Math.max(1, state.page - 1); loadRecords();});
    byId("ops-next")?.addEventListener("click", () => {state.page = Math.min(state.pages, state.page + 1); loadRecords();});
    byId("ops-save-record")?.addEventListener("click", (event) => {event.preventDefault(); saveRecord(false);});
    byId("ops-save-draft")?.addEventListener("click", () => saveRecord(true));
    byId("ops-record-form")?.addEventListener("submit", (event) => {event.preventDefault(); saveRecord(false);});
    document.querySelectorAll("[data-close-modal]").forEach((button) => button.addEventListener("click", closeModal));
    byId("ops-edit-modal")?.addEventListener("click", (event) => {if (event.target.id === "ops-edit-modal") closeModal();});
    byId("ops-detail-close")?.addEventListener("click", closeDetail);
    byId("ops-detail")?.addEventListener("click", (event) => {if (event.target.id === "ops-detail") closeDetail();});
    byId("ops-comment-form")?.addEventListener("submit", postComment);
    byId("ops-checklist-form")?.addEventListener("submit", addChecklistItem);
    byId("ops-approval-form")?.addEventListener("submit", assignApproval);
    byId("ops-link-form")?.addEventListener("submit", linkRecord);
    byId("ops-sla-form")?.addEventListener("submit", createSlaEvent);
    byId("ops-attachment-form")?.addEventListener("submit", registerAttachment);
    byId("ops-duplicate")?.addEventListener("click", duplicateRecord);
    byId("ops-archive")?.addEventListener("click", archiveRecord);
    byId("ops-edit-detail")?.addEventListener("click", () => {
      if (state.currentRecord) openModal(state.currentRecord);
    });
    byId("ops-detail-history")?.addEventListener("click", refreshHistory);
    byId("ops-readiness")?.addEventListener("click", runReadiness);
    document.addEventListener("click", (event) => {
      const action = event.target.closest("[data-action]");
      if (action) {
        const name = action.dataset.action;
        if (name === "create") openModal();
        if (name === "refresh") loadRecords();
        if (name === "open") openRecord(Number(action.dataset.id));
      }
      const transition = event.target.closest("[data-transition]");
      if (transition) transitionRecord(transition.dataset.transition);
      const checklistToggle = event.target.closest("[data-checklist-toggle]");
      if (checklistToggle) toggleChecklistItem(Number(checklistToggle.dataset.checklistToggle), checklistToggle.checked);
      const approvalDecision = event.target.closest("[data-approval-decision]");
      if (approvalDecision) decideApproval(Number(approvalDecision.dataset.approvalDecision), approvalDecision.dataset.decision);
      const selectRecord = event.target.closest("[data-select-record]");
      if (selectRecord) {
        const id = Number(selectRecord.dataset.selectRecord);
        if (selectRecord.checked) state.selectedIds.add(id); else state.selectedIds.delete(id);
        updateSelectionUi();
      }
    });
    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        byId("ops-search")?.focus();
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "n") {
        event.preventDefault();
        openModal();
      }
      if (event.key === "Escape") {
        closeModal();
        closeDetail();
      }
    });
  }

  window.TaskNestOperations = {
    api, escapeHtml, showToast, loadRecords, loadDashboard, openModal, openRecord,
    closeModal, closeDetail, collectForm, state, config, modulePath,
  };

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    loadRecords();
    loadDashboard();
    loadWorkspaceGuidance();
  });
})();
