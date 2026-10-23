(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const modal = $('goal-modal');
  const today = new Date();
  const iso = date => date.toISOString().slice(0, 10);
  const escapeHtml = value => String(value || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[c]));

  function openGoal(goal) {
    $('goal-id').value = goal?.id || '';
    $('goal-title').value = goal?.title || '';
    $('goal-description').value = goal?.description || '';
    $('goal-type').value = goal?.goal_type || 'complete_tasks';
    $('goal-target').value = goal?.target_value || 1;
    $('goal-start').value = goal?.start_date || iso(today);
    $('goal-end').value = goal?.target_date || iso(new Date(today.getFullYear(), today.getMonth(), today.getDate() + 30));
    modal.classList.add('is-active');
  }
  function closeGoal() { modal.classList.remove('is-active'); }
  function renderGoals(goals) {
    $('goals-list').innerHTML = goals.length ? goals.map(goal => `<article class="goal-row">
      <div class="goal-row-header"><div><h3>${escapeHtml(goal.title)}</h3><p class="text-muted">${escapeHtml(goal.description)}</p></div><span class="badge badge-${goal.status === 'completed' ? 'completed' : 'pending'}">${escapeHtml(goal.status)}</span></div>
      <div class="goal-progress"><div class="progress-track"><div class="progress-fill" style="width:${goal.progress_percent}%"></div></div><strong>${goal.current_progress}/${goal.target_value} (${goal.progress_percent}%)</strong></div>
      <div class="goal-row-actions"><span class="text-muted">${goal.start_date} to ${goal.target_date}</span><button class="btn btn-ghost btn-sm edit-goal" data-id="${goal.id}">Edit</button><button class="btn btn-ghost btn-sm delete-goal" data-id="${goal.id}">Delete</button></div>
    </article>`).join('') : '<p class="calendar-empty">No goals yet. Create one to start tracking progress.</p>';
    document.querySelectorAll('.edit-goal').forEach(button => button.addEventListener('click', () => openGoal(goals.find(item => item.id === Number(button.dataset.id)))));
    document.querySelectorAll('.delete-goal').forEach(button => button.addEventListener('click', async () => { if (confirm('Delete this goal?')) { await window.API.delete(`/goals/${button.dataset.id}`); loadGoals(); } }));
  }
  async function loadGoals() { const response = await window.API.get('/goals'); renderGoals(response.data); }
  async function loadAnalytics(days) {
    const end = new Date();
    const start = days === 'month' ? new Date(end.getFullYear(), end.getMonth(), 1) : new Date(end.getFullYear(), end.getMonth(), end.getDate() - Number(days) + 1);
    const response = await window.API.get(`/analytics?start=${iso(start)}&end=${iso(end)}`);
    const data = response.data;
    $('analytics-metrics').innerHTML = [['completed', 'Completed'], ['open', 'Open'], ['overdue', 'Overdue'], ['completion_rate', 'Completion rate']].map(([key, label]) => `<div><strong>${data[key]}${key === 'completion_rate' ? '%' : ''}</strong><span>${label}</span></div>`).join('');
    $('analytics-summary').textContent = data.average_completion_hours === null ? 'Average completion time is unavailable for this period.' : `Average completion time: ${data.average_completion_hours} hours.`;
  }
  $('new-goal-btn').addEventListener('click', () => openGoal());
  $('close-goal-btn').addEventListener('click', closeGoal); $('cancel-goal-btn').addEventListener('click', closeGoal);
  $('goal-form').addEventListener('submit', async event => { event.preventDefault(); const payload = { title: $('goal-title').value, description: $('goal-description').value, goal_type: $('goal-type').value, target_value: Number($('goal-target').value), start_date: $('goal-start').value, target_date: $('goal-end').value }; const id = $('goal-id').value; try { if (id) await window.API.put(`/goals/${id}`, payload); else await window.API.post('/goals', payload); closeGoal(); loadGoals(); } catch (error) { window.API.toast(error.message, 'error'); } });
  document.querySelectorAll('.period-btn').forEach(button => button.addEventListener('click', () => { document.querySelectorAll('.period-btn').forEach(item => item.classList.remove('is-active')); button.classList.add('is-active'); loadAnalytics(button.dataset.days); }));
  loadGoals(); loadAnalytics(7);
}());
