/**
 * TaskNest Task & Category Management Engine
 */

const TaskManager = {
  tasks: [],
  categories: [],
  currentFilter: {
    q: '',
    status: '',
    priority: '',
    category_id: '',
    sort: 'created_at_desc'
  },

  init() {
    this.bindEvents();
    this.loadCategories().then(() => {
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

    // Filters
    const filterStatus = document.getElementById('filter-status');
    if (filterStatus) {
      filterStatus.addEventListener('change', (e) => {
        this.currentFilter.status = e.target.value;
        this.loadTasks();
      });
    }

    const filterPriority = document.getElementById('filter-priority');
    if (filterPriority) {
      filterPriority.addEventListener('change', (e) => {
        this.currentFilter.priority = e.target.value;
        this.loadTasks();
      });
    }

    const filterCategory = document.getElementById('filter-category');
    if (filterCategory) {
      filterCategory.addEventListener('change', (e) => {
        this.currentFilter.category_id = e.target.value;
        this.loadTasks();
      });
    }

    const filterSort = document.getElementById('filter-sort');
    if (filterSort) {
      filterSort.addEventListener('change', (e) => {
        this.currentFilter.sort = e.target.value;
        this.loadTasks();
      });
    }

    const clearFiltersBtn = document.getElementById('clear-filters-btn');
    if (clearFiltersBtn) {
      clearFiltersBtn.addEventListener('click', () => {
        this.currentFilter = { q: '', status: '', priority: '', category_id: '', sort: 'created_at_desc' };
        if (searchInput) searchInput.value = '';
        if (filterStatus) filterStatus.value = '';
        if (filterPriority) filterPriority.value = '';
        if (filterCategory) filterCategory.value = '';
        if (filterSort) filterSort.value = 'created_at_desc';
        this.loadTasks();
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

    // Modal Close
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
      // Build query string
      const params = new URLSearchParams();
      if (this.currentFilter.q) params.set('q', this.currentFilter.q);
      if (this.currentFilter.status) params.set('status', this.currentFilter.status);
      if (this.currentFilter.priority) params.set('priority', this.currentFilter.priority);
      if (this.currentFilter.category_id) params.set('category_id', this.currentFilter.category_id);
      if (this.currentFilter.sort) params.set('sort', this.currentFilter.sort);

      // Support URL search param from global search
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
      this.renderTasks(this.tasks, container);

      // Refresh stats if on dashboard
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

      item.innerHTML = `
        <input type="checkbox" class="task-checkbox" ${isCompleted ? 'checked' : ''} aria-label="Toggle task status" />
        <div class="task-body">
          <div class="task-title">${this.escapeHtml(task.title)}</div>
          ${task.description ? `<div class="task-desc-preview">${this.escapeHtml(task.description)}</div>` : ''}
          <div class="task-meta">
            ${task.category_name ? `<span class="badge badge-category"><svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>${this.escapeHtml(task.category_name)}</span>` : ''}
            <span class="badge badge-${task.priority}">${task.priority}</span>
            <span class="badge badge-${task.status}">${task.status}</span>
            ${task.due_date ? `
              <span class="task-due-tag ${isOverdue ? 'is-overdue' : ''}">
                <svg class="icon icon-sm" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
                ${formattedDate} ${isOverdue ? '(Overdue)' : ''}
              </span>
            ` : ''}
          </div>
        </div>
        <div class="task-actions">
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
      checkbox.addEventListener('change', () => this.toggleTaskCompletion(task.id, checkbox.checked));

      // Edit event
      item.querySelector('.edit-task-btn').addEventListener('click', () => this.openTaskModal(task));

      // Delete event
      item.querySelector('.delete-task-btn').addEventListener('click', () => this.confirmDeleteTask(task));

      container.appendChild(item);
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
      this.loadTasks(); // Revert check state
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

      // Render upcoming panel if on dashboard
      const upcomingContainer = document.getElementById('dashboard-upcoming-list');
      if (upcomingContainer) {
        if (!stats.upcoming || stats.upcoming.length === 0) {
          upcomingContainer.innerHTML = '<p class="text-muted" style="font-size: var(--font-size-sm); padding: 1rem 0;">No upcoming tasks pending.</p>';
        } else {
          upcomingContainer.innerHTML = stats.upcoming.map(t => `
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.75rem 0; border-bottom: 1px solid var(--color-border-subtle);">
              <div>
                <div style="font-weight: 600; font-size: var(--font-size-sm); color: var(--color-text);">${this.escapeHtml(t.title)}</div>
                <div style="font-size: var(--font-size-xs); color: var(--color-muted);">${t.category_name || 'General'}</div>
              </div>
              <span class="badge ${t.is_overdue ? 'badge-overdue' : 'badge-low'}">
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

  openTaskModal(task = null) {
    const modal = document.getElementById('task-modal');
    if (!modal) return;

    const modalTitle = document.getElementById('task-modal-title');
    const taskIdField = document.getElementById('task-id');
    const titleField = document.getElementById('task-title-input');
    const descField = document.getElementById('task-desc-input');
    const priorityField = document.getElementById('task-priority-select');
    const statusField = document.getElementById('task-status-select');
    const categoryField = document.getElementById('task-category-select');
    const dueDateField = document.getElementById('task-due-date-input');

    if (task) {
      modalTitle.textContent = 'Edit Task';
      taskIdField.value = task.id;
      titleField.value = task.title;
      descField.value = task.description || '';
      priorityField.value = task.priority || 'medium';
      statusField.value = task.status || 'pending';
      categoryField.value = task.category_id || '';
      dueDateField.value = task.due_date ? task.due_date.split('T')[0] : '';
    } else {
      modalTitle.textContent = 'Add New Task';
      taskIdField.value = '';
      titleField.value = '';
      descField.value = '';
      priorityField.value = 'medium';
      statusField.value = 'pending';
      categoryField.value = '';
      dueDateField.value = '';
    }

    modal.classList.add('is-active');
    setTimeout(() => titleField.focus(), 50);
  },

  async handleTaskFormSubmit(e) {
    e.preventDefault();
    const taskId = document.getElementById('task-id').value;
    const title = document.getElementById('task-title-input').value.trim();
    const description = document.getElementById('task-desc-input').value.trim();
    const priority = document.getElementById('task-priority-select').value;
    const status = document.getElementById('task-status-select').value;
    const categoryId = document.getElementById('task-category-select').value;
    const dueDate = document.getElementById('task-due-date-input').value;

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
      due_date: dueDate || null
    };

    const submitBtn = e.target.querySelector('button[type="submit"]');
    submitBtn.disabled = true;

    try {
      if (taskId) {
        await api('PUT', `/tasks/${taskId}`, payload);
        showToast('Task updated successfully!', 'success');
      } else {
        await api('POST', '/tasks', payload);
        showToast('Task created successfully!', 'success');
      }
      this.closeModals();
      this.loadTasks();
      this.loadDashboardStats();
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
          <h3>No categories created</h3>
          <p>Organize your tasks by creating categories like Work, Personal, or Projects.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = `
      <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem;">
        ${this.categories.map(cat => `
          <div class="card" style="display: flex; align-items: center; justify-content: space-between; padding: 1.25rem;">
            <div>
              <div style="font-weight: 700; font-size: var(--font-size-base); color: var(--color-primary);">${this.escapeHtml(cat.name)}</div>
              <div style="font-size: var(--font-size-xs); color: var(--color-muted); margin-top: 0.25rem;">
                ${cat.task_count ?? 0} associated tasks
              </div>
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
        const ok = window.confirm(`Delete category "${catName}"? Tasks in this category will remain safe and be unassigned.`);
        if (ok) {
          this.deleteCategory(catId);
        }
      });
    });
  },

  async handleCategoryFormSubmit(e) {
    e.preventDefault();
    const nameInput = document.getElementById('new-category-name');
    const name = nameInput.value.trim();
    if (!name) {
      showToast('Please enter a category name.', 'error');
      return;
    }

    try {
      await api('POST', '/categories', { name });
      showToast(`Category "${name}" created!`, 'success');
      nameInput.value = '';
      await this.loadCategories();
      this.renderCategoriesPage();
    } catch (err) {
      showToast(err.message || 'Failed to create category', 'error');
    }
  },

  async deleteCategory(catId) {
    try {
      await api('DELETE', `/categories/${catId}`);
      showToast('Category deleted and tasks unassigned safely.', 'success');
      await this.loadCategories();
      this.renderCategoriesPage();
    } catch (err) {
      showToast(err.message || 'Failed to delete category', 'error');
    }
  },

  closeModals() {
    document.querySelectorAll('.modal-overlay').forEach(modal => {
      modal.classList.remove('is-active');
    });
  },

  escapeHtml(str) {
    if (!str) return '';
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
};

document.addEventListener('DOMContentLoaded', () => {
  TaskManager.init();
});
