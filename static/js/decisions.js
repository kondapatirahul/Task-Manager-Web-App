const DecisionManager = {
  page: 1,
  debounce: null,
  editingId: null,

  init() {
    document.getElementById('decision-create-toggle')?.addEventListener('click', () => {
      const card = document.getElementById('decision-form-card');
      card.hidden = !card.hidden;
    });
    document.getElementById('decision-form')?.addEventListener('submit', (event) => {
      event.preventDefault();
      this.create();
    });
    ['decision-search', 'decision-status'].forEach((id) => {
      document.getElementById(id)?.addEventListener('input', () => {
        clearTimeout(this.debounce);
        this.debounce = setTimeout(() => {
          this.page = 1;
          this.load();
        }, 250);
      });
      document.getElementById(id)?.addEventListener('change', () => {
        this.page = 1;
        this.load();
      });
    });
    this.loadTeams();
    this.load();
  },

  async loadTeams() {
    try {
      const response = await window.API.get('/teams');
      const select = document.getElementById('decision-team');
      (response.data || []).forEach((team) => {
        const option = document.createElement('option');
        option.value = team.id;
        option.textContent = team.name;
        select.appendChild(option);
      });
    } catch (error) {
      window.API.toast(error.message || 'Unable to load projects.', 'danger');
    }
  },

  async load() {
    const params = new URLSearchParams();
    const search = document.getElementById('decision-search')?.value.trim();
    const status = document.getElementById('decision-status')?.value;
    if (search) params.set('q', search);
    if (status) params.set('status', status);
    params.set('page', this.page);
    try {
      const response = await window.API.get(`/api/decisions?${params}`);
      this.render(response.data?.items || []);
      this.renderPagination(response.data || {});
    } catch (error) {
      this.renderError(error.message);
    }
  },

  render(items) {
    const container = document.getElementById('decision-list');
    container.replaceChildren();
    if (!items.length) {
      const empty = document.createElement('p');
      empty.className = 'empty-state';
      empty.textContent = 'No decisions match your filters.';
      container.appendChild(empty);
      return;
    }
    items.forEach((decision) => {
      const card = document.createElement('article');
      card.className = 'card decision-card';
      const heading = document.createElement('h2');
      heading.textContent = decision.title;
      const status = document.createElement('span');
      status.className = 'badge badge-neutral';
      status.textContent = decision.status;
      const project = document.createElement('p');
      project.className = 'text-muted';
      project.textContent = `${decision.team_name || 'Project'} · ${decision.author_name}`;
      const details = document.createElement('p');
      details.textContent = decision.details;
      card.append(heading, status, project, details);
      if (decision.linked_tasks?.length) {
        const links = document.createElement('p');
        links.textContent = `Linked tasks: ${decision.linked_tasks.map((task) => task.title).join(', ')}`;
        card.appendChild(links);
      }
      if (decision.can_edit) {
        const edit = document.createElement('button');
        edit.type = 'button';
        edit.className = 'btn btn-secondary btn-sm';
        edit.textContent = 'Edit decision';
        edit.addEventListener('click', () => this.beginEdit(decision));
        card.appendChild(edit);
      }
      container.appendChild(card);
    });
  },

  renderError(message) {
    const container = document.getElementById('decision-list');
    container.replaceChildren();
    const error = document.createElement('p');
    error.className = 'text-danger';
    error.textContent = message || 'Unable to load decisions.';
    container.appendChild(error);
    document.getElementById('decision-pagination').replaceChildren();
  },

  renderPagination(data) {
    const container = document.getElementById('decision-pagination');
    container.replaceChildren();
    if (!data.pages || data.pages < 2) return;
    const previous = document.createElement('button');
    previous.type = 'button';
    previous.className = 'btn btn-secondary btn-sm';
    previous.textContent = 'Previous';
    previous.disabled = this.page <= 1;
    previous.addEventListener('click', () => {
      this.page -= 1;
      this.load();
    });
    const label = document.createElement('span');
    label.textContent = `Page ${data.page} of ${data.pages}`;
    const next = document.createElement('button');
    next.type = 'button';
    next.className = 'btn btn-secondary btn-sm';
    next.textContent = 'Next';
    next.disabled = !data.has_more;
    next.addEventListener('click', () => {
      this.page += 1;
      this.load();
    });
    container.append(previous, label, next);
  },

  async create() {
    const payload = {
      team_id: Number(document.getElementById('decision-team').value),
      title: document.getElementById('decision-title').value.trim(),
      details: document.getElementById('decision-details').value.trim(),
      rationale: document.getElementById('decision-rationale').value.trim(),
      alternatives: document.getElementById('decision-alternatives').value.trim(),
      status: document.getElementById('decision-status-input').value,
      change_note: document.getElementById('decision-change-note').value.trim(),
    };
    try {
      if (this.editingId) {
        await window.API.put(`/api/decisions/${this.editingId}`, payload);
        window.API.toast('Decision updated.', 'success');
      } else {
        await window.API.post('/api/decisions', payload);
        window.API.toast('Decision created.', 'success');
      }
      document.getElementById('decision-form').reset();
      document.getElementById('decision-form-card').hidden = true;
      this.editingId = null;
      document.getElementById('decision-form-heading').textContent = 'Create decision';
      await this.load();
    } catch (error) {
      window.API.toast(error.message || 'Unable to create decision.', 'danger');
    }
  },

  beginEdit(decision) {
    this.editingId = decision.id;
    document.getElementById('decision-form-heading').textContent = 'Update decision';
    document.getElementById('decision-form-card').hidden = false;
    document.getElementById('decision-team').value = decision.team_id;
    document.getElementById('decision-title').value = decision.title;
    document.getElementById('decision-details').value = decision.details;
    document.getElementById('decision-rationale').value = decision.rationale;
    document.getElementById('decision-alternatives').value = decision.alternatives || '';
    document.getElementById('decision-status-input').value = decision.status;
    document.getElementById('decision-change-note').value = '';
  },
};

document.addEventListener('DOMContentLoaded', () => DecisionManager.init());
