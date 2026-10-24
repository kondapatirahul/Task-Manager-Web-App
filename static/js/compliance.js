/* Compliance policy, acknowledgement, and evidence register UI. */
(() => {
  'use strict';
  const $ = (selector) => document.querySelector(selector);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const apiCall = (method, path, body = null) => api(method, path, body).then((response) => response.data);
  const message = (text, type = 'success') => { const node = $('#cp-message'); node.textContent = text; node.className = `cp-message show ${type}`; };
  const fail = (error) => message(error?.message || 'Unable to complete this request.', 'error');
  const renderStats = (data) => {
    const rows = [['Published policies', data.published_policies], ['Draft policies', data.draft_policies], ['Pending acknowledgements', data.pending_acknowledgements], ['Overdue reviews', data.overdue_policy_reviews]];
    $('#cp-stats').innerHTML = rows.map(([label, value]) => `<div class="cp-card"><span class="cp-label">${esc(label)}</span><strong class="cp-value">${esc(value ?? 0)}</strong></div>`).join('');
  };
  const loadPolicies = async () => {
    const params = new URLSearchParams(); if ($('#cp-search').value.trim()) params.set('q', $('#cp-search').value.trim()); if ($('#cp-status').value) params.set('status', $('#cp-status').value);
    const result = await apiCall('GET', `/compliance/policies?${params.toString()}`);
    $('#cp-policies').innerHTML = result.items.length ? result.items.map((policy) => `<tr><td><strong>${esc(policy.policy_key)} · ${esc(policy.title)}</strong><br><span class="cp-muted">${esc(policy.summary)}</span></td><td>v${esc(policy.version)}</td><td>${esc(policy.category)}</td><td><span class="cp-pill ${esc(policy.status)}">${esc(policy.status)}</span></td><td>${esc(policy.effective_date || '—')}</td><td>${esc(policy.review_date || '—')}</td><td>${policy.requires_acknowledgement ? (policy.acknowledged ? '<span class="cp-pill current">Acknowledged</span>' : '<span class="cp-pill expired">Pending</span>') : 'Not required'}</td><td><div style="display:flex;gap:5px;flex-wrap:wrap">${policy.status === 'published' && policy.requires_acknowledgement && !policy.acknowledged ? `<button class="cp-button" data-ack="${policy.id}">Acknowledge</button>` : ''}${policy.status === 'published' ? `<button class="cp-button" data-version="${policy.id}">New version</button>` : ''}${policy.status === 'draft' ? `<button class="cp-button" data-publish="${policy.id}">Publish</button>` : ''}</div></td></tr>`).join('') : '<tr><td colspan="8" style="padding:22px;text-align:center">No policies match these filters.</td></tr>';
    $('#cp-policies').querySelectorAll('[data-ack]').forEach((button) => button.addEventListener('click', () => acknowledge(Number(button.dataset.ack))));
    $('#cp-policies').querySelectorAll('[data-version]').forEach((button) => button.addEventListener('click', () => newVersion(Number(button.dataset.version))));
    $('#cp-policies').querySelectorAll('[data-publish]').forEach((button) => button.addEventListener('click', () => publish(Number(button.dataset.publish))));
  };
  const loadEvidence = async () => {
    const status = $('#cp-evidence-status').value; const query = status ? `?status=${encodeURIComponent(status)}` : '';
    const result = await apiCall('GET', `/compliance/evidence${query}`);
    $('#cp-evidence').innerHTML = result.items.length ? result.items.map((row) => `<tr><td><strong>${esc(row.title)}</strong><br><span class="cp-muted">${esc(row.description)}</span></td><td>${esc(row.evidence_type)}</td><td>${esc(row.policy_id || '—')}</td><td>${esc(row.collected_on)}</td><td>${esc(row.expires_on || 'No expiry')}</td><td><span class="cp-pill ${esc(row.status)}">${esc(row.status)}</span></td><td>${/^https?:\/\//i.test(row.reference_uri || '') ? `<a href="${esc(row.reference_uri)}" rel="noopener noreferrer" target="_blank">Open reference</a>` : (row.reference_uri ? 'Reference recorded' : '—')}</td></tr>`).join('') : '<tr><td colspan="7" style="padding:22px;text-align:center">No evidence records found.</td></tr>';
  };
  const refresh = async () => { const [summary] = await Promise.all([apiCall('GET', '/compliance/summary'), loadPolicies(), loadEvidence()]); renderStats(summary); };
  const renderForm = (title, fields, submitText, submit) => {
    $('#cp-modal-title').textContent = title; const form = $('#cp-form');
    form.innerHTML = fields.map((field) => {
      const full = field.full ? ' full' : '';
      if (field.type === 'select') return `<label class="cp-field${full}">${esc(field.label)}<select name="${esc(field.name)}" ${field.required ? 'required' : ''}>${field.options.map((option) => `<option value="${esc(option.value)}">${esc(option.label)}</option>`).join('')}</select></label>`;
      if (field.type === 'textarea') return `<label class="cp-field${full}">${esc(field.label)}<textarea name="${esc(field.name)}" maxlength="${field.maxlength || 40000}" ${field.required ? 'required' : ''}></textarea></label>`;
      return `<label class="cp-field${full}">${esc(field.label)}<input name="${esc(field.name)}" type="${field.type || 'text'}" maxlength="${field.maxlength || 500}" ${field.required ? 'required' : ''}></label>`;
    }).join('') + `<div class="cp-field full"><button class="cp-button primary" type="submit">${esc(submitText)}</button></div>`;
    form.onsubmit = async (event) => { event.preventDefault(); const data = Object.fromEntries(new FormData(form).entries()); try { await submit(data); $('#cp-modal').classList.remove('open'); } catch (error) { fail(error); } };
    $('#cp-modal').classList.add('open');
  };
  const createPolicy = () => renderForm('Create compliance policy', [
    {name:'policy_key',label:'Policy key',required:true}, {name:'title',label:'Policy title',required:true},
    {name:'category',label:'Category'}, {name:'status',label:'Initial status',type:'select',options:[{value:'draft',label:'Draft'},{value:'published',label:'Published'}]},
    {name:'effective_date',label:'Effective date',type:'date'}, {name:'review_date',label:'Review date',type:'date'},
    {name:'summary',label:'Summary',maxlength:600,full:true}, {name:'body',label:'Policy body',type:'textarea',required:true,full:true},
    {name:'requires_acknowledgement',label:'Acknowledgement required',type:'select',options:[{value:'true',label:'Yes'},{value:'false',label:'No'}]}
  ], 'Save policy', async (data) => { data.requires_acknowledgement = data.requires_acknowledgement !== 'false'; await apiCall('POST','/compliance/policies',data); message('Policy saved.'); await refresh(); });
  const createEvidence = () => renderForm('Register compliance evidence', [
    {name:'title',label:'Evidence title',required:true}, {name:'evidence_type',label:'Evidence type',type:'select',options:['document','screenshot','report','approval','log','certificate','other'].map((v)=>({value:v,label:v}))},
    {name:'policy_id',label:'Policy ID (optional)',type:'number'}, {name:'collected_on',label:'Collected on',type:'date'},
    {name:'expires_on',label:'Expires on',type:'date'}, {name:'status',label:'Status',type:'select',options:['current','expired','superseded','under_review'].map((v)=>({value:v,label:v}))},
    {name:'reference_uri',label:'Evidence reference URL',type:'url',full:true}, {name:'description',label:'Description',type:'textarea',full:true}
  ], 'Register evidence', async (data) => { if (!data.policy_id) data.policy_id = null; await apiCall('POST','/compliance/evidence',data); message('Evidence registered.'); await refresh(); });
  const acknowledge = async (id) => { try { await apiCall('POST', `/compliance/policies/${id}/acknowledge`, {acknowledgement_text:'I have read and understood this policy.'}); message('Policy acknowledgement recorded.'); await refresh(); } catch (error) { fail(error); } };
  const newVersion = async (id) => { if (!window.confirm('Create a new draft version? The currently published version will be retired.')) return; try { await apiCall('POST', `/compliance/policies/${id}/new-version`, {}); message('New policy version created as a draft.'); await refresh(); } catch (error) { fail(error); } };
  const publish = async (id) => { try { await apiCall('PATCH', `/compliance/policies/${id}`, {status:'published'}); message('Policy published.'); await refresh(); } catch (error) { fail(error); } };
  $('#cp-create-policy').addEventListener('click', createPolicy); $('#cp-add-evidence').addEventListener('click', createEvidence); $('#cp-close').addEventListener('click', () => $('#cp-modal').classList.remove('open'));
  $('#cp-refresh').addEventListener('click', () => refresh().catch(fail)); $('#cp-evidence-refresh').addEventListener('click', () => loadEvidence().catch(fail));
  $('#cp-status').addEventListener('change', () => loadPolicies().catch(fail)); $('#cp-evidence-status').addEventListener('change', () => loadEvidence().catch(fail));
  $('#cp-search').addEventListener('keydown', (event) => { if (event.key === 'Enter') loadPolicies().catch(fail); });
  $('#cp-modal').addEventListener('click', (event) => { if (event.target === $('#cp-modal')) $('#cp-modal').classList.remove('open'); });
  refresh().catch(fail);
})();
