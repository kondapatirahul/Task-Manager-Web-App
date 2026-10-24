/* Timesheet entry and review interface. */
(() => {
  'use strict';
  const $ = (selector) => document.querySelector(selector);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const apiCall = (method, path, body = null) => api(method, path, body).then((response) => response.data);
  const message = (text, type = 'success') => { const node = $('#tt-message'); node.textContent = text; node.className = `tt-message show ${type}`; };
  const fail = (error) => message(error?.message || 'Unable to complete this request.', 'error');
  const loadSummary = async () => {
    const summary = await apiCall('GET', '/time-tracking/summary');
    const minutes = summary.minutes_by_status || {};
    const values = [summary.approved_hours ?? 0, summary.billable_approved_hours ?? 0,
      ((minutes.submitted || 0) / 60).toFixed(2), ((minutes.draft || 0) / 60).toFixed(2)];
    const labels = ['Approved hours', 'Billable hours', 'Submitted hours', 'Draft hours'];
    $('#tt-stats').innerHTML = values.map((value, index) => `<div class="tt-card"><span class="tt-label">${labels[index]}</span><strong class="tt-value">${esc(value)}</strong></div>`).join('');
  };
  const loadEntries = async () => {
    const status = $('#tt-status').value; const query = status ? `?status=${encodeURIComponent(status)}` : '';
    const result = await apiCall('GET', `/time-tracking/entries${query}`); const rows = result.items || [];
    $('#tt-rows').innerHTML = rows.length ? rows.map((entry) => `<tr><td>${esc(entry.work_date)}</td><td>${esc(entry.task_id || '—')}</td><td>${esc(entry.minutes)} <span class="tt-muted">(${esc(entry.hours)}h)</span></td><td>${entry.billable ? 'Yes' : 'No'}</td><td><span class="tt-pill ${esc(entry.status)}">${esc(entry.status)}</span></td><td>${esc(entry.review_note || '—')}</td><td>${entry.status === 'draft' || entry.status === 'rejected' ? `<button class="tt-button" data-submit="${entry.id}">Submit</button>` : ''}${entry.status === 'submitted' ? `<button class="tt-button" data-review="${entry.id}" data-decision="approve">Approve</button> <button class="tt-button" data-review="${entry.id}" data-decision="reject">Reject</button>` : ''}</td></tr>`).join('') : '<tr><td colspan="7" style="padding:22px;text-align:center">No time entries match these filters.</td></tr>';
    $('#tt-rows').querySelectorAll('[data-submit]').forEach((button) => button.addEventListener('click', () => submitEntry(Number(button.dataset.submit))));
    $('#tt-rows').querySelectorAll('[data-review]').forEach((button) => button.addEventListener('click', () => reviewEntry(Number(button.dataset.review), button.dataset.decision)));
  };
  const refresh = async () => { await Promise.all([loadSummary(), loadEntries()]); };
  const submitEntry = async (id) => { try { await apiCall('POST', `/time-tracking/entries/${id}/submit`, {}); message('Time entry submitted for approval.'); await refresh(); } catch (error) { fail(error); } };
  const reviewEntry = async (id, decision) => {
    const note = decision === 'reject' ? window.prompt('Enter a reason for rejection:') : (window.prompt('Optional review note:') || '');
    if (decision === 'reject' && !note?.trim()) { message('A rejection reason is required.', 'error'); return; }
    try { await apiCall('POST', `/time-tracking/entries/${id}/review`, {decision, note: note || ''}); message(`Time entry ${decision === 'approve' ? 'approved' : 'rejected'}.`); await refresh(); }
    catch (error) { fail(error); }
  };
  $('#tt-form').elements.work_date.value = new Date().toISOString().slice(0, 10);
  $('#tt-form').addEventListener('submit', async (event) => {
    event.preventDefault(); const form = event.currentTarget;
    const payload = {work_date: form.elements.work_date.value, minutes: Number(form.elements.minutes.value),
      task_id: form.elements.task_id.value || null, project_id: form.elements.project_id.value || null,
      billable: form.elements.billable.checked, description: form.elements.description.value.trim()};
    try { await apiCall('POST', '/time-tracking/entries', payload); form.reset(); form.elements.work_date.value = new Date().toISOString().slice(0, 10); message('Time entry saved as draft.'); await refresh(); }
    catch (error) { fail(error); }
  });
  $('#tt-refresh').addEventListener('click', () => refresh().catch(fail)); $('#tt-status').addEventListener('change', () => loadEntries().catch(fail));
  refresh().catch(fail);
})();
