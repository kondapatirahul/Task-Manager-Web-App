/* Vendor directory and contract-renewal console. */
(() => {
  'use strict';
  const $ = (selector) => document.querySelector(selector);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const apiCall = (method, path, body = null) => api(method, path, body).then((response) => response.data);
  const state = {vendors: [], selectedVendor: null, contracts: []};
  const message = (text, type = 'success') => { const node = $('#vm-message'); node.textContent = text; node.className = `vm-message show ${type}`; };
  const fail = (error) => message(error?.message || 'Unable to complete this request.', 'error');
  const renderStats = (summary) => {
    const items = [['Vendors', summary.vendors], ['Active suppliers', summary.active_vendors], ['High-risk suppliers', summary.high_risk_vendors], ['Renewals due in 30 days', summary.renewals_due_30_days]];
    $('#vm-stats').innerHTML = items.map(([label, value]) => `<div class="vm-card"><span class="vm-label">${esc(label)}</span><strong class="vm-value">${esc(value ?? 0)}</strong></div>`).join('');
  };
  const fieldsHtml = (fields) => fields.map((field) => {
    const full = field.full ? ' full' : '';
    if (field.type === 'select') return `<label class="vm-field${full}">${esc(field.label)}<select name="${esc(field.name)}" ${field.required ? 'required' : ''}>${field.options.map((o) => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join('')}</select></label>`;
    if (field.type === 'textarea') return `<label class="vm-field${full}">${esc(field.label)}<textarea name="${esc(field.name)}" maxlength="${field.maxlength || 12000}" ${field.required ? 'required' : ''}></textarea></label>`;
    return `<label class="vm-field${full}">${esc(field.label)}<input name="${esc(field.name)}" type="${field.type || 'text'}" maxlength="${field.maxlength || 500}" ${field.required ? 'required' : ''} ${field.step ? `step="${field.step}"` : ''} ${field.required ? 'required' : ''}></label>`;
  }).join('');
  const modal = (title, fields, submitText, submit) => {
    $('#vm-modal-title').textContent = title;
    const form = $('#vm-form'); form.innerHTML = fieldsHtml(fields) + `<div class="vm-field full"><button class="vm-button primary" type="submit">${esc(submitText)}</button></div>`;
    form.onsubmit = async (event) => { event.preventDefault(); const data = Object.fromEntries(new FormData(form).entries()); try { await submit(data); $('#vm-modal').classList.remove('open'); } catch (error) { fail(error); } };
    $('#vm-modal').classList.add('open');
  };
  const loadVendors = async () => {
    const params = new URLSearchParams();
    if ($('#vm-search').value.trim()) params.set('q', $('#vm-search').value.trim());
    if ($('#vm-status').value) params.set('status', $('#vm-status').value);
    if ($('#vm-risk').value) params.set('risk_tier', $('#vm-risk').value);
    const [result, summary] = await Promise.all([apiCall('GET', `/vendors?${params.toString()}`), apiCall('GET', '/vendors/summary')]);
    state.vendors = result.items || []; renderStats(summary);
    $('#vm-vendors').innerHTML = state.vendors.length ? state.vendors.map((vendor) => `<tr><td><strong>${esc(vendor.name)}</strong><br><span class="vm-muted">${esc(vendor.website || '')}</span></td><td>${esc(vendor.vendor_code)}</td><td>${esc(vendor.category)}</td><td>${esc(vendor.contact_name)}<br>${esc(vendor.contact_email)}</td><td><span class="vm-pill ${esc(vendor.risk_tier)}">${esc(vendor.risk_tier)}</span></td><td><span class="vm-pill ${esc(vendor.status)}">${esc(vendor.status)}</span></td><td><div style="display:flex;gap:6px;flex-wrap:wrap"><button class="vm-button" data-view="${vendor.id}">Contracts</button><button class="vm-button" data-contract="${vendor.id}">+ Contract</button><button class="vm-button" data-vendor-status="${vendor.id}" data-next="${vendor.status === 'active' ? 'suspended' : 'active'}">${vendor.status === 'active' ? 'Suspend' : 'Activate'}</button></div></td></tr>`).join('') : '<tr><td colspan="7" style="padding:22px;text-align:center">No vendors match these filters.</td></tr>';
    $('#vm-vendors').querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => loadContracts(Number(button.dataset.view))));
    $('#vm-vendors').querySelectorAll('[data-contract]').forEach((button) => button.addEventListener('click', () => createContract(Number(button.dataset.contract))));
    $('#vm-vendors').querySelectorAll('[data-vendor-status]').forEach((button) => button.addEventListener('click', () => changeVendorStatus(Number(button.dataset.vendorStatus), button.dataset.next)));
  };
  const loadContracts = async (vendorId) => {
    const vendor = await apiCall('GET', `/vendors/${vendorId}`); state.selectedVendor = vendor; state.contracts = vendor.contracts || [];
    $('#vm-contracts').innerHTML = state.contracts.length ? state.contracts.map((contract) => `<tr><td><strong>${esc(contract.contract_number)}</strong><br>${esc(contract.title)}</td><td>${esc(vendor.name)}</td><td>${esc(contract.start_date)}<br>to ${esc(contract.end_date)}</td><td>${esc(contract.currency)} ${esc(contract.value)}</td><td>${esc(contract.notice_days)} days ${contract.renewal_due ? '<span class="vm-pill high">Due</span>' : ''}</td><td><span class="vm-pill ${esc(contract.status)}">${esc(contract.status)}</span></td><td><button class="vm-button" data-contract-status="${contract.id}" data-next="${contract.status === 'active' ? 'terminated' : 'active'}">${contract.status === 'active' ? 'Terminate' : 'Activate'}</button></td></tr>`).join('') : '<tr><td colspan="7" style="padding:22px;text-align:center">No contracts registered for this vendor.</td></tr>';
    $('#vm-contracts').querySelectorAll('[data-contract-status]').forEach((button) => button.addEventListener('click', () => changeContractStatus(Number(button.dataset.contractStatus), button.dataset.next)));
  };
  const createVendor = () => modal('Register vendor', [
    {name:'name',label:'Vendor name',required:true}, {name:'vendor_code',label:'Vendor code',required:true},
    {name:'category',label:'Category'}, {name:'risk_tier',label:'Risk tier',type:'select',options:['low','medium','high','critical'].map((v)=>({value:v,label:v}))},
    {name:'contact_name',label:'Contact name'}, {name:'contact_email',label:'Contact email',type:'email'},
    {name:'contact_phone',label:'Contact phone'}, {name:'website',label:'Website',type:'url'},
    {name:'payment_terms',label:'Payment terms'}, {name:'tax_reference',label:'Tax reference'},
    {name:'status',label:'Status',type:'select',options:['pending','active','suspended','inactive'].map((v)=>({value:v,label:v}))},
    {name:'notes',label:'Notes',type:'textarea',full:true}
  ], 'Create vendor', async (data) => { await apiCall('POST','/vendors',data); message('Vendor registered.'); await loadVendors(); });
  const createContract = (vendorId) => modal('Register vendor contract', [
    {name:'contract_number',label:'Contract number',required:true}, {name:'title',label:'Contract title',required:true},
    {name:'start_date',label:'Start date',type:'date',required:true}, {name:'end_date',label:'End date',type:'date',required:true},
    {name:'value',label:'Contract value',type:'number',step:'0.01',required:true}, {name:'currency',label:'Currency code'},
    {name:'notice_days',label:'Renewal notice days',type:'number',step:'1'},
    {name:'status',label:'Status',type:'select',options:['draft','active','expired','terminated','renewed'].map((v)=>({value:v,label:v}))},
    {name:'auto_renew',label:'Auto-renew',type:'select',options:[{value:'false',label:'No'},{value:'true',label:'Yes'}]},
    {name:'notes',label:'Notes',type:'textarea',full:true}
  ], 'Save contract', async (data) => { data.auto_renew = data.auto_renew === 'true'; data.notice_days = Number(data.notice_days || 30); await apiCall('POST', `/vendors/${vendorId}/contracts`, data); message('Contract registered.'); await Promise.all([loadContracts(vendorId), loadVendors()]); });
  const changeVendorStatus = async (vendorId, status) => { try { await apiCall('PATCH', `/vendors/${vendorId}`, {status}); message(`Vendor ${status}.`); await loadVendors(); if (state.selectedVendor?.id === vendorId) await loadContracts(vendorId); } catch (error) { fail(error); } };
  const changeContractStatus = async (contractId, status) => { try { await apiCall('PATCH', `/vendors/contracts/${contractId}`, {status}); message(`Contract ${status}.`); if (state.selectedVendor) await loadContracts(state.selectedVendor.id); await loadVendors(); } catch (error) { fail(error); } };
  const showRenewals = async () => { try { const result = await apiCall('GET', '/vendors/contracts/renewals?days=90'); $('#vm-contracts').innerHTML = result.items.length ? result.items.map((contract) => `<tr><td><strong>${esc(contract.contract_number)}</strong><br>${esc(contract.title)}</td><td>${esc(contract.vendor_id)}</td><td>${esc(contract.start_date)}<br>to ${esc(contract.end_date)}</td><td>${esc(contract.currency)} ${esc(contract.value)}</td><td>${esc(contract.notice_days)} days</td><td><span class="vm-pill ${contract.end_date < new Date().toISOString().slice(0,10) ? 'expired' : 'active'}">${esc(contract.status)}</span></td><td>${contract.renewal_due ? '<span class="vm-pill high">Renewal notice window</span>' : '—'}</td></tr>`).join('') : '<tr><td colspan="7" style="padding:22px;text-align:center">No active contracts expire within 90 days.</td></tr>'; message(`Showing ${result.total} contracts ending within ${result.horizon_days} days.`); } catch (error) { fail(error); } };
  $('#vm-add-vendor').addEventListener('click', createVendor); $('#vm-renewals').addEventListener('click', showRenewals); $('#vm-close').addEventListener('click', () => $('#vm-modal').classList.remove('open'));
  $('#vm-refresh').addEventListener('click', () => loadVendors().catch(fail)); $('#vm-status').addEventListener('change', () => loadVendors().catch(fail)); $('#vm-risk').addEventListener('change', () => loadVendors().catch(fail));
  $('#vm-search').addEventListener('keydown', (event) => { if (event.key === 'Enter') loadVendors().catch(fail); });
  $('#vm-modal').addEventListener('click', (event) => { if (event.target === $('#vm-modal')) $('#vm-modal').classList.remove('open'); });
  loadVendors().catch(fail);
})();
