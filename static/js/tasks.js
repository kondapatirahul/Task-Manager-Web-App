
document.addEventListener('DOMContentLoaded', () => {
  const list = document.getElementById('taskList');
  const form = document.getElementById('taskForm');
  const modal = document.getElementById('taskModal');
  const modalTitle = document.getElementById('taskModalTitle');
  const addButton = document.getElementById('openAddTaskModalBtn');
  const cancelButton = document.getElementById('cancelTaskBtn');
  const searchInput = document.getElementById('taskSearch');
  const filterSelect = document.getElementById('taskFilter');

  if (!list || !form || !modal) return;

  let tasks = [];
  let editingId = null;

  const escape = value =>
    typeof escapeHtml === 'function'
      ? escapeHtml(String(value ?? ''))
      : String(value ?? '').replace(/[&<>"']/g, char => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;',
          '"': '&quot;', "'": '&#039;'
        })[char]);

  function notify(message, type = 'info') {
    if (typeof toast === 'function') toast(message, type);
    else alert(message);
  }

  function openModal(task = null) {
    editingId = task ? task.id : null;
    form.reset();

    modalTitle.textContent = task ? 'Edit Task' : 'Add Task';
    document.getElementById('taskTitle').value = task?.title || '';
    document.getElementById('taskDescription').value = task?.description || '';
    document.getElementById('taskPriority').value = task?.priority || 'medium';

    modal.hidden = false;
    document.getElementById('taskTitle').focus();
  }

  function closeModal() {
    modal.hidden = true;
    editingId = null;
    form.reset();
  }

  function renderTasks() {
    const query = searchInput.value.trim().toLowerCase();
    const filter = filterSelect.value;

    const filtered = tasks.filter(task => {
      const matchesSearch =
        (task.title || '').toLowerCase().includes(query) ||
        (task.description || '').toLowerCase().includes(query);

      const matchesFilter =
        filter === 'all' ||
        (filter === 'completed' && task.status === 'done') ||
        (filter === 'pending' && task.status !== 'done');

      return matchesSearch && matchesFilter;
    });

    if (!filtered.length) {
      list.innerHTML = `
        <div class="card task-empty">
          <h3>${tasks.length ? 'No matching tasks' : 'No tasks yet'}</h3>
          <p>${tasks.length
            ? 'Try another search or filter.'
            : 'Add your first task to get started.'}</p>
        </div>`;
      return;
    }

    list.innerHTML = filtered.map(task => {
      const completed = task.status === 'done';

      return `
        <article class="card task-item ${completed ? 'task-completed' : ''}">
          <div class="task-item-main">
            <label class="task-check-label">
              <input
                type="checkbox"
                class="task-toggle"
                data-id="${task.id}"
                ${completed ? 'checked' : ''}
                aria-label="Mark ${escape(task.title)} as completed">
            </label>

            <div class="task-item-details">
              <h3>${escape(task.title)}</h3>
              ${task.description
                ? `<p>${escape(task.description)}</p>`
                : ''}
              <div class="task-meta">
                <span class="task-priority priority-${escape(task.priority)}">
                  ${escape(task.priority || 'medium')} priority
                </span>
                <span class="task-status">
                  ${completed ? 'Completed' : 'Pending'}
                </span>
              </div>
            </div>
          </div>

          <div class="task-actions">
            <button type="button" class="btn btn-secondary"
              data-action="edit" data-id="${task.id}">Edit</button>
            <button type="button" class="btn btn-danger"
              data-action="delete" data-id="${task.id}">Delete</button>
          </div>
        </article>`;
    }).join('');
  }

  async function loadTasks() {
    list.innerHTML = '<div class="card task-empty">Loading tasks...</div>';

    try {
      tasks = await TaskAPI.getTasks();
      renderTasks();
    } catch (error) {
      list.innerHTML = `
        <div class="card task-empty">
          <p>Unable to load tasks: ${escape(error.message)}</p>
          <button type="button" class="btn btn-primary" id="retryTasks">
            Try Again
          </button>
        </div>`;

      document.getElementById('retryTasks')?.addEventListener('click', loadTasks);
    }
  }

  addButton?.addEventListener('click', () => openModal());
  cancelButton?.addEventListener('click', closeModal);

  modal.addEventListener('click', event => {
    if (event.target === modal) closeModal();
  });

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !modal.hidden) closeModal();
  });

  searchInput.addEventListener('input', renderTasks);
  filterSelect.addEventListener('change', renderTasks);

  form.addEventListener('submit', async event => {
    event.preventDefault();

    const title = document.getElementById('taskTitle').value.trim();
    if (!title) {
      notify('Please enter a task title.', 'error');
      return;
    }

    const submitButton = form.querySelector('[type="submit"]');
    const taskData = {
      title,
      description: document.getElementById('taskDescription').value.trim(),
      priority: document.getElementById('taskPriority').value
    };

    submitButton.disabled = true;

    try {
      if (editingId !== null) {
        await TaskAPI.updateTask(editingId, taskData);
        notify('Task updated successfully.', 'success');
      } else {
        await TaskAPI.addTask(taskData);
        notify('Task added successfully.', 'success');
      }

      closeModal();
      await loadTasks();
    } catch (error) {
      notify(error.message, 'error');
    } finally {
      submitButton.disabled = false;
    }
  });

  list.addEventListener('click', async event => {
    const button = event.target.closest('button[data-action]');
    if (!button) return;

    const id = Number(button.dataset.id);
    const task = tasks.find(item => item.id === id);
    if (!task) return;

    if (button.dataset.action === 'edit') {
      openModal(task);
    }

    if (button.dataset.action === 'delete') {
      if (!confirm(`Delete "${task.title}"? This cannot be undone.`)) return;

      button.disabled = true;

      try {
        await TaskAPI.deleteTask(id);
        notify('Task deleted successfully.', 'success');
        await loadTasks();
      } catch (error) {
        notify(error.message, 'error');
        button.disabled = false;
      }
    }
  });

  list.addEventListener('change', async event => {
    const checkbox = event.target.closest('.task-toggle');
    if (!checkbox) return;

    const id = Number(checkbox.dataset.id);
    const task = tasks.find(item => item.id === id);
    if (!task) return;

    checkbox.disabled = true;

    try {
      await TaskAPI.updateTask(id, {
        status: checkbox.checked ? 'done' : 'pending'
      });

      notify(checkbox.checked ? 'Task completed!' : 'Task marked pending.', 'success');
      await loadTasks();
    } catch (error) {
      checkbox.checked = !checkbox.checked;
      notify(error.message, 'error');
      checkbox.disabled = false;
    }
  });

  loadTasks();
});
