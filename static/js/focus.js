const FocusManager = {
  active: null,
  interval: null,

  async init() {
    document.getElementById('focus-start').addEventListener('click', () => this.start());
    document.getElementById('focus-pause').addEventListener('click', () => this.transition('pause'));
    document.getElementById('focus-resume').addEventListener('click', () => this.transition('resume'));
    document.getElementById('focus-finish').addEventListener('click', () => this.transition('finish'));
    await this.loadTasks();
    await this.refresh();
    this.interval = setInterval(() => this.renderTimer(), 1000);
  },

  async loadTasks() {
    try {
      const response = await window.API.get('/tasks?assigned_to=me');
      const tasks = response.data?.items || response.data || [];
      const select = document.getElementById('focus-task');
      tasks.forEach((task) => {
        const option = document.createElement('option');
        option.value = task.id;
        option.textContent = task.title;
        select.appendChild(option);
      });
    } catch (error) {
      this.message(error.message || 'Unable to load tasks.', 'error');
    }
  },

  async refresh() {
    try {
      const [active, history] = await Promise.all([
        window.API.get('/focus-sessions/active'),
        window.API.get('/focus-sessions'),
      ]);
      this.active = active.data;
      this.renderHistory(history.data);
      this.renderTimer();
    } catch (error) {
      this.message(error.message || 'Unable to load focus sessions.', 'error');
    }
  },

  async start() {
    const taskId = document.getElementById('focus-task').value;
    if (!taskId) return this.message('Choose a task first.', 'error');
    try {
      const response = await window.API.post('/focus-sessions', { task_id: Number(taskId) });
      this.active = response.data;
      this.message('Focus session started.', 'success');
      this.renderTimer();
    } catch (error) {
      this.message(error.message, 'error');
    }
  },

  async transition(action) {
    if (!this.active) return;
    try {
      const response = await window.API.post(`/focus-sessions/${this.active.id}/${action}`);
      this.active = action === 'finish' ? null : response.data;
      this.message(`Focus session ${action === 'finish' ? 'finished' : `${action}d`}.`, 'success');
      await this.refresh();
    } catch (error) {
      this.message(error.message, 'error');
    }
  },

  renderTimer() {
    const display = document.getElementById('focus-timer-display');
    const task = document.getElementById('focus-timer-task');
    const start = document.getElementById('focus-start');
    const pause = document.getElementById('focus-pause');
    const resume = document.getElementById('focus-resume');
    const finish = document.getElementById('focus-finish');
    if (!this.active) {
      display.textContent = '00:00:00';
      task.textContent = 'No active session';
      start.disabled = false;
      pause.disabled = true;
      resume.disabled = true;
      finish.disabled = true;
      return;
    }
    let seconds = this.active.active_seconds;
    if (this.active.status === 'active') {
      seconds += Math.max(0, Math.floor((Date.now() - Date.parse(this.active.last_resumed_at)) / 1000));
    }
    display.textContent = this.format(seconds);
    task.textContent = this.active.task_title;
    start.disabled = true;
    pause.disabled = this.active.status !== 'active';
    resume.disabled = this.active.status !== 'paused';
    finish.disabled = false;
  },

  format(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainder = seconds % 60;
    return [hours, minutes, remainder].map((value) => String(value).padStart(2, '0')).join(':');
  },

  renderHistory(data) {
    const summary = document.getElementById('focus-summary');
    summary.replaceChildren();
    [['Today', `${data.summary.actual_hours}h`], ['This week', `${data.weekly_summary.actual_hours}h`], ['Sessions', data.summary.session_count]].forEach(([label, value]) => {
      const item = document.createElement('div');
      const title = document.createElement('strong');
      title.textContent = value;
      const caption = document.createElement('span');
      caption.textContent = label;
      item.append(title, caption);
      summary.appendChild(item);
    });
    const history = document.getElementById('focus-history');
    history.replaceChildren();
    if (!data.items.length) {
      history.textContent = 'No focus sessions recorded for this period.';
      return;
    }
    data.items.forEach((item) => {
      const row = document.createElement('p');
      row.textContent = `${item.task_title} — ${this.format(item.active_seconds)} (${item.status})`;
      history.appendChild(row);
    });
  },

  message(text, type) {
    const node = document.getElementById('focus-message');
    node.textContent = text;
    node.className = type === 'error' ? 'text-danger' : 'text-success';
  },
};

document.addEventListener('DOMContentLoaded', () => FocusManager.init());
