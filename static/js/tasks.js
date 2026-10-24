/**
 * TaskNest Enterprise Task & Category Management Engine
 */

const TaskManager = {
  tasks: [],
  categories: [],
  employees: [],
  activeTaskId: null,
  viewMode: 'list', // 'list' | 'kanban'
  currentFilter: {
    q: '',
    status: '',
    priority: '',
    category_id: '',
    sort: 'created_at_desc'
  },

  init() {
    // If no view-mode toggle exists (employee role), default directly to kanban
    if (!document.getElementById('view-mode-list-btn') && document.getElementById('kanban-container')) {
      this.viewMode = 'kanban';
      const lc = document.getElementById('task-list-container');
      const kc = document.getElementById('kanban-container');
      if (lc) lc.style.display = 'none';
      if (kc) kc.style.display = 'block';
    }

    this.bindEvents();
    this.loadCategories().then(() => {
      this.loadEmployeesList();
      if (document.getElementById('task-list-container') || document.getElementById('kanban-container')) {
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

    const filterType = document.getElementById('filter-type');
    if (filterType) {
      filterType.addEventListener('change', (e) => {
        this.currentFilter.type = e.target.value;
        this.loadTasks();
      });
    }

    const clearFiltersBtn = document.getElementById('clear-filters-btn');
    if (clearFiltersBtn) {
      clearFiltersBtn.addEventListener('click', () => {
        this.currentFilter = { q: '', status: '', priority: '', category_id: '', type: '', sort: 'created_at_desc' };
        if (searchInput) searchInput.value = '';
        if (filterStatus) filterStatus.value = '';
        if (filterPriority) filterPriority.value = '';
        if (filterCategory) filterCategory.value = '';
        if (filterType) filterType.value = '';
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
    } else if (kanbanContainer) {
      // Default directly to kanban when list/kanban toggle is not rendered (employee view)
      this.viewMode = 'kanban';
      if (listContainer) listContainer.style.display = 'none';
      kanbanContainer.style.display = 'block';
    }

    // Add Task Button
    document.querySelectorAll('.open-add-task-btn').forEach(btn => {
      btn.addEventListener('click', () => this.openTaskModal());
    });

    // Personal Task Modal Button
    const personalTaskBtn = document.getElementById('open-personal-task-btn');
    if (personalTaskBtn) {
      personalTaskBtn.addEventListener('click', () => {
        const modal = document.getElementById('personal-task-modal');
        if (modal) modal.classList.add('is-active');
      });
    }

    // Personal Task Form Submit
    const personalTaskForm = document.getElementById('personal-task-form');
    if (personalTaskForm) {
      personalTaskForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const title = document.getElementById('personal-task-title-input').value.trim();
        if (!title) return;
        const description = document.getElementById('personal-task-desc-input').value.trim();
        const priority = document.getElementById('personal-task-priority-input').value;
        const due_date = document.getElementById('personal-task-due-input').value;
        const start_date = document.getElementById('personal-task-start-input').value;
        const ref_link = document.getElementById('personal-task-ref-input').value.trim();
        const subtasksRaw = document.getElementById('personal-task-subtasks-input').value;
        const subtasks = subtasksRaw.split('\n').map(s => s.trim()).filter(Boolean);

        let fullDesc = description;
        if (ref_link) {
          fullDesc = fullDesc ? `${fullDesc}\n\nReference: ${ref_link}` : `Reference: ${ref_link}`;
        }

        const saveBtn = document.getElementById('save-personal-task-btn');
        if (saveBtn) saveBtn.disabled = true;

        try {
          await api('POST', '/tasks', {
            title,
            description: fullDesc,
            priority,
            due_date: due_date || null,
            start_date: start_date || null,
            is_personal: true,
            subtasks
          });
          showToast('Personal task created successfully!', 'success');
          document.getElementById('personal-task-modal')?.classList.remove('is-active');
          personalTaskForm.reset();
          this.loadTasks();
        } catch (err) {
          showToast(err.message || 'Failed to create personal task', 'error');
        } finally {
          if (saveBtn) saveBtn.disabled = false;
        }
      });
    }

    // Block Reason Form Submit
    const blockReasonForm = document.getElementById('block-reason-form');
    if (blockReasonForm) {
      blockReasonForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const taskId = document.getElementById('block-task-id').value;
        const reason = document.getElementById('block-reason-input').value.trim();
        if (!taskId || !reason) return;

        try {
          await api('PATCH', `/tasks/${taskId}`, {
            status: 'blocked',
            block_reason: reason,
            comment: `Blocked: ${reason}`
          });
          showToast('Task marked as blocked', 'success');
          document.getElementById('block-reason-modal')?.classList.remove('is-active');
          blockReasonForm.reset();
          this.loadTasks();
        } catch (err) {
          showToast(err.message || 'Failed to block task', 'error');
        }
      });
    }

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

  async loadEmployeesList() {
    try {
      const res = await fetch('/api/employees');
      if (res.ok) {
        const json = await res.json();
        this.employees = Array.isArray(json.data) ? json.data : (json.data?.employees || []);
        const assigneeSelect = document.getElementById('task-assignee-select');
        if (assigneeSelect) {
          const currentVal = assigneeSelect.value;
          assigneeSelect.innerHTML = '<option value="">Unassigned (Assign to Self)</option>' +
            this.employees.map(e => `<option value="${e.id}">${e.full_name || e.username} (@${e.username})</option>`).join('');
          if (currentVal) assigneeSelect.value = currentVal;
        }
      }
    } catch (e) {
      console.error('Failed to load employees for assignee dropdown', e);
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

  renderSmartPriority(tasks) {
    const summary = document.getElementById('smart-priority-summary');
    const list = document.getElementById('smart-priority-list');
    if (!summary || !list) return;
    const now = new Date();
    const openTasks = (Array.isArray(tasks) ? tasks : []).filter(task => !['completed', 'cancelled'].includes(String(task.status || '').toLowerCase()));
    const priorityWeight = { urgent: 100, high: 75, medium: 45, low: 20 };
    const score = task => {
      let result = priorityWeight[String(task.priority || 'medium').toLowerCase()] || 45;
      if (task.due_date) {
        const due = new Date(`${String(task.due_date).slice(0, 10)}T23:59:59`);
        const days = Math.ceil((due.getTime() - now.getTime()) / 86400000);
        if (days < 0) result += 60;
        else if (days === 0) result += 45;
        else if (days <= 2) result += 25;
        else if (days <= 7) result += 10;
      }
      if (String(task.status || '').toLowerCase() === 'blocked') result += 15;
      return result;
    };
    openTasks.sort((a, b) => score(b) - score(a));
    if (!openTasks.length) {
      summary.textContent = 'You are all caught up. No open tasks need prioritizing.';
      list.innerHTML = '';
      return;
    }
    const next = openTasks[0];
    summary.textContent = `Recommended next: ${next.title || 'Untitled task'} · ${next.priority || 'medium'} priority${next.due_date ? ` · Due ${String(next.due_date).slice(0, 10)}` : ''}`;
    list.innerHTML = openTasks.slice(0, 3).map((task, index) => `<a class="card" style="padding:.75rem;text-decoration:none;color:inherit;" href="/tasks/${encodeURIComponent(task.id)}"><strong>${index + 1}. ${this.escapeHtml(task.title || 'Untitled task')}</strong><div class="text-muted" style="font-size:.8rem;margin-top:.35rem;">${this.escapeHtml(task.priority || 'medium')} priority · ${this.escapeHtml(String(task.status || 'todo').replaceAll('_', ' '))}${task.due_date ? ` · Due ${this.escapeHtml(String(task.due_date).slice(0, 10))}` : ''}</div></a>`).join('');
  },

  async loadTasks() {
    const container = document.getElementById('task-list-container');
    if (!container) return;

    // Dashboard task panels should show work that needs attention first.
    const isDashboard = !document.getElementById('task-search');

    container.innerHTML = `
      <div style="text-align: center; padding: 2.5rem; color: var(--color-muted);">
        <svg class="icon icon-lg" viewBox="0 0 24 24" style="animation: spin 1s linear infinite;"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>
        <p style="margin-top: 0.5rem; font-size: var(--font-size-sm);">Loading tasks...</p>
      </div>
    `;

    try {
      const params = new URLSearchParams();
      if (this.currentFilter.q) params.set('q', this.currentFilter.q);
      if (this.currentFilter.status) params.set('status', this.currentFilter.status);
      if (this.currentFilter.priority) params.set('priority', this.currentFilter.priority);
      if (this.currentFilter.category_id) params.set('category_id', this.currentFilter.category_id);
      if (this.currentFilter.type === 'personal') params.set('is_personal', 'true');
      else if (this.currentFilter.type === 'assigned') params.set('is_personal', 'false');

      if (isDashboard) {
        params.set('sort', 'priority_desc');
      } else if (this.currentFilter.sort) params.set('sort', this.currentFilter.sort);

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

      if (!isDashboard && this.viewMode === 'kanban') {
        container.style.display = 'none';
        const kc = document.getElementById('kanban-container');
        if (kc) kc.style.display = 'block';
      }

      if (isDashboard) {
        const label = container.closest('.card')?.querySelector('.card-title');
        if (label) label.textContent = document.getElementById('admin-metrics') ? 'Task Overview' : (document.getElementById('lead-metrics') ? 'Team Workload & Assignments' : 'My Active Tasks');
      }

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
        <div class="task-body" style="cursor: pointer;">
          <div style="display: flex; align-items: baseline; gap: 0.5rem; flex-wrap: wrap;">
            <span style="font-size: 0.7rem; font-weight: 700; color: var(--color-muted); font-family: monospace;">#${task.id}</span>
            <div class="task-title" style="margin-bottom: 0;">${this.escapeHtml(task.title)}</div>
          </div>
          ${task.description ? `<div class="task-desc-preview">${this.escapeHtml(task.description)}</div>` : ''}
          <div class="task-meta">
            ${task.category_name ? `<span class="badge badge-category"><svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>${this.escapeHtml(task.category_name)}</span>` : ''}
            <span class="badge badge-${task.priority}">${task.priority}</span>
            <span class="badge badge-${task.status}">${task.status.replace('_', ' ')}</span>
            ${task.team_name ? `<span class="badge badge-category">🏢 ${this.escapeHtml(task.team_name)}</span>` : ''}
            <span class="badge badge-employee">👤 ${this.escapeHtml(task.assignee_name || 'Unassigned')}</span>
            ${task.creator_name ? `<span class="badge badge-category">Assigned by ${this.escapeHtml(task.creator_name)}</span>` : ''}
            ${task.recurrence && task.recurrence !== 'none' ? `<span class="badge badge-category">🔁 ${task.recurrence}</span>` : ''}
            <span class="task-due-tag ${isOverdue ? 'is-overdue' : ''}">
              <svg class="icon icon-sm" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
              ${formattedDate} ${isOverdue ? '(Overdue)' : ''}
            </span>
          </div>
        </div>
        <div class="task-actions">
          <button class="btn btn-ghost btn-sm view-detail-btn" title="View Discussions & Deliverables">
            <svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
            <span style="font-size: var(--font-size-xs);">Discuss</span>
          </button>
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
      changes_requested: document.getElementById('kanban-changes_requested'),
      completed: document.getElementById('kanban-completed')
    };

    const counts = {
      pending: document.getElementById('kanban-count-pending'),
      in_progress: document.getElementById('kanban-count-in_progress'),
      blocked: document.getElementById('kanban-count-blocked'),
      in_review: document.getElementById('kanban-count-in_review'),
      changes_requested: document.getElementById('kanban-count-changes_requested'),
      completed: document.getElementById('kanban-count-completed')
    };

    Object.values(cols).forEach(col => { if (col) col.innerHTML = ''; });
    const colCounters = { pending: 0, in_progress: 0, blocked: 0, in_review: 0, changes_requested: 0, completed: 0 };

    tasks.forEach(task => {
      let colKey = task.status;
      if (colKey === 'todo') colKey = 'pending';
      if (!cols[colKey]) colKey = 'pending';

      colCounters[colKey]++;

      // Action buttons based on status & task type
      let actionButtonsHtml = '';
      if (task.is_personal) {
        if (task.status === 'completed') {
          actionButtonsHtml = `<button class="btn btn-ghost btn-xs kanban-quick-btn" data-action="reopen" data-id="${task.id}" style="color: var(--color-muted);">Reopen</button>`;
        } else {
          actionButtonsHtml = `<button class="btn btn-secondary btn-xs kanban-quick-btn" data-action="complete" data-id="${task.id}" style="color: #059669; border-color: #10B981; font-weight: 600;">✓ Complete</button>`;
        }
      } else {
        if (['pending', 'todo'].includes(task.status)) {
          actionButtonsHtml = `<button class="btn btn-primary btn-xs kanban-quick-btn" data-action="start" data-id="${task.id}">Start Work</button>`;
        } else if (task.status === 'in_progress') {
          actionButtonsHtml = `
            <button class="btn btn-secondary btn-xs kanban-quick-btn" data-action="block" data-id="${task.id}" style="color: var(--color-danger); border-color: var(--color-danger);">Block</button>
            <button class="btn btn-primary btn-xs kanban-quick-btn" data-action="submit" data-id="${task.id}">Submit Work</button>
          `;
        } else if (task.status === 'blocked') {
          actionButtonsHtml = `<button class="btn btn-secondary btn-xs kanban-quick-btn" data-action="resume" data-id="${task.id}">Resume Work</button>`;
        } else if (task.status === 'changes_requested') {
          actionButtonsHtml = `<button class="btn btn-primary btn-xs kanban-quick-btn" data-action="submit" data-id="${task.id}">Resubmit</button>`;
        }
      }

      // Counters (checklist, comments, attachments)
      const counters = [];
      if (task.subtask_count > 0) {
        counters.push(`<span>☑ ${task.subtasks_completed_count || 0}/${task.subtask_count}</span>`);
      }
      if (task.message_count > 0) {
        counters.push(`<span>💬 ${task.message_count}</span>`);
      }
      if (task.attachment_count > 0) {
        counters.push(`<span>📎 ${task.attachment_count}</span>`);
      }

      const card = document.createElement('div');
      card.className = 'card';
      card.style.cssText = 'padding: 0.85rem; cursor: pointer; border-radius: var(--radius-sm); border: 1px solid var(--color-border); box-shadow: var(--shadow-sm); transition: transform 0.15s ease; display: flex; flex-direction: column; gap: 0.5rem;';
      card.innerHTML = `
        <div>
          <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; margin-bottom: 0.35rem;">
            <div style="display: flex; align-items: baseline; gap: 0.35rem;">
              <span style="font-size: 0.65rem; font-weight: 700; color: var(--color-muted); font-family: monospace;">#${task.id}</span>
              <div style="font-weight: 700; font-size: var(--font-size-sm); color: var(--color-text);">
                ${this.escapeHtml(task.title)}
              </div>
            </div>
            ${task.is_personal ? `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #059669; font-weight: 700; font-size: 0.65rem; flex-shrink: 0;">Personal</span>` : ''}
          </div>
          ${task.description ? `<p style="font-size: var(--font-size-xs); color: var(--color-muted); margin: 0; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;">${this.escapeHtml(task.description)}</p>` : ''}
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.35rem; font-size: var(--font-size-xs);">
          <span class="badge badge-${task.priority}">${task.priority}</span>
          ${task.is_overdue ? `<span class="badge badge-overdue" style="font-size: 0.65rem;">⚠️ Overdue</span>` : ''}
          ${task.due_date ? `<span style="color: var(--color-muted); font-size: 0.7rem;">📅 ${task.due_date}</span>` : ''}
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.7rem; color: var(--color-muted); flex-wrap: wrap; gap: 0.25rem;">
          <div>
            ${task.is_personal ? '👤 My Task' : `👤 ${this.escapeHtml(task.creator_name ? `From: ${task.creator_name}` : (task.assignee_name || 'Assigned'))}`}
            ${task.team_name ? `<span class="badge badge-employee" style="font-size: 0.65rem; margin-left: 0.35rem;">${this.escapeHtml(task.team_name)}</span>` : ''}
          </div>
          <div style="display: flex; gap: 0.4rem;">
            ${counters.join('')}
          </div>
        </div>

        ${actionButtonsHtml ? `
          <div style="display: flex; justify-content: flex-end; gap: 0.4rem; border-top: 1px solid var(--color-border-subtle); padding-top: 0.4rem; margin-top: 0.2rem;">
            ${actionButtonsHtml}
          </div>
        ` : ''}
      `;

      card.addEventListener('mouseenter', () => { card.style.transform = 'translateY(-2px)'; });
      card.addEventListener('mouseleave', () => { card.style.transform = 'translateY(0)'; });
      card.addEventListener('click', () => this.openTaskDetailModal(task));

      // Quick action listeners
      card.querySelectorAll('.kanban-quick-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
          e.stopPropagation();
          const action = btn.dataset.action;
          const id = btn.dataset.id;

          if (action === 'start') {
            try {
              await api('PATCH', `/tasks/${id}`, { status: 'in_progress', comment: 'Started working on task' });
              showToast('Task marked in progress', 'success');
              this.loadTasks();
            } catch (err) {
              showToast(err.message || 'Failed to start task', 'error');
            }
          } else if (action === 'block') {
            const blockModal = document.getElementById('block-reason-modal');
            const blockIdInput = document.getElementById('block-task-id');
            if (blockModal && blockIdInput) {
              blockIdInput.value = id;
              blockModal.classList.add('is-active');
            }
          } else if (action === 'resume') {
            try {
              await api('PATCH', `/tasks/${id}`, { status: 'in_progress', comment: 'Resumed task' });
              showToast('Task resumed in progress', 'success');
              this.loadTasks();
            } catch (err) {
              showToast(err.message || 'Failed to resume task', 'error');
            }
          } else if (action === 'submit') {
            this.openTaskDetailModal(task);
            setTimeout(() => {
              document.getElementById('deliverable-message')?.focus();
            }, 300);
          } else if (action === 'complete') {
            try {
              await api('PATCH', `/tasks/${id}`, { status: 'completed' });
              showToast('Task completed!', 'success');
              this.loadTasks();
            } catch (err) {
              showToast(err.message || 'Failed to complete task', 'error');
            }
          } else if (action === 'reopen') {
            try {
              await api('PATCH', `/tasks/${id}`, { status: 'pending' });
              showToast('Task reopened', 'success');
              this.loadTasks();
            } catch (err) {
              showToast(err.message || 'Failed to reopen task', 'error');
            }
          }
        });
      });

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

      // Employee summary card metrics
      const empTodoEl = document.getElementById('emp-stat-todo');
      const empInReviewEl = document.getElementById('emp-stat-in-review');
      const empBreakdownEl = document.getElementById('emp-stat-personal-breakdown');
      if (empTodoEl) empTodoEl.textContent = stats.todo ?? stats.pending ?? 0;
      if (empInReviewEl) empInReviewEl.textContent = stats.in_review ?? 0;
      if (empBreakdownEl) {
        empBreakdownEl.textContent = `${stats.assigned_count ?? 0} assigned · ${stats.personal_count ?? 0} personal`;
      }

      // Smart Priority Banner ("What should I work on next?")
      const smartTitle = document.getElementById('smart-next-title');
      const smartReason = document.getElementById('smart-next-reason');
      const smartMeta = document.getElementById('smart-next-meta');
      const smartAction = document.getElementById('smart-next-action');

      if (smartTitle) {
        if (stats.smart_next && stats.smart_next.task) {
          const sn = stats.smart_next;
          smartTitle.textContent = sn.task.title;
          if (smartReason) {
            smartReason.textContent = sn.reason;
            smartReason.className = sn.reason.includes('Overdue') ? 'badge badge-overdue' : (sn.reason.includes('Changes') ? 'badge badge-high' : 'badge badge-completed');
          }
          if (smartMeta) {
            smartMeta.textContent = `Priority: ${sn.task.priority.toUpperCase()} · Status: ${sn.task.status_label || sn.task.status}${sn.task.due_date ? ` · Due: ${sn.task.due_date}` : ''}`;
          }
          if (smartAction) {
            smartAction.innerHTML = `<a href="/tasks?task_id=${sn.task.id}" class="btn btn-primary btn-sm">Start Working</a>`;
          }
        } else {
          smartTitle.textContent = 'All caught up!';
          if (smartReason) {
            smartReason.textContent = 'No pending tasks';
            smartReason.className = 'badge badge-completed';
          }
          if (smartMeta) smartMeta.textContent = 'Great work! You have no open tasks requiring immediate action.';
          if (smartAction) {
            smartAction.innerHTML = `<a href="/tasks" class="btn btn-secondary btn-sm">View Board</a>`;
          }
        }
      }

      // Personal Weekly Progress
      if (stats.weekly_progress) {
        const wp = stats.weekly_progress;
        const wAssigned = document.getElementById('weekly-assigned');
        const wCompleted = document.getElementById('weekly-completed');
        const wReview = document.getElementById('weekly-review');
        const wOverdue = document.getElementById('weekly-overdue');
        const wTrend = document.getElementById('weekly-progress-trend');

        if (wAssigned) wAssigned.textContent = wp.assigned_this_week ?? 0;
        if (wCompleted) wCompleted.textContent = wp.completed_this_week ?? 0;
        if (wReview) wReview.textContent = wp.awaiting_review ?? 0;
        if (wOverdue) wOverdue.textContent = wp.overdue ?? 0;
        if (wTrend) wTrend.textContent = wp.completion_trend ?? 'Active week';
      }

      // Employee Attendance Summary
      if (stats.attendance_summary) {
        const attSummary = stats.attendance_summary;
        const hToday = document.getElementById('emp-hours-today');
        const hWeek = document.getElementById('emp-hours-week');
        const shiftsList = document.getElementById('emp-recent-shifts');

        if (hToday) hToday.textContent = `${attSummary.today_hours ?? 0}h`;
        if (hWeek) hWeek.textContent = `${attSummary.week_hours ?? 0}h`;
        if (shiftsList) {
          if (!attSummary.recent_sessions || !attSummary.recent_sessions.length) {
            shiftsList.innerHTML = '<p class="text-muted" style="font-size: var(--font-size-xs); padding: 0.5rem 0;">No shifts recorded this week.</p>';
          } else {
            shiftsList.innerHTML = attSummary.recent_sessions.map(s => {
              const inStr = s.check_in ? new Date(s.check_in).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '—';
              const outStr = s.check_out ? new Date(s.check_out).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : (s.status === 'active' ? 'Active' : '—');
              const hrs = (s.duration_minutes ? (s.duration_minutes / 60).toFixed(1) : '0.0') + 'h';
              return `
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.35rem 0; border-bottom: 1px solid var(--color-border-subtle); font-size: var(--font-size-xs);">
                  <div>
                    <span style="font-weight: 600;">${s.work_date || (s.check_in ? s.check_in.split('T')[0] : 'Today')}</span>
                    <span style="color: var(--color-muted); margin-left: 0.35rem;">${inStr} – ${outStr}</span>
                  </div>
                  <span class="badge ${s.status === 'active' ? 'badge-completed' : 'badge-employee'}">${hrs}</span>
                </div>
              `;
            }).join('');
          }
        }
      }

      // Recent Activity Feed
      const activityContainer = document.getElementById('emp-recent-activity-list');
      if (activityContainer) {
        if (!stats.recent_activity || !stats.recent_activity.length) {
          activityContainer.innerHTML = '<p class="text-muted" style="font-size: var(--font-size-xs); padding: 1.5rem; text-align: center;">No recent activity on your tasks.</p>';
        } else {
          activityContainer.innerHTML = stats.recent_activity.map(a => {
            const timeStr = a.created_at ? new Date(a.created_at).toLocaleString([], {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}) : '';
            return `
              <div style="display: flex; gap: 0.75rem; align-items: flex-start; padding: 0.6rem 0; border-bottom: 1px solid var(--color-border-subtle);">
                <div style="width: 8px; height: 8px; border-radius: 50%; background: var(--color-primary); margin-top: 6px; flex-shrink: 0;"></div>
                <div style="flex: 1; min-width: 0;">
                  <div style="display: flex; justify-content: space-between; align-items: baseline; gap: 0.5rem;">
                    <span style="font-weight: 600; font-size: var(--font-size-xs); color: var(--color-text);">${this.escapeHtml(a.task_title)}</span>
                    <span style="font-size: 0.65rem; color: var(--color-muted);">${timeStr}</span>
                  </div>
                  <div style="font-size: var(--font-size-xs); color: var(--color-muted); margin-top: 0.15rem;">
                    <strong>${this.escapeHtml(a.actor_name)}</strong>: ${this.escapeHtml(a.comment)}
                    ${a.new_status ? `<span class="badge badge-employee" style="margin-left: 0.35rem; font-size: 0.65rem;">${a.new_status.replace('_', ' ')}</span>` : ''}
                  </div>
                </div>
              </div>
            `;
          }).join('');
        }
      }

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
    const assigneeField = document.getElementById('task-assignee-select');
    const recurrenceField = document.getElementById('task-recurrence-select');
    const criteriaField = document.getElementById('task-acceptance-input');

    if (task) {
      modalTitle.textContent = 'Edit Task';
      taskIdField.value = task.id;
      titleField.value = task.title;
      descField.value = task.description || '';
      priorityField.value = task.priority || 'medium';
      statusField.value = task.status || 'pending';
      categoryField.value = task.category_id || '';
      dueDateField.value = task.due_date ? task.due_date.split('T')[0] : '';
      if (assigneeField) assigneeField.value = task.assignee_id || '';
      if (recurrenceField) recurrenceField.value = task.recurrence || 'none';
      if (criteriaField) criteriaField.value = task.acceptance_criteria || '';
    } else {
      modalTitle.textContent = 'Add New Task';
      taskIdField.value = '';
      titleField.value = '';
      descField.value = '';
      priorityField.value = 'medium';
      statusField.value = 'pending';
      categoryField.value = '';
      dueDateField.value = '';
      if (assigneeField) assigneeField.value = '';
      if (recurrenceField) recurrenceField.value = 'none';
      if (criteriaField) criteriaField.value = '';
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
    const assigneeField = document.getElementById('task-assignee-select');
    const recurrenceField = document.getElementById('task-recurrence-select');
    const criteriaField = document.getElementById('task-acceptance-input');

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

  // ── Task Details, Subtasks, Discussions & Deliverables ────────────────────────

  async openTaskDetailModal(task) {
    this.activeTaskId = task.id;
    const modal = document.getElementById('task-detail-modal');
    if (!modal) return;

    document.getElementById('task-detail-title').textContent = `#${task.id} · ${task.title}`;
    const priBadge = document.getElementById('detail-priority-badge');
    if (priBadge) {
      priBadge.className = `badge badge-${task.priority}`;
      priBadge.textContent = task.priority;
    }

    const stBadge = document.getElementById('detail-status-badge');
    if (stBadge) {
      stBadge.className = `badge badge-${task.status}`;
      stBadge.textContent = task.status.replace('_', ' ');
    }

    document.getElementById('detail-desc').textContent = task.description || 'No description provided.';
    
    const critBox = document.getElementById('detail-criteria-box');
    const critText = document.getElementById('detail-criteria');
    if (task.acceptance_criteria) {
      critBox.style.display = 'block';
      critText.textContent = task.acceptance_criteria;
    } else {
      critBox.style.display = 'none';
    }

    document.getElementById('detail-assignee').textContent = task.is_personal ? 'Self (Personal Task)' : (task.assignee_name || 'Self / Unassigned');
    document.getElementById('detail-due').textContent = task.due_date || 'No due date';
    const creator = document.getElementById('detail-creator');
    if (creator) creator.textContent = task.is_personal ? 'Self' : (task.creator_name || 'Workspace administrator');
    const teamEl = document.getElementById('detail-team');
    if (teamEl) teamEl.textContent = task.team_name || 'General / Unassigned';

    // Personal Task Actions vs Assigned Task Deliverable Review
    let personalActionBox = document.getElementById('detail-personal-action-box');
    if (!personalActionBox) {
      personalActionBox = document.createElement('div');
      personalActionBox.id = 'detail-personal-action-box';
      const leftCol = modal.querySelector('.modal-body > div:first-child');
      if (leftCol) leftCol.insertBefore(personalActionBox, leftCol.firstChild);
    }

    const delivSection = document.getElementById('submit-deliverable-form')?.closest('div');

    if (task.is_personal) {
      personalActionBox.style.display = 'block';
      const isDone = task.status === 'completed';
      personalActionBox.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: var(--radius-sm); padding: 0.6rem 0.85rem; margin-bottom: 0.75rem;">
          <span style="font-size: var(--font-size-xs); font-weight: 700; color: #059669;">Personal Task</span>
          <button class="btn ${isDone ? 'btn-secondary' : 'btn-primary'} btn-sm" id="detail-toggle-personal-btn">
            ${isDone ? 'Reopen Task' : '✓ Mark Complete'}
          </button>
        </div>
      `;
      document.getElementById('detail-toggle-personal-btn')?.addEventListener('click', async () => {
        try {
          await api('PATCH', `/tasks/${task.id}`, { status: isDone ? 'pending' : 'completed' });
          showToast(isDone ? 'Task reopened' : 'Personal task completed!', 'success');
          this.closeModals();
          this.loadTasks();
        } catch (e) {
          showToast(e.message || 'Failed to update personal task', 'error');
        }
      });
      if (delivSection) delivSection.style.display = 'none';
    } else {
      personalActionBox.style.display = 'none';
      if (delivSection) delivSection.style.display = 'block';
    }

    modal.classList.add('is-active');

    // Load subtasks, messages, submissions, and history
    this.loadSubtasks(task.id);
    this.loadMessages(task.id);
    this.loadSubmissions(task.id);
    this.loadHistory(task.id);
  },

  async loadHistory(taskId) {
    const container = document.getElementById('status-history-container');
    if (!container) return;
    try {
      const res = await api('GET', `/tasks/${taskId}/history`);
      const history = res.data || [];
      if (!history.length) {
        container.innerHTML = '<span style="font-size: var(--font-size-xs); color: var(--color-muted);">No activity recorded yet.</span>';
        return;
      }
      container.innerHTML = history.map(h => {
        const timeStr = h.created_at ? new Date(h.created_at).toLocaleString([], {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'}) : '';
        return `
          <div style="font-size: var(--font-size-xs); padding: 0.35rem 0.5rem; background: var(--color-surface-subtle); border-radius: var(--radius-sm); border-left: 2px solid var(--color-primary); display: flex; justify-content: space-between; align-items: center; gap: 0.5rem;">
            <div>
              <strong>${this.escapeHtml(h.changed_by_name || 'System')}</strong>: ${this.escapeHtml(h.comment || (h.new_status ? `Changed to ${h.new_status}` : 'Updated'))}
            </div>
            <span style="font-size: 0.65rem; color: var(--color-muted); white-space: nowrap;">${timeStr}</span>
          </div>
        `;
      }).join('');
    } catch (e) {
      container.innerHTML = '<span style="font-size: var(--font-size-xs); color: var(--color-muted);">Activity history unavailable.</span>';
    }
  },

  async loadSubtasks(taskId) {
    const container = document.getElementById('subtasks-list');
    if (!container) return;
    try {
      const res = await api('GET', `/tasks/${taskId}`);
      const task = res.data;
      const subtasks = task.subtasks || [];

      if (subtasks.length === 0) {
        container.innerHTML = '<span style="font-size: var(--font-size-xs); color: var(--color-muted);">No subtasks yet. Add one below.</span>';
        return;
      }

      container.innerHTML = subtasks.map(s => `
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.35rem 0.5rem; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-sm); font-size: var(--font-size-xs);">
          <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer; flex: 1; margin: 0;">
            <input type="checkbox" class="subtask-checkbox" data-id="${s.id}" ${s.is_completed ? 'checked' : ''}>
            <span style="${s.is_completed ? 'text-decoration: line-through; color: var(--color-muted);' : 'color: var(--color-text);'}">${this.escapeHtml(s.title)}</span>
          </label>
        </div>
      `).join('');

      container.querySelectorAll('.subtask-checkbox').forEach(cb => {
        cb.addEventListener('change', async () => {
          const subId = cb.dataset.id;
          try {
            await api('PATCH', `/tasks/${taskId}/subtasks/${subId}`, {
              is_completed: cb.checked
            });
            this.loadSubtasks(taskId);
          } catch (e) {
            showToast('Failed to update subtask', 'error');
          }
        });
      });
    } catch (e) {
      console.error(e);
    }
  },

  async handleAddSubtask(e) {
    e.preventDefault();
    if (!this.activeTaskId) return;
    const input = document.getElementById('new-subtask-title');
    const title = input.value.trim();
    if (!title) return;

    try {
      await api('POST', `/tasks/${this.activeTaskId}/subtasks`, { title });
      input.value = '';
      this.loadSubtasks(this.activeTaskId);
    } catch (err) {
      showToast(err.message || 'Failed to add subtask', 'error');
    }
  },

  async loadMessages(taskId) {
    const container = document.getElementById('messages-container');
    if (!container) return;

    try {
      const res = await fetch(`/api/tasks/${taskId}/messages`);
      const json = await res.json();
      const messages = json.data || [];

      if (messages.length === 0) {
        container.innerHTML = '<div style="text-align: center; color: var(--color-muted); font-size: var(--font-size-xs); padding: 2rem;">No messages in this task thread yet.</div>';
        return;
      }

      container.innerHTML = messages.map(m => `
        <div style="background-color: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: 0.65rem 0.85rem; font-size: var(--font-size-xs);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
            <strong style="color: var(--color-primary);">${m.author_name}</strong>
            <span style="font-size: 0.65rem; color: var(--color-muted);">${new Date(m.created_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}</span>
          </div>
          <div style="color: var(--color-text); margin-bottom: 0.35rem; white-space: pre-wrap;">${this.escapeHtml(m.content)}</div>
          ${m.attachments && m.attachments.length > 0 ? `
            <div style="border-top: 1px dashed var(--color-border); padding-top: 0.35rem; margin-top: 0.35rem; display: flex; flex-direction: column; gap: 0.2rem;">
              ${m.attachments.map(a => `
                <a href="/api/files/${a.id}/download" target="_blank" style="color: var(--color-accent); font-weight: 600; font-size: 0.7rem; text-decoration: underline;">
                  📎 ${this.escapeHtml(a.filename)}
                </a>
              `).join('')}
            </div>
          ` : ''}
        </div>
      `).join('');

      container.scrollTop = container.scrollHeight;
    } catch (e) {
      container.innerHTML = `<div style="color: var(--color-danger); font-size: var(--font-size-xs); padding: 1rem;">Failed to load messages: ${e.message}</div>`;
    }
  },

  async handleSendMessage(e) {
    e.preventDefault();
    if (!this.activeTaskId) return;

    const textarea = document.getElementById('message-text');
    const fileInput = document.getElementById('message-file');
    const content = textarea.value.trim();
    if (!content) return;

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const formData = new FormData();
    formData.append('content', content);
    if (fileInput.files.length > 0) {
      formData.append('file', fileInput.files[0]);
    }

    try {
      const res = await fetch(`/api/tasks/${this.activeTaskId}/messages`, {
        method: 'POST', headers: { 'X-CSRFToken': csrfToken }, body: formData
      });
      const json = await res.json();
      if (!res.ok || json.ok === false) throw new Error(json.error || json.message || 'Failed to send message');
      textarea.value = ''; fileInput.value = '';
      showToast('Message sent.', 'success');
      await this.loadMessages(this.activeTaskId);
    } catch (err) {
      showToast(err.message, 'error');
    }
  },

  async loadSubmissions(taskId) {
    const container = document.getElementById('submissions-history');
    if (!container) return;

    try {
      const res = await fetch(`/api/tasks/${taskId}/submissions`);
      const json = await res.json();
      const subs = json.data || [];

      if (subs.length === 0) {
        container.innerHTML = '<span style="font-size: var(--font-size-xs); color: var(--color-muted);">No deliverables submitted yet.</span>';
        return;
      }

      container.innerHTML = subs.map(s => `
        <div style="background-color: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-sm); padding: 0.75rem; font-size: var(--font-size-xs);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
            <span>By <strong>${s.submitter_name || s.submitted_by_name || "Employee"}</strong> on ${new Date(s.created_at).toLocaleDateString()}</span>
            <span class="badge ${s.status === 'approved' ? 'badge-completed' : s.status === 'changes_requested' || s.status === 'rejected' ? 'badge-overdue' : 'badge-pending'}">${s.status.toUpperCase()}</span>
          </div>
          <div style="color: var(--color-text); margin-bottom: 0.35rem;">${this.escapeHtml(s.notes || s.message || "") }</div>
          ${s.attachments && s.attachments.length > 0 ? `
            <div style="margin-bottom: 0.35rem;">
              ${s.attachments.map(a => `<a href="/api/files/${a.id}/download" style="color: var(--color-primary); font-weight: 600;">📥 ${this.escapeHtml(a.filename)}</a>`).join(' ')}
            </div>
          ` : ''}
          ${(s.review_notes || s.review_feedback) ? `
            <div style="background: #FFF9F5; border-left: 2px solid var(--color-accent); padding: 0.4rem; font-size: 0.7rem; color: var(--color-accent);">
              <strong>Review Feedback:</strong> ${this.escapeHtml(s.review_notes || s.review_feedback)}
            </div>
          ` : ''}
          ${['pending','submitted'].includes(s.status) ? `
            <div style="display: flex; gap: 0.5rem; margin-top: 0.5rem; justify-content: flex-end;">
              <button class="btn btn-secondary btn-sm review-action-btn" data-sub-id="${s.id}" data-action="request_changes">Request Changes</button>
              <button class="btn btn-primary btn-sm review-action-btn" data-sub-id="${s.id}" data-action="approved">Approve</button>
            </div>
          ` : ''}
        </div>
      `).join('');

      container.querySelectorAll('.review-action-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          const subId = btn.dataset.subId;
          const action = btn.dataset.action;
          const feedback = prompt(action === 'approved' ? 'Optional approval notes:' : 'Please enter feedback describing changes needed:');
          if (action === 'request_changes' && !feedback) {
            showToast('Feedback is required when requesting revisions.', 'error');
            return;
          }

          const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
          try {
            const revRes = await fetch(`/api/tasks/${this.activeTaskId}/submissions/${subId}/review`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
              },
              body: JSON.stringify({
                decision: action === 'approved' ? 'approve' : 'request_changes',
                review_notes: feedback || ''
              })
            });
            const revData = await revRes.json();
            if (!revRes.ok || revData.ok === false) throw new Error(revData.error || revData.message || 'Review action failed');
            showToast(action === 'approved' ? 'Submission approved!' : 'Changes requested.', 'success');
            this.loadSubmissions(this.activeTaskId);
            this.loadTasks();
          } catch (err) {
            showToast(err.message, 'error');
          }
        });
      });
    } catch (e) {
      container.innerHTML = `<span style="color: var(--color-danger); font-size: var(--font-size-xs);">Failed to load submissions: ${e.message}</span>`;
    }
  },

  async handleSubmitDeliverable(e) {
    e.preventDefault();
    if (!this.activeTaskId) return;

    const msgInput = document.getElementById('deliverable-message');
    const fileInput = document.getElementById('deliverable-file');
    const message = msgInput.value.trim();
    if (!message) return;

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const formData = new FormData();
    formData.append('notes', message);
    if (fileInput.files.length > 0) {
      formData.append('file', fileInput.files[0]);
    }

    try {
      // Upload the file first; the submissions endpoint links saved attachment IDs.
      let attachmentIds = [];
      if (fileInput.files.length > 0) {
        const uploadData = new FormData(); uploadData.append('file', fileInput.files[0]);
        const uploadRes = await fetch(`/api/tasks/${this.activeTaskId}/attachments`, { method: 'POST', headers: {'X-CSRFToken': csrfToken}, body: uploadData });
        const uploadJson = await uploadRes.json();
        if (!uploadRes.ok || uploadJson.ok === false) throw new Error(uploadJson.error || uploadJson.message || 'File upload failed');
        if (uploadJson.data && uploadJson.data.id) attachmentIds.push(uploadJson.data.id);
      }
      const res = await fetch(`/api/tasks/${this.activeTaskId}/submissions`, {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
        body: JSON.stringify({notes: message, attachment_ids: attachmentIds})
      });
      const json = await res.json();
      if (!res.ok || json.ok === false) throw new Error(json.error || json.message || 'Failed to submit work deliverable');
      showToast('Deliverable submitted for review!', 'success');
      msgInput.value = ''; fileInput.value = '';
      await this.loadSubmissions(this.activeTaskId); await this.loadTasks();
    } catch (err) {
      showToast(err.message, 'error');
    }
  },

  // ── Categories ─────────────────────────────────────────────────────────────

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
      modal.classList.remove('is-open');
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
