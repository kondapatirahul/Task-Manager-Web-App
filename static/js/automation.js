const AutomationManager = {
  rules: [],

  init() {
    document.getElementById('automation-create-toggle').addEventListener('click', () => {
      document.getElementById('automation-form-card').hidden = false;
    });
    document.getElementById('automation-form').addEventListener('submit', (event) => {
      event.preventDefault();
      this.create();
    });
    this.load();
  },

  async load() {
    try {
      const response = await window.API.get('/automation/rules');
      this.rules = response.data || [];
      this.render();
    } catch (error) {
      this.message(error.message, 'text-danger');
    }
  },

  render() {
    const list = document.getElementById('automation-list');
    list.replaceChildren();
    if (!this.rules.length) return this.message('No automation rules configured.', 'empty-state');
    this.rules.forEach((rule) => {
      const card = document.createElement('article');
      card.className = 'card automation-card';
      const title = document.createElement('h2');
      title.textContent = rule.name;
      const details = document.createElement('p');
      details.textContent = `${rule.schedule} · next run ${rule.next_run_at || 'not scheduled'} · ${rule.enabled ? 'enabled' : 'disabled'}`;
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'btn btn-secondary btn-sm';
      toggle.textContent = rule.enabled ? 'Disable' : 'Enable';
      toggle.addEventListener('click', () => this.toggle(rule));
      const inspect = document.createElement('button');
      inspect.type = 'button';
      inspect.className = 'btn btn-ghost btn-sm';
      inspect.textContent = 'Inspect executions';
      inspect.addEventListener('click', () => this.inspect(rule));
      card.append(title, details, toggle, inspect);
      list.appendChild(card);
    });
  },

  message(text, className) {
    const list = document.getElementById('automation-list');
    list.replaceChildren();
    const node = document.createElement('p');
    node.className = className;
    node.textContent = text;
    list.appendChild(node);
  },

  async create() {
    const sourceType = document.getElementById('automation-source-type').value;
    const id = Number(document.getElementById('automation-source-id').value);
    const localDate = document.getElementById('automation-next-run').value;
    const payload = {
      name: document.getElementById('automation-name').value.trim(),
      schedule: document.getElementById('automation-schedule').value,
      next_run_at: new Date(localDate).toISOString(),
    };
    payload[sourceType === 'template' ? 'template_id' : 'source_task_id'] = id;
    try {
      await window.API.post('/automation/rules', { ...payload, rule_type: 'recurring_task' });
      document.getElementById('automation-form-card').hidden = true;
      await this.load();
    } catch (error) {
      window.API.toast(error.message, 'danger');
    }
  },

  async toggle(rule) {
    try {
      await window.API.patch(`/automation/rules/${rule.id}`, { enabled: !rule.enabled });
      await this.load();
    } catch (error) {
      window.API.toast(error.message, 'danger');
    }
  },

  async inspect(rule) {
    try {
      const response = await window.API.get(`/automation/rules/${rule.id}/executions`);
      const result = response.data || [];
      window.API.toast(`${result.length} execution record(s).`, 'info');
    } catch (error) {
      window.API.toast(error.message, 'danger');
    }
  },
};

document.addEventListener('DOMContentLoaded', () => AutomationManager.init());
