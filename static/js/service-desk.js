/* Service desk workspace: tickets, ticket replies, SLA metrics, and knowledge articles. */
(() => {
  'use strict';
  const $ = (selector) => document.querySelector(selector);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const state = { tickets: [], articles: [], selectedTicket: null, selectedArticle: null, activePanel: 'tickets' };
  const notice = (message, type = 'success') => { const node = $('#sd-notice'); node.textContent = message; node.className = `sd-notice show ${type}`; };
  const fail = (error) => notice(error?.message || 'The request failed. Please try again.', 'error');
  const apiCall = async (method, path, body = null) => api(method, path, body).then((response) => response.data);
  const showModal = (title, fields, submitLabel, submit) => {
    $('#sd-modal-title').textContent = title;
    const form = $('#sd-form');
    form.innerHTML = fields.map((field) => {
      const full = field.full ? ' full' : '';
      if (field.type === 'select') return `<label class="sd-field${full}">${esc(field.label)}<select name="${esc(field.name)}" ${field.required ? 'required' : ''}>${field.options.map((option) => `<option value="${esc(option.value)}">${esc(option.label)}</option>`).join('')}</select></label>`;
      if (field.type === 'textarea') return `<label class="sd-field${full}">${esc(field.label)}<textarea name="${esc(field.name)}" maxlength="${field.maxlength || 20000}" ${field.required ? 'required' : ''} placeholder="${esc(field.placeholder || '')}"></textarea></label>`;
      return `<label class="sd-field${full}">${esc(field.label)}<input name="${esc(field.name)}" type="${field.type || 'text'}" maxlength="${field.maxlength || 500}" ${field.required ? 'required' : ''} placeholder="${esc(field.placeholder || '')}"></label>`;
    }).join('') + `<div class="sd-field full"><button class="sd-button primary" type="submit">${esc(submitLabel)}</button></div>`;
    form.onsubmit = async (event) => { event.preventDefault(); const payload = Object.fromEntries(new FormData(form).entries()); try { await submit(payload); $('#sd-modal').classList.remove('open'); } catch (error) { fail(error); } };
    $('#sd-modal').classList.add('open');
  };
  const renderStats = (metrics) => {
    $('#sd-stats').innerHTML = [
      ['Open', metrics.open ?? 0], ['In progress', metrics.in_progress ?? 0],
      ['Overdue SLA', metrics.overdue ?? 0], ['Avg. satisfaction', metrics.average_satisfaction ?? '—']
    ].map(([label, value]) => `<div class="sd-card"><span class="sd-stat-label">${esc(label)}</span><strong class="sd-stat-value">${esc(value)}</strong></div>`).join('');
  };
  const renderTickets = () => {
    const tbody = $('#sd-ticket-rows');
    if (!state.tickets.length) { tbody.innerHTML = '<tr><td colspan="7" class="sd-empty">No support tickets found.</td></tr>'; return; }
    tbody.innerHTML = state.tickets.map((ticket) => `<tr>
      <td><strong>${esc(ticket.ticket_key)}</strong><br><span class="sd-muted">${esc((ticket.created_at || '').slice(0, 10))}</span></td>
      <td>${esc(ticket.subject)}</td><td>${esc(ticket.category)}</td>
      <td><span class="sd-pill ${esc(ticket.priority)}">${esc(ticket.priority)}</span></td>
      <td><span class="sd-pill ${esc(ticket.status)}">${esc(ticket.status.replaceAll('_', ' '))}</span></td>
      <td>${esc(ticket.due_at ? ticket.due_at.replace('T', ' ').slice(0, 16) : '—')}</td>
      <td><button class="sd-button" data-ticket="${ticket.id}">Open</button></td></tr>`).join('');
    tbody.querySelectorAll('[data-ticket]').forEach((button) => button.addEventListener('click', () => loadTicket(Number(button.dataset.ticket))));
  };
  const loadTickets = async () => {
    const params = new URLSearchParams();
    if ($('#sd-search').value.trim()) params.set('q', $('#sd-search').value.trim());
    if ($('#sd-status').value) params.set('status', $('#sd-status').value);
    if ($('#sd-priority').value) params.set('priority', $('#sd-priority').value);
    const [ticketResult, metrics] = await Promise.all([
      apiCall('GET', `/service-desk/tickets?${params.toString()}`), apiCall('GET', '/service-desk/metrics')
    ]);
    state.tickets = ticketResult.items || [];
    renderTickets(); renderStats(metrics);
  };
  const loadTicket = async (id) => {
    const ticket = await apiCall('GET', `/service-desk/tickets/${id}`);
    state.selectedTicket = ticket;
    const comments = ticket.comments || [];
    $('#sd-ticket-detail').innerHTML = `<div class="sd-toolbar"><div style="flex:1"><h3 style="margin:0">${esc(ticket.ticket_key)} · ${esc(ticket.subject)}</h3><p class="sd-muted">${esc(ticket.description)}</p></div><span class="sd-pill ${esc(ticket.priority)}">${esc(ticket.priority)}</span></div>
      <div class="sd-toolbar"><label class="sd-field" style="min-width:180px">Status<select id="sd-ticket-next-status">${['open','in_progress','waiting_for_requester','resolved','closed'].map((s) => `<option value="${s}" ${ticket.status === s ? 'selected' : ''}>${s.replaceAll('_',' ')}</option>`).join('')}</select></label><label class="sd-field" style="min-width:180px">Priority<select id="sd-ticket-next-priority">${['low','normal','high','urgent'].map((s) => `<option value="${s}" ${ticket.priority === s ? 'selected' : ''}>${s}</option>`).join('')}</select></label><button class="sd-button primary" id="sd-ticket-update">Update ticket</button></div>
      <h4>Conversation</h4><div id="sd-comments">${comments.length ? comments.map((comment) => `<div class="sd-comment"><div class="sd-muted">${comment.internal_note ? 'Internal note' : 'Reply'} · ${esc(comment.created_at || '')}</div><div class="sd-detail">${esc(comment.body)}</div></div>`).join('') : '<p class="sd-muted">No replies yet.</p>'}</div>
      <form id="sd-reply-form" class="sd-form"><label class="sd-field full">Reply or note<textarea name="body" maxlength="12000" required></textarea></label><label class="sd-field"><span><input name="internal_note" type="checkbox" style="width:auto"> Internal note (admin only)</span></label><div class="sd-field" style="justify-content:end"><button class="sd-button primary" type="submit">Add reply</button></div></form>`;
    $('#sd-ticket-update').addEventListener('click', async () => {
      try { await apiCall('PATCH', `/service-desk/tickets/${id}`, {status: $('#sd-ticket-next-status').value, priority: $('#sd-ticket-next-priority').value}); notice('Ticket updated.'); await loadTickets(); await loadTicket(id); }
      catch (error) { fail(error); }
    });
    $('#sd-reply-form').addEventListener('submit', async (event) => {
      event.preventDefault(); const form = event.currentTarget; const body = form.elements.body.value.trim();
      try { await apiCall('POST', `/service-desk/tickets/${id}/comments`, {body, internal_note: form.elements.internal_note.checked}); notice('Reply added.'); await loadTickets(); await loadTicket(id); }
      catch (error) { fail(error); }
    });
  };
  const createTicket = () => showModal('Create support ticket', [
    {name:'subject', label:'Subject', required:true, maxlength:180, placeholder:'What do you need help with?'},
    {name:'category', label:'Category', type:'select', options:['general','access','hardware','software','finance','hr','security','other'].map((v) => ({value:v,label:v}))},
    {name:'priority', label:'Priority', type:'select', options:['low','normal','high','urgent'].map((v) => ({value:v,label:v}))},
    {name:'description', label:'Description', type:'textarea', full:true, required:true, maxlength:20000, placeholder:'Include steps, impact, and any relevant context.'}
  ], 'Create ticket', async (data) => { await apiCall('POST', '/service-desk/tickets', data); notice('Ticket created.'); await loadTickets(); });
  const loadArticles = async () => {
    const params = new URLSearchParams(); if ($('#sd-knowledge-search').value.trim()) params.set('q', $('#sd-knowledge-search').value.trim());
    const result = await apiCall('GET', `/service-desk/knowledge?${params.toString()}`); state.articles = result.items || [];
    $('#sd-articles').innerHTML = state.articles.length ? state.articles.map((article) => `<article class="sd-article"><span class="sd-pill ${esc(article.status)}">${esc(article.category)}</span><h3>${esc(article.title)}</h3><p class="sd-muted">${esc(article.summary || 'No summary provided.')}</p><p class="sd-small">${esc(article.view_count)} views · ${esc((article.tags || []).join(', '))}</p><button class="sd-button" data-article="${article.id}">Read article</button></article>`).join('') : '<div class="sd-empty">No published articles found.</div>';
    $('#sd-articles').querySelectorAll('[data-article]').forEach((button) => button.addEventListener('click', () => loadArticle(Number(button.dataset.article))));
  };
  const loadArticle = async (id) => {
    const article = await apiCall('GET', `/service-desk/knowledge/${id}`); state.selectedArticle = article;
    $('#sd-article-detail').innerHTML = `<h2>${esc(article.title)}</h2><p class="sd-muted">${esc(article.category)} · Published ${esc(article.published_at || 'date unavailable')}</p><p>${esc(article.summary)}</p><div class="sd-detail">${esc(article.body)}</div><div class="sd-toolbar" style="margin-top:16px"><button class="sd-button" id="sd-helpful">This helped</button><button class="sd-button" id="sd-not-helpful">Not helpful</button><span class="sd-muted">${esc(article.helpful_count)} found helpful · ${esc(article.not_helpful_count)} not helpful</span></div>`;
    $('#sd-helpful').addEventListener('click', () => feedbackArticle(id, true)); $('#sd-not-helpful').addEventListener('click', () => feedbackArticle(id, false));
  };
  const feedbackArticle = async (id, helpful) => { try { await apiCall('POST', `/service-desk/knowledge/${id}/feedback`, {helpful}); notice('Thanks for your feedback.'); await loadArticle(id); } catch (error) { fail(error); } };
  const createArticle = () => showModal('Create knowledge article', [
    {name:'title', label:'Title', required:true, maxlength:180}, {name:'category', label:'Category', maxlength:64},
    {name:'summary', label:'Summary', maxlength:500, full:true}, {name:'tags', label:'Tags (comma separated)', maxlength:120},
    {name:'status', label:'Initial status', type:'select', options:[{value:'draft',label:'Draft'},{value:'published',label:'Published'}]},
    {name:'body', label:'Article body', type:'textarea', full:true, required:true, maxlength:40000}
  ], 'Save article', async (data) => { data.tags = (data.tags || '').split(',').map((tag) => tag.trim()).filter(Boolean); await apiCall('POST', '/service-desk/knowledge', data); notice('Knowledge article saved.'); await loadArticles(); });
  const setPanel = (name) => {
    state.activePanel = name;
    document.querySelectorAll('.sd-tab').forEach((tab) => tab.setAttribute('aria-selected', String(tab.dataset.panel === name)));
    document.querySelectorAll('.sd-panel').forEach((panel) => panel.classList.toggle('active', panel.id === `sd-panel-${name}`));
    if (name === 'knowledge') loadArticles().catch(fail);
  };
  document.querySelectorAll('.sd-tab').forEach((tab) => tab.addEventListener('click', () => setPanel(tab.dataset.panel)));
  $('#sd-new-ticket').addEventListener('click', createTicket); $('#sd-new-article').addEventListener('click', createArticle);
  $('#sd-modal-close').addEventListener('click', () => $('#sd-modal').classList.remove('open'));
  $('#sd-refresh').addEventListener('click', () => loadTickets().catch(fail)); $('#sd-knowledge-refresh').addEventListener('click', () => loadArticles().catch(fail));
  $('#sd-search').addEventListener('keydown', (event) => { if (event.key === 'Enter') loadTickets().catch(fail); });
  $('#sd-status').addEventListener('change', () => loadTickets().catch(fail)); $('#sd-priority').addEventListener('change', () => loadTickets().catch(fail));
  $('#sd-knowledge-search').addEventListener('keydown', (event) => { if (event.key === 'Enter') loadArticles().catch(fail); });
  $('#sd-modal').addEventListener('click', (event) => { if (event.target === $('#sd-modal')) $('#sd-modal').classList.remove('open'); });
  loadTickets().catch(fail);
})();
