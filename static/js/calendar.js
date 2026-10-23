(function () {
  'use strict';

  const state = { date: new Date(), view: 'month', tasks: [] };
  const content = document.getElementById('calendar-content');
  const title = document.getElementById('calendar-title');
  const statusMessage = document.getElementById('calendar-status-message');

  function pad(value) { return String(value).padStart(2, '0'); }
  function iso(date) {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  }
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, char => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
    }[char]));
  }
  function startOfWeek(date) {
    const result = new Date(date);
    const day = result.getDay();
    result.setDate(result.getDate() - (day === 0 ? 6 : day - 1));
    return result;
  }
  function range() {
    if (state.view === 'week') {
      const start = startOfWeek(state.date);
      const end = new Date(start); end.setDate(end.getDate() + 6);
      return [start, end];
    }
    if (state.view === 'agenda') {
      const start = new Date(state.date);
      const end = new Date(start); end.setDate(end.getDate() + 30);
      return [start, end];
    }
    const start = new Date(state.date.getFullYear(), state.date.getMonth(), 1);
    const end = new Date(state.date.getFullYear(), state.date.getMonth() + 1, 0);
    return [start, end];
  }
  function taskMarkup(task) {
    return `<a class="calendar-task priority-${escapeHtml(task.priority)} status-${escapeHtml(task.status)}${task.is_overdue ? ' is-overdue' : ''}" href="${task.task_url}">
      <strong>${escapeHtml(task.title)}</strong><span>${escapeHtml(task.priority)} · ${escapeHtml(task.status_label)}</span>
    </a>`;
  }
  function tasksFor(day) {
    const key = iso(day);
    return state.tasks.filter(task => task.due_date === key);
  }
  function renderMonth() {
    const first = new Date(state.date.getFullYear(), state.date.getMonth(), 1);
    const gridStart = startOfWeek(first);
    const cells = [];
    for (let index = 0; index < 42; index += 1) {
      const day = new Date(gridStart); day.setDate(gridStart.getDate() + index);
      cells.push(`<div class="calendar-day${day.getMonth() !== state.date.getMonth() ? ' is-outside' : ''}">
        <div class="calendar-day-number">${day.getDate()}</div>${tasksFor(day).map(taskMarkup).join('')}
      </div>`);
    }
    content.innerHTML = `<div class="calendar-weekdays">${['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(day => `<span>${day}</span>`).join('')}</div><div class="calendar-month-grid">${cells.join('')}</div>`;
    title.textContent = state.date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
  }
  function renderWeek() {
    const start = startOfWeek(state.date);
    const days = Array.from({ length: 7 }, (_, index) => {
      const day = new Date(start); day.setDate(start.getDate() + index);
      return `<section class="calendar-week-day"><h3>${day.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</h3>${tasksFor(day).map(taskMarkup).join('') || '<p class="text-muted">No tasks</p>'}</section>`;
    });
    content.innerHTML = `<div class="calendar-week-grid">${days.join('')}</div>`;
    title.textContent = `Week of ${start.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}`;
  }
  function renderAgenda() {
    const groups = {};
    state.tasks.forEach(task => { (groups[task.due_date] ||= []).push(task); });
    const rows = Object.keys(groups).sort().map(day => `<section class="calendar-agenda-day"><h3>${new Date(`${day}T00:00:00`).toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' })}</h3>${groups[day].map(taskMarkup).join('')}</section>`);
    content.innerHTML = rows.length ? rows.join('') : '<p class="calendar-empty">No tasks match this date range or filters.</p>';
    title.textContent = 'Upcoming agenda';
  }
  function render() {
    if (!state.tasks.length) {
      content.innerHTML = '<p class="calendar-empty">No tasks match this date range or filters.</p>';
      if (state.view === 'month') title.textContent = state.date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
      else if (state.view === 'week') title.textContent = 'Selected week';
      else title.textContent = 'Upcoming agenda';
    } else if (state.view === 'month') renderMonth();
    else if (state.view === 'week') renderWeek();
    else renderAgenda();
  }
  async function load() {
    const [start, end] = range();
    const params = new URLSearchParams({ start: iso(start), end: iso(end) });
    [['status', 'calendar-status'], ['priority', 'calendar-priority'], ['deadline', 'calendar-deadline'], ['q', 'calendar-search'], ['employee_id', 'calendar-employee']].forEach(([key, id]) => {
      const value = document.getElementById(id)?.value;
      if (value) params.set(key, value);
    });
    statusMessage.textContent = 'Loading tasks...';
    try {
      const response = await window.API.get(`/calendar/tasks?${params.toString()}`);
      state.tasks = response.data.tasks;
      statusMessage.textContent = `${state.tasks.length} dated task${state.tasks.length === 1 ? '' : 's'}`;
      render();
    } catch (error) {
      state.tasks = [];
      content.innerHTML = `<p class="calendar-empty">${escapeHtml(error.message || 'Unable to load calendar tasks.')}</p>`;
      statusMessage.textContent = 'Calendar could not be loaded.';
    }
  }
  function shift(amount) {
    if (state.view === 'month') state.date.setMonth(state.date.getMonth() + amount);
    else if (state.view === 'week') state.date.setDate(state.date.getDate() + amount * 7);
    else state.date.setDate(state.date.getDate() + amount * 30);
    load();
  }
  document.getElementById('calendar-prev').addEventListener('click', () => shift(-1));
  document.getElementById('calendar-next').addEventListener('click', () => shift(1));
  document.getElementById('calendar-today').addEventListener('click', () => { state.date = new Date(); load(); });
  document.querySelectorAll('[data-calendar-view]').forEach(button => button.addEventListener('click', () => {
    state.view = button.dataset.calendarView;
    document.querySelectorAll('[data-calendar-view]').forEach(item => item.classList.toggle('is-active', item === button));
    load();
  }));
  ['calendar-status', 'calendar-priority', 'calendar-deadline', 'calendar-employee'].forEach(id => document.getElementById(id)?.addEventListener('change', load));
  document.getElementById('calendar-search').addEventListener('input', () => {
    clearTimeout(window.calendarSearchTimer);
    window.calendarSearchTimer = setTimeout(load, 250);
  });
  load();
}());
