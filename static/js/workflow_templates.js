const WorkflowTemplateManager = {
  templates: [],
  editingId: null,

  init() {
    document.getElementById('template-create-toggle').addEventListener('click', () => {
      document.getElementById('template-form-card').hidden = false;
      this.editingId = null;
      document.getElementById('template-form-heading').textContent = 'Create template';
    });
    document.getElementById('template-form').addEventListener('submit', (event) => {
      event.preventDefault();
      this.save();
    });
    this.load();
  },

  async load() {
    try {
      const response = await window.API.get('/workflow-templates');
      this.templates = response.data || [];
      this.render();
    } catch (error) {
      this.renderMessage(error.message || 'Unable to load templates.', 'text-danger');
    }
  },

  render() {
    const list = document.getElementById('template-list');
    list.replaceChildren();
    if (!this.templates.length) {
      this.renderMessage('No workflow templates are available yet.', 'empty-state');
      return;
    }
    this.templates.forEach((template) => {
      const card = document.createElement('article');
      card.className = 'card template-card';
      const title = document.createElement('h2');
      title.textContent = template.name;
      const meta = document.createElement('p');
      meta.className = 'text-muted';
      meta.textContent = `${template.visibility} · ${template.default_priority} priority · ${template.checklist.length} steps`;
      const description = document.createElement('p');
      description.textContent = template.description;
      const steps = document.createElement('ol');
      template.checklist.forEach((item) => {
        const step = document.createElement('li');
        step.textContent = item.due_offset_days === null
          ? item.title
          : `${item.title} (${item.due_offset_days} days)`;
        steps.appendChild(step);
      });
      const actions = document.createElement('div');
      actions.className = 'template-actions';
      [['Preview', () => this.preview(template)], ['Use template', () => this.instantiate(template)]].forEach(([label, handler]) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-secondary btn-sm';
        button.textContent = label;
        button.addEventListener('click', handler);
        actions.appendChild(button);
      });
      if (template.can_edit) {
        [['Edit', () => this.edit(template)], ['Duplicate', () => this.duplicate(template)], ['Archive', () => this.archive(template)]].forEach(([label, handler]) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'btn btn-ghost btn-sm';
          button.textContent = label;
          button.addEventListener('click', handler);
          actions.appendChild(button);
        });
      }
      card.append(title, meta, description, steps, actions);
      list.appendChild(card);
    });
  },

  renderMessage(message, className) {
    const list = document.getElementById('template-list');
    list.replaceChildren();
    const node = document.createElement('p');
    node.className = className;
    node.textContent = message;
    list.appendChild(node);
  },

  readPayload() {
    const checklist = document.getElementById('template-items').value.split('\n').map((line) => line.trim()).filter(Boolean).map((line) => {
      const parts = line.split('|');
      const item = { title: parts[0].trim() };
      if (parts[1] && parts[1].trim()) item.due_offset_days = Number(parts[1].trim());
      return item;
    });
    return {
      name: document.getElementById('template-name').value.trim(),
      description: document.getElementById('template-description').value.trim(),
      default_priority: document.getElementById('template-priority').value,
      visibility: document.getElementById('template-visibility').value,
      checklist,
    };
  },

  async save() {
    try {
      if (this.editingId) {
        await window.API.put(`/workflow-templates/${this.editingId}`, this.readPayload());
      } else {
        await window.API.post('/workflow-templates', this.readPayload());
      }
      document.getElementById('template-form-card').hidden = true;
      await this.load();
    } catch (error) {
      window.API.toast(error.message, 'danger');
    }
  },

  preview(template) {
    const preview = document.getElementById('template-preview');
    preview.hidden = false;
    preview.replaceChildren();
    const heading = document.createElement('h2');
    heading.textContent = `Preview: ${template.name}`;
    const text = document.createElement('p');
    text.textContent = template.description;
    preview.append(heading, text);
    template.checklist.forEach((item, index) => {
      const line = document.createElement('p');
      line.textContent = `${index + 1}. ${item.title}`;
      preview.appendChild(line);
    });
    preview.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  },

  edit(template) {
    this.editingId = template.id;
    document.getElementById('template-form-card').hidden = false;
    document.getElementById('template-form-heading').textContent = 'Edit template';
    document.getElementById('template-name').value = template.name;
    document.getElementById('template-description').value = template.description;
    document.getElementById('template-priority').value = template.default_priority;
    document.getElementById('template-visibility').value = template.visibility;
    document.getElementById('template-items').value = template.checklist.map((item) => (
      item.due_offset_days === null ? item.title : `${item.title} | ${item.due_offset_days}`
    )).join('\n');
  },

  async duplicate(template) {
    try {
      await window.API.post(`/workflow-templates/${template.id}/duplicate`, {});
      await this.load();
    } catch (error) {
      window.API.toast(error.message, 'danger');
    }
  },

  async archive(template) {
    try {
      await window.API.post(`/workflow-templates/${template.id}/archive`, {});
      await this.load();
    } catch (error) {
      window.API.toast(error.message, 'danger');
    }
  },

  async instantiate(template) {
    const baseDueDate = window.prompt('Optional base due date (YYYY-MM-DD):', '');
    if (baseDueDate === null) return;
    try {
      await window.API.post(`/workflow-templates/${template.id}/instantiate`, { base_due_date: baseDueDate || null });
      window.API.toast('Tasks created from template.', 'success');
    } catch (error) {
      window.API.toast(error.message, 'danger');
    }
  },
};

document.addEventListener('DOMContentLoaded', () => WorkflowTemplateManager.init());
