(() => {
  'use strict';
  const root = document.getElementById('enterprise-console');
  if (!root) return;
  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];
  const csrf = $('meta[name="csrf-token"]')?.content || '';
  const state = { transactions: [], purchases: [], risks: [], objectives: [], assets: [], currentTab: 'finance' };
  const modal = $('#ec-modal');
  const form = $('#ec-form');
  const message = $('#ec-message');
  const money = value => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(Number(value || 0));
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pill = value => `<span class="ec-pill ${escapeHtml(String(value || '').toLowerCase())}">${escapeHtml(String(value || 'unknown').replaceAll('_',' '))}</span>`;
  const showMessage = (text, type = 'success') => { message.textContent = text; message.className = `ec-message show ${type}`; window.setTimeout(() => message.classList.remove('show'), 5000); };
  async function api(path, options = {}) {
    const response = await fetch(path, { credentials: 'same-origin', ...options, headers: {
      'Accept': 'application/json', ...(options.body ? {'Content-Type':'application/json'} : {}),
      ...(options.method && !['GET','HEAD'].includes(options.method.toUpperCase()) ? {'X-CSRFToken':csrf} : {}), ...(options.headers || {})
    }});
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload.data;
  }
  const post = (path, body) => api(path, { method: 'POST', body: JSON.stringify(body) });
  const patch = (path, body) => api(path, { method: 'PATCH', body: JSON.stringify(body) });
  function setStats(id, values) { const node = $(`#${id}`); if (!node) return; node.innerHTML = values.map(([label, value]) => `<div class="ec-stat"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join(''); }
  function emptyRow(colspan, text) { return `<tr><td colspan="${colspan}" class="ec-empty">${escapeHtml(text)}</td></tr>`; }
  function renderFinance() {
    const query = $('#finance-search').value.trim().toLowerCase();
    const status = $('#finance-status').value;
    const rows = state.transactions.filter(t => (!status || t.status === status) && (!query || `${t.merchant} ${t.reference} ${t.description}`.toLowerCase().includes(query)));
    $('#finance-rows').innerHTML = rows.length ? rows.map(t => `<tr><td>${escapeHtml(t.transaction_date || '—')}</td><td>${t.task_id ? `#${t.task_id}` : '—'}</td><td><strong>${escapeHtml(t.merchant || t.reference || 'Expense')}</strong><br><span class="ec-small">${escapeHtml(t.description || '')}</span></td><td>${escapeHtml(t.category)}</td><td>${money(t.amount)}</td><td>${pill(t.status)}</td><td><div class="ec-actions">${t.status === 'submitted' ? `<button class="ec-btn" data-approve-tx="${t.id}">Approve</button><button class="ec-btn danger" data-reject-tx="${t.id}">Reject</button>` : ''}${t.status !== 'void' ? `<button class="ec-btn secondary" data-void-tx="${t.id}">Void</button>` : ''}</div></td></tr>`).join('') : emptyRow(7, 'No transactions match these filters.');
    const purchases = state.purchases;
    $('#purchase-rows').innerHTML = purchases.length ? purchases.map(p => `<tr><td><strong>${escapeHtml(p.title)}</strong><br><span class="ec-small">${escapeHtml(p.justification || '')}</span></td><td>${escapeHtml(p.vendor || '—')}</td><td>${money(p.amount)}</td><td>${escapeHtml((p.created_at || '').slice(0,10))}</td><td>${pill(p.status)}</td><td>${p.status === 'pending' ? `<div class="ec-actions"><button class="ec-btn" data-review-purchase="${p.id}" data-decision="approved">Approve</button><button class="ec-btn danger" data-review-purchase="${p.id}" data-decision="rejected">Reject</button></div>` : '—'}</td></tr>`).join('') : emptyRow(6, 'No purchase requests.');
  }
  function renderRisks() {
    const query = $('#risk-search').value.trim().toLowerCase(); const severity = $('#risk-severity').value;
    const rows = state.risks.filter(r => (!severity || r.severity === severity) && (!query || `${r.key} ${r.title} ${r.description}`.toLowerCase().includes(query)));
    $('#risk-rows').innerHTML = rows.length ? rows.map(r => `<tr><td><strong>${escapeHtml(r.key)}</strong><br>${escapeHtml(r.title)}<br><span class="ec-small">${escapeHtml(r.description || '')}</span></td><td>${escapeHtml(r.category)}</td><td>${r.probability}/5</td><td>${r.impact}/5</td><td><strong>${r.score}</strong> ${pill(r.severity)}</td><td>${r.owner_id ?? 'Unassigned'}</td><td>${pill(r.status)}</td><td>${escapeHtml(r.due_date || '—')}</td></tr>`).join('') : emptyRow(8, 'No risks match these filters.');
  }
  function renderObjectives() {
    const status = $('#objective-status').value; const rows = state.objectives.filter(o => !status || o.status === status);
    $('#objective-rows').innerHTML = rows.length ? rows.map(o => `<tr><td><strong>${escapeHtml(o.title)}</strong><br><span class="ec-small">${escapeHtml(o.description || '')}</span></td><td>${escapeHtml(o.period)}</td><td>${o.owner_id ?? '—'}</td><td><strong>${o.progress}%</strong><div class="ec-progress"><span style="width:${Math.max(0,Math.min(100,Number(o.progress)||0))}%"></span></div></td><td>${'●'.repeat(Math.max(0,Math.min(5,o.confidence)))}<span class="ec-small">${o.confidence}/5</span></td><td>${pill(o.status)}</td><td>${escapeHtml(o.due_date || '—')}</td></tr>`).join('') : emptyRow(7, 'No objectives yet.');
  }
  function renderAssets() {
    const query = $('#asset-search').value.trim().toLowerCase(); const status = $('#asset-status').value;
    const rows = state.assets.filter(a => (!status || a.status === status) && (!query || `${a.asset_tag} ${a.name} ${a.serial_number}`.toLowerCase().includes(query)));
    $('#asset-rows').innerHTML = rows.length ? rows.map(a => `<tr><td><strong>${escapeHtml(a.asset_tag)}</strong></td><td>${escapeHtml(a.name)}<br><span class="ec-small">${escapeHtml(a.vendor || '')}</span></td><td>${escapeHtml(a.category)}</td><td>${escapeHtml(a.serial_number || '—')}</td><td>${escapeHtml(a.location || '—')}</td><td>${a.purchase_cost == null ? '—' : money(a.purchase_cost)}</td><td>${pill(a.status)}</td><td><div class="ec-actions">${a.status === 'available' ? `<button class="ec-btn" data-assign-asset="${a.id}">Assign</button>` : a.status === 'assigned' ? `<button class="ec-btn secondary" data-return-asset="${a.id}">Return</button>` : ''}<button class="ec-btn secondary" data-maintenance-asset="${a.id}">Maintenance</button></div></td></tr>`).join('') : emptyRow(8, 'No assets match these filters.');
  }
  async function loadFinance() {
    const [summary, tx, purchases, alerts] = await Promise.all([api('/api/finance/summary'), api('/api/finance/transactions?page_size=100'), api('/api/finance/purchases'), api('/api/finance/budget-alerts?threshold=80')]);
    state.transactions = tx.items || []; state.purchases = purchases || [];
    setStats('finance-stats', [['Task budgets', money(summary.task_budget_total)], ['Approved expenses', money(summary.approved_expenses)], ['Net spend', money(summary.net_expense)], ['Budget remaining', money(summary.budget_remaining_against_ledger)]]);
    renderFinance();
    if (alerts.some(x => x.over_budget)) showMessage(`${alerts.filter(x => x.over_budget).length} task(s) are over budget.`, 'error');
  }
  async function loadRisks() {
    const [list, summary] = await Promise.all([api('/api/risks?page_size=100'), api('/api/risks/summary/heatmap')]);
    state.risks = list.items || [];
    setStats('risk-stats', [['Open risks', summary.open_risks], ['Critical', summary.severity_counts.critical], ['High', summary.severity_counts.high], ['Overdue', summary.overdue]]);
    renderRisks();
  }
  async function loadObjectives() {
    const [list, summary] = await Promise.all([api('/api/objectives?page_size=100'), api('/api/objectives/summary/portfolio')]);
    state.objectives = list.items || [];
    setStats('objective-stats', [['Objectives', summary.total], ['Average progress', `${summary.average_progress}%`], ['At risk', summary.by_status.at_risk], ['Overdue', summary.overdue]]);
    renderObjectives();
  }
  async function loadAssets() {
    const [list, summary] = await Promise.all([api('/api/assets?page_size=100'), api('/api/assets/summary/inventory')]);
    state.assets = list.items || [];
    setStats('asset-stats', [['Assets', summary.total_assets], ['Assigned', summary.by_status.assigned], ['Purchase value', money(summary.purchase_value)], ['Warranty alerts', summary.warranties_expiring_60_days]]);
    renderAssets();
  }
  async function loadTab(tab) {
    root.classList.add('ec-loading');
    try {
      if (tab === 'finance') await loadFinance();
      if (tab === 'risks') await loadRisks();
      if (tab === 'objectives') await loadObjectives();
      if (tab === 'assets') await loadAssets();
    } catch (error) { showMessage(error.message, 'error'); }
    finally { root.classList.remove('ec-loading'); }
  }
  function field(name, label, type = 'text', options = {}) {
    const id = `ec-field-${name}`;
    let control;
    if (type === 'textarea') control = `<textarea id="${id}" name="${name}" ${options.required ? 'required' : ''} maxlength="${options.maxlength || 12000}" ${options.placeholder ? `placeholder="${escapeHtml(options.placeholder)}"` : ''}></textarea>`;
    else if (type === 'select') control = `<select id="${id}" name="${name}" ${options.required ? 'required' : ''}>${options.choices.map(([v,l]) => `<option value="${escapeHtml(v)}">${escapeHtml(l)}</option>`).join('')}</select>`;
    else control = `<input id="${id}" name="${name}" type="${type}" ${options.required ? 'required' : ''} ${options.min !== undefined ? `min="${options.min}"` : ''} ${options.max !== undefined ? `max="${options.max}"` : ''} ${options.step ? `step="${options.step}"` : ''} maxlength="${options.maxlength || 1000}" ${options.placeholder ? `placeholder="${escapeHtml(options.placeholder)}"` : ''}>`;
    return `<label class="ec-field ${options.full ? 'full' : ''}" for="${id}">${escapeHtml(label)}${control}</label>`;
  }
  const choices = items => ({ type:'select', choices:items });
  function openForm(kind) {
    const configs = {
      transaction: {title:'Submit expense transaction', endpoint:'/api/finance/transactions', fields:[field('amount','Amount (INR)','number',{required:true,min:0.01,step:'0.01'}),field('transaction_date','Transaction date','date',{required:true}),field('category','Category','select',{required:true,choices:['travel','equipment','software','training','contractor','operational','other'].map(x=>[x,x])}),field('transaction_type','Type','select',{choices:[['expense','Expense'],['credit','Credit']] }),field('task_id','Task ID (optional)','number',{min:1}),field('merchant','Merchant','text'),field('reference','Reference','text'),field('description','Description','textarea',{full:true})]},
      purchase: {title:'Request purchase', endpoint:'/api/finance/purchases', fields:[field('title','Purchase title','text',{required:true}),field('vendor','Vendor','text'),field('amount','Amount (INR)','number',{required:true,min:0.01,step:'0.01'}),field('task_id','Task ID (optional)','number',{min:1}),field('justification','Business justification','textarea',{full:true,required:true})]},
      risk: {title:'Register a project risk', endpoint:'/api/risks', fields:[field('title','Risk title','text',{required:true}),field('category','Category','select',{choices:['delivery','financial','security','compliance','people','technical','vendor','operational','other'].map(x=>[x,x])}),field('probability','Probability (1–5)','number',{required:true,min:1,max:5}),field('impact','Impact (1–5)','number',{required:true,min:1,max:5}),field('owner_id','Owner user ID','number',{min:1}),field('project_id','Project ID','number',{min:1}),field('due_date','Mitigation due date','date'),field('response_strategy','Response strategy','select',{choices:[['mitigate','Mitigate'],['avoid','Avoid'],['transfer','Transfer'],['accept','Accept']]}),field('description','Risk description','textarea',{full:true}),field('mitigation_plan','Mitigation plan','textarea',{full:true})]},
      objective: {title:'Create objective', endpoint:'/api/objectives', fields:[field('title','Objective title','text',{required:true}),field('period','Period','select',{choices:[['monthly','Monthly'],['quarterly','Quarterly'],['half_yearly','Half-yearly'],['annual','Annual'],['custom','Custom']]}),field('owner_id','Owner user ID','number',{min:1}),field('project_id','Project ID','number',{min:1}),field('start_date','Start date','date'),field('due_date','Due date','date'),field('confidence','Confidence (1–5)','number',{required:true,min:1,max:5}),field('description','Description','textarea',{full:true})]},
      asset: {title:'Register company asset', endpoint:'/api/assets', fields:[field('asset_tag','Asset tag','text',{required:true}),field('name','Asset name','text',{required:true}),field('category','Category','select',{choices:['laptop','desktop','mobile','equipment','license','furniture','vehicle','other'].map(x=>[x,x])}),field('serial_number','Serial number','text'),field('purchase_date','Purchase date','date'),field('purchase_cost','Purchase cost','number',{min:0,step:'0.01'}),field('warranty_until','Warranty until','date'),field('vendor','Vendor','text'),field('location','Location','text'),field('notes','Notes','textarea',{full:true})]}
    };
    const config = configs[kind]; if (!config) return;
    $('#ec-modal-title').textContent = config.title;
    form.dataset.endpoint = config.endpoint; form.dataset.kind = kind;
    form.innerHTML = config.fields.join('') + `<div class="ec-field full"><button class="ec-btn" type="submit">Save record</button></div>`;
    modal.classList.add('open');
    $('input,select,textarea', form)?.focus();
  }
  function closeForm() { modal.classList.remove('open'); form.reset(); }
  async function submitForm(event) {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    for (const key of Object.keys(data)) if (data[key] === '') delete data[key];
    const submit = $('button[type="submit"]', form); submit.disabled = true; submit.textContent = 'Saving…';
    try {
      await post(form.dataset.endpoint, data); closeForm(); showMessage('Record created successfully.'); await loadTab(state.currentTab);
    } catch (error) { showMessage(error.message, 'error'); }
    finally { submit.disabled = false; submit.textContent = 'Save record'; }
  }
  $$('.ec-tab').forEach(button => button.addEventListener('click', () => {
    state.currentTab = button.dataset.panel;
    $$('.ec-tab').forEach(tab => tab.setAttribute('aria-selected', String(tab === button)));
    $$('.ec-panel').forEach(panel => panel.classList.toggle('active', panel.id === `panel-${state.currentTab}`));
    loadTab(state.currentTab);
  }));
  root.addEventListener('click', async event => {
    const create = event.target.closest('[data-create]'); if (create) return openForm(create.dataset.create);
    const approve = event.target.closest('[data-approve-tx]');
    const reject = event.target.closest('[data-reject-tx]');
    const voidTx = event.target.closest('[data-void-tx]');
    const purchase = event.target.closest('[data-review-purchase]');
    const assign = event.target.closest('[data-assign-asset]');
    const returned = event.target.closest('[data-return-asset]');
    const maintenance = event.target.closest('[data-maintenance-asset]');
    try {
      if (approve) { await post(`/api/finance/transactions/${approve.dataset.approveTx}/approve`, {}); showMessage('Expense approved.'); await loadFinance(); }
      if (reject) { const reason = window.prompt('Enter a rejection reason:'); if (!reason?.trim()) return; await post(`/api/finance/transactions/${reject.dataset.rejectTx}/reject`, {reason}); showMessage('Expense rejected.'); await loadFinance(); }
      if (voidTx) { if (!window.confirm('Void this transaction? An approved task expense will be reversed.')) return; await post(`/api/finance/transactions/${voidTx.dataset.voidTx}/void`, {}); showMessage('Transaction voided.'); await loadFinance(); }
      if (purchase) { const decision = purchase.dataset.decision; const note = decision === 'rejected' ? window.prompt('Reason for rejection:') : ''; if (decision === 'rejected' && !note?.trim()) return; await post(`/api/finance/purchases/${purchase.dataset.reviewPurchase}/review`, {decision, note: note || ''}); showMessage(`Purchase request ${decision}.`); await loadFinance(); }
      if (assign) { const user_id = window.prompt('Enter employee user ID to assign this asset:'); if (!user_id) return; await post(`/api/assets/${assign.dataset.assignAsset}/assignments`, {user_id:Number(user_id)}); showMessage('Asset assigned.'); await loadAssets(); }
      if (returned) { const condition_in = window.prompt('Condition on return (optional):') || ''; await post(`/api/assets/${returned.dataset.returnAsset}/return`, {condition_in}); showMessage('Asset returned.'); await loadAssets(); }
      if (maintenance) { const title = window.prompt('Describe the maintenance work:'); if (!title?.trim()) return; await post(`/api/assets/${maintenance.dataset.maintenanceAsset}/maintenance`, {title}); showMessage('Maintenance request created.'); await loadAssets(); }
    } catch (error) { showMessage(error.message, 'error'); }
  });
  form.addEventListener('submit', submitForm);
  $('#ec-modal-close').addEventListener('click', closeForm);
  modal.addEventListener('click', event => { if (event.target === modal) closeForm(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && modal.classList.contains('open')) closeForm(); });
  $('#finance-search').addEventListener('input', renderFinance); $('#finance-status').addEventListener('change', renderFinance);
  $('#risk-search').addEventListener('input', renderRisks); $('#risk-severity').addEventListener('change', renderRisks);
  $('#objective-status').addEventListener('change', renderObjectives); $('#asset-search').addEventListener('input', renderAssets); $('#asset-status').addEventListener('change', renderAssets);
  loadTab('finance');
})();
