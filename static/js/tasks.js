/**
 * TaskNest Enterprise Task & Category Management Engine
 */

const TaskManager = {
  tasks: [],
  categories: [],
  teams: [],
  employees: [],
  currentFilter: {
    q: '',
    scope: '',
    status: '',
    priority: '',
    category_id: '',
    team_id: '',
    sort: 'created_at_desc'
  },

  init() {
    this.bindEvents();
    Promise.all([
      this.loadCategories(),
      this.loadTeams(),
      this.loadEmployees()
    ]).then(() => {
      if (document.getElementById('task-list-container')) {
        this.loadTasks();
      }
      if (document.getElementById('dashboard-metrics')) {
        this.loadDashboardStats();
      }
      if (document.getElementById('categories-list-container')) {
        this.renderCategoriesPage();
      }
    });
  },

  bindEvents() {
    // Search input with debounce
    const searchInput = document.getElementById('task-search');
    if (searchInput) {
      let debounceTimeout;
      searchInput.addEventListener('input', (e) => {
        clearTimeout(debounceTimeout);
        debounceTimeout = setTimeout(() => {
          this.currentFilter.q = e.target.value.trim();
          this.loadTasks();
        }, 250);
      });
    }

    // Global Header Search
    const globalSearch = document.getElementById('global-search');
    if (globalSearch) {
      globalSearch.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const query = globalSearch.value.trim();
          window.location.href = `/tasks?q=${encodeURIComponent(query)}`;
        }
      });
    }

    // Scope Filter
    const filterScope = document.getElementById('filter-scope');
    if (filterScope) {
      filterScope.addEventListener('change', (e) => {
        this.currentFilter.scope = e.target.value;
        this.loadTasks();
      });
    }

    // Status Filter
    const filterStatus = document.getElementById('filter-status');
    if (filterStatus) {
      filterStatus.addEventListener('change', (e) => {
        this.currentFilter.status = e.target.value;
        this.loadTasks();
      });
    }

    // Priority Filter
    const filterPriority = document.getElementById('filter-priority');
    if (filterPriority) {
      filterPriority.addEventListener('change', (e) => {
        this.currentFilter.priority = e.target.value;
        this.loadTasks();
      });
    }

    // Category Filter
    const filterCategory = document.getElementById('filter-category');
    if (filterCategory) {
      filterCategory.addEventListener('change', (e) => {
        this.currentFilter.category_id = e.target.value;
        this.loadTasks();
      });
    }

    // Team Filter
    const filterTeam = document.getElementById('filter-team');
    if (filterTeam) {
      filterTeam.addEventListener('change', (e) => {
        this.currentFilter.team_id = e.target.value;
        this.loadTasks();
      });
    }

    // Sort Filter
    const filterSort = document.getElementById('filter-sort');
    if (filterSort) {
      filterSort.addEventListener('change', (e) => {
        this.currentFilter.sort = e.target.value;
        this.loadTasks();
      });
    }

    // Reset Filters
    const clearFiltersBtn = document.getElementById('clear-filters-btn');
    if (clearFiltersBtn) {
      clearFiltersBtn.addEventListener('click', () => {
        this.currentFilter = { q: '', scope: '', status: '', priority: '', category_id: '', team_id: '', sort: 'created_at_desc' };
        if (searchInput) searchInput.value = '';
        if (filterScope) filterScope.value = '';
        if (filterStatus) filterStatus.value = '';
        if (filterPriority) filterPriority.value = '';
        if (filterCategory) filterCategory.value = '';
        if (filterTeam) filterTeam.value = '';
        if (filterSort) filterSort.value = 'created_at_desc';
        this.loadTasks();
      });
    }

    // View Mode Switcher
    const listBtn = document.getElementById('view-mode-list-btn');
    const kanbanBtn = document.getElementById('view-mode-kanban-btn');
    const listContainer = document.getElementById('task-list-container');
    const kanbanContainer = document.getElementById('kanban-container');

    if (listBtn && kanbanBtn) {
      listBtn.addEventListener('click', () => {
        this.viewMode = 'list';
        listBtn.classList.add('active');
        listBtn.style.backgroundColor = 'var(--color-surface-subtle)';
        listBtn.style.color = 'var(--color-primary)';
        kanbanBtn.classList.remove('active');
        kanbanBtn.style.backgroundColor = 'transparent';
        kanbanBtn.style.color = 'var(--color-text)';
        if (listContainer) listContainer.style.display = 'block';
        if (kanbanContainer) kanbanContainer.style.display = 'none';
      });

      kanbanBtn.addEventListener('click', () => {
        this.viewMode = 'kanban';
        kanbanBtn.classList.add('active');
        kanbanBtn.style.backgroundColor = 'var(--color-surface-subtle)';
        kanbanBtn.style.color = 'var(--color-primary)';
        listBtn.classList.remove('active');
        listBtn.style.backgroundColor = 'transparent';
        listBtn.style.color = 'var(--color-text)';
        if (listContainer) listContainer.style.display = 'none';
        if (kanbanContainer) kanbanContainer.style.display = 'block';
        this.renderKanban(this.tasks);
      });
    }

    // Add Task Button
    document.querySelectorAll('.open-add-task-btn').forEach(btn => {
      btn.addEventListener('click', () => this.openTaskModal());
    });

    // Task Form Submit
    const taskForm = document.getElementById('task-form');
    if (taskForm) {
      taskForm.addEventListener('submit', (e) => this.handleTaskFormSubmit(e));
    }

    // Category Form Submit
    const catForm = document.getElementById('category-form');
    if (catForm) {
      catForm.addEventListener('submit', (e) => this.handleCategoryFormSubmit(e));
    }

    // Subtask Form Submit
    const subtaskForm = document.getElementById('add-subtask-form');
    if (subtaskForm) {
      subtaskForm.addEventListener('submit', (e) => this.handleAddSubtask(e));
    }

    // Send Message Form Submit
    const msgForm = document.getElementById('send-message-form');
    if (msgForm) {
      msgForm.addEventListener('submit', (e) => this.handleSendMessage(e));
    }

    // Submit Deliverable Form Submit
    const deliverableForm = document.getElementById('submit-deliverable-form');
    if (deliverableForm) {
      deliverableForm.addEventListener('submit', (e) => this.handleSubmitDeliverable(e));
    }

    // Modal Close Triggers
    document.querySelectorAll('.modal-close-trigger').forEach(el => {
      el.addEventListener('click', () => this.closeModals());
    });

    // Close on Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.closeModals();
    });
  },

  async loadCategories() {
    try {
      const res = await api('GET', '/categories');
      this.categories = res.data || [];
      this.populateCategoryDropdowns();
    } catch (err) {
      console.error('Failed to load categories', err);
    }
  },

  async loadTeams() {
    try {
      const res = await api('GET', '/teams');
      this.teams = res.data || [];
      this.populateTeamDropdowns();
    } catch (err) {
      // Teams endpoint may return empty if none created yet
      this.teams = [];
    }
  },

  async loadEmployees() {
    try {
      const res = await api('GET', '/employees');
      this.employees = res.data || [];
      this.populateAssigneeDropdown();
    } catch (err) {
      this.employees = [];
    }
  },

  populateCategoryDropdowns() {
    const selects = [
      document.getElementById('filter-category'),
      document.getElementById('task-category-select')
    ];

    selects.forEach(select => {
      if (!select) return;
      const isFilter = select.id === 'filter-category';
      const currentVal = select.value;

      select.innerHTML = isFilter
        ? '<option value="">All Categories</option>'
        : '<option value="">No Category</option>';

      this.categories.forEach(cat => {
        const opt = document.createElement('option');
        opt.value = cat.id;
        opt.textContent = cat.name;
        select.appendChild(opt);
      });

      if (currentVal) select.value = currentVal;
    });
  },

  populateTeamDropdowns() {
    const filterTeam = document.getElementById('filter-team');
    if (filterTeam) {
      const cur = filterTeam.value;
      filterTeam.innerHTML = '<option value="">All Teams</option>';
      this.teams.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.id;
        opt.textContent = t.name;
        filterTeam.appendChild(opt);
      });
      if (cur) filterTeam.value = cur;
    }

    const modalTeam = document.getElementById('task-team-select');
    if (modalTeam) {
      const cur = modalTeam.value;
      modalTeam.innerHTML = '<option value="">No Team (Personal Task)</option>';
      this.teams.forEach(t => {
        const opt = document.createElement('option');
        opt.value = t.id;
        opt.textContent = t.name;
        modalTeam.appendChild(opt);
      });
      if (cur) modalTeam.value = cur;
    }
  },

  populateAssigneeDropdown() {
    const select = document.getElementById('task-assignee-select');
    if (!select) return;

    const cur = select.value;
    select.innerHTML = '<option value="">Unassigned (Self / Open)</option>';
    this.employees.forEach(emp => {
      const opt = document.createElement('option');
      opt.value = emp.id;
      opt.textContent = `${emp.full_name || emp.username} (${emp.role.replace('_', ' ')})`;
      select.appendChild(opt);
    });
    if (cur) select.value = cur;
  },

  async loadTasks() {
    const container = document.getElementById('task-list-container');
    if (!container) return;

    container.innerHTML = `
      <div style="text-align: center; padding: 2.5rem; color: var(--color-muted);">
        <svg class="icon icon-lg" viewBox="0 0 24 24" style="animation: spin 1s linear infinite;"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>
        <p style="margin-top: 0.5rem; font-size: var(--font-size-sm);">Loading tasks...</p>
      </div>
    `;

    try {
      const params = new URLSearchParams();
      if (this.currentFilter.q) params.set('q', this.currentFilter.q);
      if (this.currentFilter.scope) params.set('scope', this.currentFilter.scope);
      if (this.currentFilter.status) params.set('status', this.currentFilter.status);
      if (this.currentFilter.priority) params.set('priority', this.currentFilter.priority);
      if (this.currentFilter.category_id) params.set('category_id', this.currentFilter.category_id);
      if (this.currentFilter.team_id) params.set('team_id', this.currentFilter.team_id);
      if (this.currentFilter.sort) params.set('sort', this.currentFilter.sort);

      const urlParams = new URLSearchParams(window.location.search);
      const urlQ = urlParams.get('q');
      if (urlQ && !this.currentFilter.q) {
        this.currentFilter.q = urlQ;
        params.set('q', urlQ);
        const searchInput = document.getElementById('task-search');
        if (searchInput) searchInput.value = urlQ;
      }

      const res = await api('GET', `/tasks?${params.toString()}`);
      this.tasks = res.data || [];
      this.renderSmartPriority(this.tasks);
      this.renderTasks(this.tasks, container);
      this.renderKanban(this.tasks);

      if (document.getElementById('dashboard-metrics')) {
        this.loadDashboardStats();
      }
    } catch (err) {
      container.innerHTML = `
        <div class="alert alert-danger">
          <svg class="icon" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
          <span>Error loading tasks: ${err.message}</span>
        </div>
      `;
    }
  },

  getStatusBadgeClass(status) {
    switch (status) {
      case 'completed':
        return 'badge-success';
      case 'in_progress':
        return 'badge-primary';
      case 'in_review':
        return 'badge-warning';
      case 'changes_requested':
      case 'blocked':
        return 'badge-danger';
      case 'todo':
      case 'pending':
      default:
        return 'badge-neutral';
    }
  },

  renderTasks(tasks, container) {
    if (!tasks || tasks.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon-wrap">
            <svg class="icon icon-xl" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
          </div>
          <h3>No tasks found</h3>
          <p>Get started by creating a new task, or adjust your active search and filters.</p>
          <button class="btn btn-primary open-add-task-btn">
            <svg class="icon" viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
            Add New Task
          </button>
        </div>
      `;
      container.querySelector('.open-add-task-btn')?.addEventListener('click', () => this.openTaskModal());
      return;
    }

    container.innerHTML = '';
    tasks.forEach(task => {
      const isCompleted = task.status === 'completed';
      const isOverdue = task.is_overdue;

      const item = document.createElement('div');
      item.className = `task-item ${isCompleted ? 'is-completed' : ''}`;
      item.id = `task-row-${task.id}`;

      let formattedDate = 'No date';
      if (task.due_date) {
        const [y, m, d] = task.due_date.split('-');
        const dateObj = new Date(y, m - 1, d);
        formattedDate = dateObj.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
      }

      const statusLabel = task.status_label || task.status.replace('_', ' ').toUpperCase();
      const statusClass = this.getStatusBadgeClass(task.status);

      item.innerHTML = `
        <input type="checkbox" class="task-checkbox" ${isCompleted ? 'checked' : ''} aria-label="Toggle task status" />
        <div class="task-body">
          <div class="task-title">
            <a href="/tasks/${task.id}" class="task-title-link" style="color: inherit; text-decoration: none;">
              ${this.escapeHtml(task.title)}
            </a>
          </div>
          ${task.description ? `<div class="task-desc-preview">${this.escapeHtml(task.description)}</div>` : ''}
          <div class="task-meta">
            ${task.team_name ? `<span class="badge badge-neutral" title="Team"><svg class="icon icon-sm" viewBox="0 0 24 24"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>${this.escapeHtml(task.team_name)}</span>` : ''}
            ${task.assigned_to_name ? `<span class="badge badge-neutral" title="Assignee"><svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>${this.escapeHtml(task.assigned_to_name)}</span>` : ''}
            ${task.category_name ? `<span class="badge badge-category"><svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>${this.escapeHtml(task.category_name)}</span>` : ''}
            <span class="badge badge-${task.priority}">${task.priority.toUpperCase()}</span>
            <span class="badge ${statusClass}">${statusLabel}</span>
            ${task.due_date ? `
              <span class="task-due-tag ${isOverdue ? 'is-overdue' : ''}">
                <svg class="icon icon-sm" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
                ${formattedDate} ${isOverdue ? '(Overdue)' : ''}
              </span>
            ` : ''}
          </div>
        </div>
        <div class="task-actions">
          <a href="/tasks/${task.id}" class="btn btn-ghost btn-sm btn-icon-only" title="View Details" aria-label="View Details">
            <svg class="icon" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          </a>
          <button class="btn btn-ghost btn-sm btn-icon-only edit-task-btn" title="Edit Task" aria-label="Edit Task">
            <svg class="icon" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
          </button>
          <button class="btn btn-ghost btn-sm btn-icon-only text-danger delete-task-btn" title="Delete Task" aria-label="Delete Task">
            <svg class="icon" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
          </button>
        </div>
      `;

      // Checkbox event
      const checkbox = item.querySelector('.task-checkbox');
      checkbox.addEventListener('change', (e) => {
        e.stopPropagation();
        this.toggleTaskCompletion(task.id, checkbox.checked);
      });

      // Clicking task body opens detail modal
      item.querySelector('.task-body').addEventListener('click', () => {
        this.openTaskDetailModal(task);
      });
      item.querySelector('.view-detail-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        this.openTaskDetailModal(task);
      });

      // Edit event
      item.querySelector('.edit-task-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        this.openTaskModal(task);
      });

      // Delete event
      item.querySelector('.delete-task-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        this.confirmDeleteTask(task);
      });

      container.appendChild(item);
    });
  },

  renderKanban(tasks) {
    const kanbanContainer = document.getElementById('kanban-container');
    if (!kanbanContainer) return;

    const cols = {
      pending: document.getElementById('kanban-pending'),
      in_progress: document.getElementById('kanban-in_progress'),
      blocked: document.getElementById('kanban-blocked'),
      in_review: document.getElementById('kanban-in_review'),
      completed: document.getElementById('kanban-completed')
    };

    const counts = {
      pending: document.getElementById('kanban-count-pending'),
      in_progress: document.getElementById('kanban-count-in_progress'),
      blocked: document.getElementById('kanban-count-blocked'),
      in_review: document.getElementById('kanban-count-in_review'),
      completed: document.getElementById('kanban-count-completed')
    };

    Object.values(cols).forEach(col => { if (col) col.innerHTML = ''; });
    const colCounters = { pending: 0, in_progress: 0, blocked: 0, in_review: 0, completed: 0 };

    tasks.forEach(task => {
      let colKey = task.status;
      if (colKey === 'todo') colKey = 'pending';
      if (colKey === 'changes_requested') colKey = 'in_review';
      if (!cols[colKey]) colKey = 'pending';

      colCounters[colKey]++;

      const card = document.createElement('div');
      card.className = 'card';
      card.style.cssText = 'padding: 0.85rem; cursor: pointer; border-radius: var(--radius-sm); border: 1px solid var(--color-border); box-shadow: var(--shadow-sm); transition: transform 0.15s ease;';
      card.innerHTML = `
        <div style="font-weight: 700; font-size: var(--font-size-sm); color: var(--color-text); margin-bottom: 0.35rem;">
          ${this.escapeHtml(task.title)}
        </div>
        ${task.description ? `<p style="font-size: var(--font-size-xs); color: var(--color-muted); margin: 0 0 0.5rem 0; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">${this.escapeHtml(task.description)}</p>` : ''}
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.35rem; font-size: var(--font-size-xs);">
          <span class="badge badge-${task.priority}">${task.priority}</span>
          ${task.due_date ? `<span style="color: var(--color-muted); font-size: 0.7rem;">📅 ${task.due_date}</span>` : ''}
        </div>
        ${task.assignee_name ? `<div style="font-size: 0.7rem; color: var(--color-muted); margin-top: 0.4rem;">👤 ${this.escapeHtml(task.assignee_name)}</div>` : ''}
      `;

      card.addEventListener('mouseenter', () => { card.style.transform = 'translateY(-2px)'; });
      card.addEventListener('mouseleave', () => { card.style.transform = 'translateY(0)'; });
      card.addEventListener('click', () => this.openTaskDetailModal(task));

      if (cols[colKey]) {
        cols[colKey].appendChild(card);
      }
    });

    Object.keys(counts).forEach(k => {
      if (counts[k]) counts[k].textContent = colCounters[k];
    });
  },

  async toggleTaskCompletion(taskId, isChecked) {
    try {
      await api('PATCH', `/tasks/${taskId}/complete`, {
        status: isChecked ? 'completed' : 'pending'
      });
      showToast(isChecked ? 'Task marked as completed!' : 'Task reopened.', 'success');
      this.loadTasks();
    } catch (err) {
      showToast(err.message || 'Failed to update task status', 'error');
      this.loadTasks();
    }
  },

  async loadDashboardStats() {
    try {
      const res = await api('GET', '/stats');
      const stats = res.data;

      const totalEl = document.getElementById('stat-total');
      const pendingEl = document.getElementById('stat-pending');
      const completedEl = document.getElementById('stat-completed');
      const overdueEl = document.getElementById('stat-overdue');
      const rateEl = document.getElementById('stat-completion-rate');

      if (totalEl) totalEl.textContent = stats.total ?? 0;
      if (pendingEl) pendingEl.textContent = stats.pending ?? 0;
      if (completedEl) completedEl.textContent = stats.completed ?? 0;
      if (overdueEl) overdueEl.textContent = stats.overdue ?? 0;
      if (rateEl) rateEl.textContent = `${stats.completion_rate ?? 0}%`;

      const upcomingContainer = document.getElementById('dashboard-upcoming-list');
      if (upcomingContainer) {
        if (!stats.upcoming || stats.upcoming.length === 0) {
          upcomingContainer.innerHTML = '<p class="text-muted" style="font-size: var(--font-size-sm); padding: 1rem 0;">No upcoming tasks pending.</p>';
        } else {
          upcomingContainer.innerHTML = stats.upcoming.map(t => `
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.75rem 0; border-bottom: 1px solid var(--color-border-subtle);">
              <div>
                <a href="/tasks/${t.id}" style="font-weight: 600; font-size: var(--font-size-sm); color: var(--color-text); text-decoration: none;">
                  ${this.escapeHtml(t.title)}
                </a>
                <div style="font-size: var(--font-size-xs); color: var(--color-muted);">
                  ${t.team_name ? `[${this.escapeHtml(t.team_name)}] ` : ''}${t.category_name || 'General'}
                </div>
              </div>
              <span class="badge ${t.is_overdue ? 'badge-danger' : 'badge-neutral'}">
                ${t.due_date ? t.due_date : 'No date'}
              </span>
            </div>
          `).join('');
        }
      }
    } catch (err) {
      console.error('Failed to load dashboard stats', err);
    }
  },

  async openEditModal(taskId) {
    try {
      const res = await api('GET', `/tasks/${taskId}`);
      if (res && res.ok) {
        this.openTaskModal(res.data);
      }
    } catch (err) {
      showToast('Could not load task for editing.', 'error');
    }
  },

  openTaskModal(task = null) {
    const modal = document.getElementById('task-modal');
    if (!modal) return;

    const modalTitle = document.getElementById('task-modal-title');
    const taskIdField = document.getElementById('task-id');
    const titleField = document.getElementById('task-title-input');
    const descField = document.getElementById('task-desc-input');
    const criteriaField = document.getElementById('task-criteria-input');
    const priorityField = document.getElementById('task-priority-select');
    const statusField = document.getElementById('task-status-select');
    const teamField = document.getElementById('task-team-select');
    const assigneeField = document.getElementById('task-assignee-select');
    const startDateField = document.getElementById('task-start-date-input');
    const dueDateField = document.getElementById('task-due-date-input');
    const categoryField = document.getElementById('task-category-select');
    const recurringField = document.getElementById('task-recurring-select');

    const refFilesField = document.getElementById('task-modal-ref-files');
    if (refFilesField) refFilesField.value = '';

    if (task) {
      modalTitle.textContent = 'Edit Task';
      taskIdField.value = task.id;
      titleField.value = task.title;
      descField.value = task.description || '';
      if (criteriaField) criteriaField.value = task.acceptance_criteria || '';
      priorityField.value = task.priority || 'medium';
      statusField.value = task.status || 'todo';
      if (teamField) teamField.value = task.team_id || '';
      if (assigneeField) assigneeField.value = task.assigned_to_id || '';
      if (startDateField) startDateField.value = task.start_date ? task.start_date.split('T')[0] : '';
      if (dueDateField) dueDateField.value = task.due_date ? task.due_date.split('T')[0] : '';
      if (categoryField) categoryField.value = task.category_id || '';
      if (recurringField) recurringField.value = task.recurrence_interval || '';
    } else {
      modalTitle.textContent = 'Add New Task';
      taskIdField.value = '';
      titleField.value = '';
      descField.value = '';
      if (criteriaField) criteriaField.value = '';
      priorityField.value = 'medium';
      statusField.value = 'todo';
      if (teamField) teamField.value = '';
      if (assigneeField) assigneeField.value = '';
      if (startDateField) startDateField.value = '';
      if (dueDateField) dueDateField.value = '';
      if (categoryField) categoryField.value = '';
      if (recurringField) recurringField.value = '';
    }

    modal.classList.add('is-active');
    modal.classList.add('active');
    setTimeout(() => titleField.focus(), 50);
  },

  closeModals() {
    document.querySelectorAll('.modal-overlay').forEach(modal => {
      modal.classList.remove('is-active');
      modal.classList.remove('active');
    });
  },

  async handleTaskFormSubmit(e) {
    e.preventDefault();
    const taskId = document.getElementById('task-id').value;
    const title = document.getElementById('task-title-input').value.trim();
    const description = document.getElementById('task-desc-input').value.trim();
    const priority = document.getElementById('task-priority-select').value;
    const status = document.getElementById('task-status-select').value;
    const categoryId = document.getElementById('task-category-select')?.value;
    const dueDate = document.getElementById('task-due-date-input')?.value;

    const criteria = document.getElementById('task-criteria-input')?.value.trim() || '';
    const teamId = document.getElementById('task-team-select')?.value;
    const assigneeId = document.getElementById('task-assignee-select')?.value;
    const startDate = document.getElementById('task-start-date-input')?.value;
    const recurring = document.getElementById('task-recurring-select')?.value;

    if (!title) {
      showToast('Task title is required.', 'error');
      return;
    }

    const payload = {
      title,
      description,
      priority,
      status,
      category_id: categoryId ? parseInt(categoryId, 10) : null,
      team_id: teamId ? parseInt(teamId, 10) : null,
      assigned_to_id: assigneeId ? parseInt(assigneeId, 10) : null,
      start_date: startDate || null,
      due_date: dueDate || null,
      acceptance_criteria: criteria,
      is_recurring: Boolean(recurring),
      recurrence_interval: recurring || null
    };

    if (assigneeField && assigneeField.value) {
      payload.assignee_id = parseInt(assigneeField.value, 10);
    }
    if (recurrenceField && recurrenceField.value) {
      payload.recurrence = recurrenceField.value;
    }
    if (criteriaField && criteriaField.value.trim()) {
      payload.acceptance_criteria = criteriaField.value.trim();
    }

    const submitBtn = e.target.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    try {
      const refFilesInput = document.getElementById('task-modal-ref-files');
      if (taskId) {
        await api('PUT', `/tasks/${taskId}`, payload);
        if (refFilesInput && refFilesInput.files && refFilesInput.files.length > 0) {
          for (let i = 0; i < refFilesInput.files.length; i++) {
            const fd = new FormData();
            fd.append('file', refFilesInput.files[i]);
            await api('POST', `/tasks/${taskId}/attachments`, fd);
          }
        }
        showToast('Task updated successfully!', 'success');
      } else {
        if (refFilesInput && refFilesInput.files && refFilesInput.files.length > 0) {
          const formData = new FormData();
          Object.keys(payload).forEach(key => {
            if (payload[key] !== null && payload[key] !== undefined) {
              formData.append(key, payload[key]);
            }
          });
          for (let i = 0; i < refFilesInput.files.length; i++) {
            formData.append('files', refFilesInput.files[i]);
          }
          await api('POST', '/tasks', formData);
        } else {
          await api('POST', '/tasks', payload);
        }
        showToast('Task created successfully!', 'success');
      }
      this.closeModals();
      this.loadTasks();
      this.loadDashboardStats();

      // If on detail page, refresh
      if (window.TaskDetail && typeof window.TaskDetail.init === 'function') {
        window.TaskDetail.init();
      }
    } catch (err) {
      showToast(err.message || 'Failed to save task', 'error');
    } finally {
      submitBtn.disabled = false;
    }
  },

  confirmDeleteTask(task) {
    const confirmed = window.confirm(`Are you sure you want to delete task "${task.title}"? This cannot be undone.`);
    if (confirmed) {
      this.deleteTask(task.id);
    }
  },

  async deleteTask(taskId) {
    try {
      await api('DELETE', `/tasks/${taskId}`);
      showToast('Task deleted successfully.', 'success');
      this.loadTasks();
      this.loadDashboardStats();
    } catch (err) {
      showToast(err.message || 'Failed to delete task', 'error');
    }
  },

  escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },

  // Category page methods
  renderCategoriesPage() {
    const container = document.getElementById('categories-list-container');
    if (!container) return;

    if (this.categories.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon-wrap">
            <svg class="icon icon-xl" viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
          </div>
          <h3>No categories yet</h3>
          <p>Create categories to group, organize, and sort your tasks easily.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = `
      <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem;">
        ${this.categories.map(cat => `
          <div class="card" style="display: flex; align-items: center; justify-content: space-between;">
            <div>
              <div style="font-weight: 700; color: var(--color-text);">${this.escapeHtml(cat.name)}</div>
              <div style="font-size: var(--font-size-xs); color: var(--color-muted);">${cat.task_count ?? 0} associated tasks</div>
            </div>
            <button class="btn btn-ghost btn-sm btn-icon-only text-danger delete-cat-btn" data-id="${cat.id}" data-name="${this.escapeHtml(cat.name)}" title="Delete Category">
              <svg class="icon" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
            </button>
          </div>
        `).join('')}
      </div>
    `;

    container.querySelectorAll('.delete-cat-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const catId = btn.getAttribute('data-id');
        const catName = btn.getAttribute('data-name');
        if (confirm(`Delete category "${catName}"? Tasks in this category will become unassigned.`)) {
          this.deleteCategory(catId);
        }
      });
    });
  },

  async handleCategoryFormSubmit(e) {
    e.preventDefault();
    const input = document.getElementById('category-name-input');
    const name = input?.value.trim();
    if (!name) return;

    try {
      await api('POST', '/categories', { name });
      showToast('Category created!', 'success');
      if (input) input.value = '';
      await this.loadCategories();
      this.renderCategoriesPage();
    } catch (err) {
      showToast(err.message || 'Failed to create category', 'error');
    }
  },

  async deleteCategory(catId) {
    try {
      await api('DELETE', `/categories/${catId}`);
      showToast('Category deleted.', 'success');
      await this.loadCategories();
      this.renderCategoriesPage();
    } catch (err) {
      showToast(err.message || 'Failed to delete category', 'error');
    }
  }
};

window.TaskManager = TaskManager;

document.addEventListener('DOMContentLoaded', () => {
  TaskManager.init();
});
