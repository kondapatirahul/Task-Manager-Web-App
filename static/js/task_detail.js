/**
 * TaskNest Task Detail & Workflow Engine
 */

const TaskDetail = {
  taskId: null,
  task: null,
  currentUser: null,

  async init() {
    const pageEl = document.querySelector('.task-detail-page');
    if (!pageEl) return;

    this.taskId = pageEl.getAttribute('data-task-id');
    if (!this.taskId) return;

    this.bindEvents();

    try {
      // Load current user and task in parallel
      const [userRes, taskRes] = await Promise.all([
        window.API.get('/api/auth/me'),
        window.API.get(`/api/tasks/${this.taskId}`),
      ]);

      if (userRes && userRes.ok) {
        this.currentUser = userRes.data;
      }

      if (taskRes && taskRes.ok) {
        this.task = taskRes.data;
        this.renderTask();
      } else {
        this.showError(taskRes?.error || 'Task not found or access denied.');
      }
    } catch (err) {
      console.error('Failed to load task detail:', err);
      this.showError('Unable to load task details. Please check your connection.');
    }
  },

  bindEvents() {
    // Close submit modal
    document.querySelectorAll('.close-submit-modal').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.getElementById('submit-review-modal')?.classList.remove('active');
        document.getElementById('submit-review-modal')?.classList.remove('is-active');
        document.body.classList.remove('modal-open');
      });
    });

    // Close on backdrop overlay click
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
      overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
          overlay.classList.remove('active');
          overlay.classList.remove('is-active');
          document.body.classList.remove('modal-open');
        }
      });
    });

    // Handle submit form
    const submitForm = document.getElementById('submit-review-form');
    if (submitForm) {
      submitForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const notes = document.getElementById('submit-notes-input')?.value || '';
        try {
          const res = await window.API.post(`/api/tasks/${this.taskId}/submit`, { notes });
          if (res && res.ok) {
            window.API.toast('Work submitted for review successfully!', 'success');
            document.getElementById('submit-review-modal')?.classList.remove('active');
            document.getElementById('submit-review-modal')?.classList.remove('is-active');
            document.body.classList.remove('modal-open');
            this.task = res.data;
            this.renderTask();
          } else {
            window.API.toast(res?.error || 'Failed to submit work for review', 'danger');
          }
        } catch (err) {
          window.API.toast('Submission failed.', 'danger');
        }
      });
    }

    // Close review modal
    document.querySelectorAll('.close-review-modal').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.getElementById('review-action-modal')?.classList.remove('active');
        document.getElementById('review-action-modal')?.classList.remove('is-active');
        document.body.classList.remove('modal-open');
      });
    });

    // Handle review form
    const reviewForm = document.getElementById('review-action-form');
    if (reviewForm) {
      reviewForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const action = document.getElementById('review-action-type')?.value || 'approve';
        const notes = document.getElementById('review-notes-input')?.value || '';
        try {
          const res = await window.API.post(`/api/tasks/${this.taskId}/review`, { action, notes });
          if (res && res.ok) {
            const msg = action === 'approve' ? 'Task approved and completed!' : 'Changes requested.';
            window.API.toast(msg, 'success');
            document.getElementById('review-action-modal')?.classList.remove('active');
            document.getElementById('review-action-modal')?.classList.remove('is-active');
            document.body.classList.remove('modal-open');
            this.task = res.data;
            this.renderTask();
          } else {
            window.API.toast(res?.error || 'Failed to submit review', 'danger');
          }
        } catch (err) {
          window.API.toast('Review action failed.', 'danger');
        }
      });
    }
  },

  showError(msg) {
    document.getElementById('detail-loading').style.display = 'none';
    const errCard = document.getElementById('detail-error');
    if (errCard) {
      errCard.style.display = 'block';
      const msgEl = document.getElementById('detail-error-msg');
      if (msgEl) msgEl.textContent = msg;
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
        return 'badge-danger';
      case 'blocked':
        return 'badge-danger';
      case 'todo':
      case 'pending':
      default:
        return 'badge-neutral';
    }
  },

  getPriorityBadgeClass(priority) {
    switch (priority) {
      case 'high':
        return 'badge-danger';
      case 'medium':
        return 'badge-warning';
      case 'low':
      default:
        return 'badge-info';
    }
  },

  renderTask() {
    const t = this.task;
    if (!t) return;

    document.getElementById('detail-loading').style.display = 'none';
    document.getElementById('detail-content').style.display = 'block';

    // Title
    document.getElementById('detail-title').textContent = t.title;

    // Badges
    const statusBadge = document.getElementById('detail-status-badge');
    statusBadge.textContent = t.status_label || t.status.replace('_', ' ').toUpperCase();
    statusBadge.className = `badge ${this.getStatusBadgeClass(t.status)}`;

    const priorityBadge = document.getElementById('detail-priority-badge');
    priorityBadge.textContent = `${t.priority.toUpperCase()} PRIORITY`;
    priorityBadge.className = `badge ${this.getPriorityBadgeClass(t.priority)}`;

    if (t.category_name) {
      const catBadge = document.getElementById('detail-category-badge');
      catBadge.textContent = t.category_name;
      catBadge.style.display = 'inline-block';
    }

    if (t.is_overdue) {
      document.getElementById('detail-overdue-badge').style.display = 'inline-block';
    }

    // Meta line
    const createdStr = t.created_at ? new Date(t.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : 'recently';
    document.getElementById('detail-meta-line').textContent = `Created by ${t.creator_name || 'Team Member'} on ${createdStr}`;

    // Description
    const descEl = document.getElementById('detail-description');
    if (t.description) {
      descEl.textContent = t.description;
    } else {
      descEl.innerHTML = '<span class="text-muted">No description provided.</span>';
    }

    // Criteria
    const critEl = document.getElementById('detail-criteria');
    if (t.acceptance_criteria) {
      critEl.textContent = t.acceptance_criteria;
    } else {
      critEl.innerHTML = '<span class="text-muted">No acceptance criteria specified.</span>';
    }

    // Submission / Review notes panel
    const reviewCard = document.getElementById('detail-review-card');
    let hasNotes = false;

    if (t.submission_notes) {
      document.getElementById('detail-submission-notes-box').style.display = 'block';
      document.getElementById('detail-submission-notes').textContent = t.submission_notes;
      hasNotes = true;
    } else {
      document.getElementById('detail-submission-notes-box').style.display = 'none';
    }

    if (t.review_notes) {
      document.getElementById('detail-review-notes-box').style.display = 'block';
      document.getElementById('detail-review-notes').textContent = t.review_notes;
      hasNotes = true;
    } else {
      document.getElementById('detail-review-notes-box').style.display = 'none';
    }

    reviewCard.style.display = hasNotes ? 'block' : 'none';

    // People
    const assigneeName = t.assigned_to_name || 'Unassigned';
    document.getElementById('detail-assignee-name').textContent = assigneeName;
    document.getElementById('detail-assignee-role').textContent = t.assigned_to_role || (t.assigned_to_id ? 'Employee' : 'Open task');
    document.getElementById('detail-assignee-avatar').textContent = assigneeName.charAt(0).toUpperCase();

    const creatorName = t.creator_name || 'Team Member';
    document.getElementById('detail-creator-name').textContent = creatorName;
    document.getElementById('detail-creator-role').textContent = t.creator_role ? t.creator_role.replace('_', ' ').toUpperCase() : 'Creator';
    document.getElementById('detail-creator-avatar').textContent = creatorName.charAt(0).toUpperCase();

    // Details dl
    document.getElementById('detail-team-name').textContent = t.team_name || 'Personal / Unassigned Team';
    document.getElementById('detail-start-date').textContent = t.start_date || '—';
    document.getElementById('detail-due-date').textContent = t.due_date || '—';
    document.getElementById('detail-completed-at').textContent = t.completed_at ? new Date(t.completed_at).toLocaleString() : '—';
    document.getElementById('detail-recurrence').textContent = t.is_recurring ? (t.recurrence_interval || 'Yes') : 'None';
    document.getElementById('detail-created-at').textContent = t.created_at ? new Date(t.created_at).toLocaleString() : '—';

    // Status Timeline
    this.renderTimeline(t.status_history || []);

    // Actions
    this.renderActions();
  },

  renderTimeline(history) {
    const timelineEl = document.getElementById('detail-timeline');
    if (!history || history.length === 0) {
      timelineEl.innerHTML = '<p class="text-muted" style="padding: 0.5rem 0;">No status changes recorded yet.</p>';
      return;
    }

    timelineEl.innerHTML = history
      .map((item) => {
        const timeStr = item.created_at
          ? new Date(item.created_at).toLocaleString(undefined, {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })
          : '';
        const oldLabel = item.old_status ? (item.old_status.replace('_', ' ').toUpperCase()) : 'CREATED';
        const newLabel = item.new_status ? (item.new_status.replace('_', ' ').toUpperCase()) : '';

        return `
        <div class="timeline-item">
          <div class="timeline-marker"></div>
          <div class="timeline-content">
            <div class="timeline-header">
              <span class="timeline-author">${item.changed_by_name}</span>
              <span class="timeline-transition">changed status to <strong>${newLabel}</strong></span>
              <span class="timeline-time text-muted">${timeStr}</span>
            </div>
            ${item.comment ? `<div class="timeline-comment">${item.comment}</div>` : ''}
          </div>
        </div>
      `;
      })
      .join('');
  },

  renderActions() {
    const container = document.getElementById('task-detail-actions');
    if (!container || !this.task || !this.currentUser) return;

    const t = this.task;
    const u = this.currentUser;

    const isAssignee = t.assigned_to_id === u.id;
    const isCreator = t.user_id === u.id;
    const isAdmin = ['super_admin', 'admin'].includes(u.role);
    const isTeamLead = u.role === 'team_lead';
    const isManager = isAdmin || isCreator || (isTeamLead && t.team_id);

    let html = '';

    // If task is in review and user has review privileges (manager/creator, not self-reviewing employee)
    if (t.status === 'in_review' && (isManager && (!isAssignee || isAdmin))) {
      html += `
        <button id="btn-approve-task" class="btn btn-success btn-sm">
          <svg class="icon icon-sm" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>
          <span>Approve Task</span>
        </button>
        <button id="btn-request-changes" class="btn btn-danger btn-sm">
          <svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
          <span>Request Changes</span>
        </button>
      `;
    }

    // If assignee employee and task is ready to submit
    if (isAssignee && ['todo', 'pending', 'in_progress', 'changes_requested', 'blocked'].includes(t.status)) {
      html += `
        <button id="btn-open-submit-modal" class="btn btn-primary btn-sm">
          <svg class="icon icon-sm" viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
          <span>Submit for Review</span>
        </button>
      `;
    }

    // Status quick changer
    const statusOptions = [
      { val: 'todo', label: 'To Do' },
      { val: 'in_progress', label: 'In Progress' },
      { val: 'blocked', label: 'Blocked' },
    ];
    if (isManager) {
      statusOptions.push({ val: 'in_review', label: 'In Review' });
      statusOptions.push({ val: 'changes_requested', label: 'Changes Requested' });
      statusOptions.push({ val: 'completed', label: 'Completed' });
    }

    html += `
      <div class="dropdown-container">
        <select id="quick-status-select" class="filter-select" style="margin: 0; padding: 0.375rem 0.75rem;">
          ${statusOptions
            .map((opt) => `<option value="${opt.val}" ${opt.val === t.status ? 'selected' : ''}>Move to: ${opt.label}</option>`)
            .join('')}
        </select>
      </div>
    `;

    // Edit and Delete buttons for manager
    if (isManager) {
      html += `
        <button id="btn-edit-detail-task" class="btn btn-secondary btn-sm" title="Edit Task">
          <svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
          <span>Edit</span>
        </button>
        <button id="btn-delete-detail-task" class="btn btn-ghost btn-sm text-danger" title="Delete Task">
          <svg class="icon icon-sm" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
        </button>
      `;
    }

    container.innerHTML = html;

    // Attach listeners
    document.getElementById('btn-approve-task')?.addEventListener('click', () => {
      document.getElementById('review-action-type').value = 'approve';
      document.getElementById('review-action-title').textContent = 'Approve Completed Task';
      document.getElementById('review-notes-label').textContent = 'Approval Feedback / Notes (Optional)';
      const submitBtn = document.getElementById('review-submit-btn');
      submitBtn.textContent = 'Approve & Mark Completed';
      submitBtn.className = 'btn btn-success';
      document.body.classList.add('modal-open');
      document.getElementById('review-action-modal')?.classList.add('active');
      document.getElementById('review-action-modal')?.classList.add('is-active');
    });

    document.getElementById('btn-request-changes')?.addEventListener('click', () => {
      document.getElementById('review-action-type').value = 'request_changes';
      document.getElementById('review-action-title').textContent = 'Request Changes on Task';
      document.getElementById('review-notes-label').textContent = 'Required Fixes & Feedback';
      const submitBtn = document.getElementById('review-submit-btn');
      submitBtn.textContent = 'Send Changes Requested';
      submitBtn.className = 'btn btn-danger';
      document.body.classList.add('modal-open');
      document.getElementById('review-action-modal')?.classList.add('active');
      document.getElementById('review-action-modal')?.classList.add('is-active');
    });

    document.getElementById('btn-open-submit-modal')?.addEventListener('click', () => {
      document.body.classList.add('modal-open');
      document.getElementById('submit-review-modal')?.classList.add('active');
      document.getElementById('submit-review-modal')?.classList.add('is-active');
    });

    document.getElementById('quick-status-select')?.addEventListener('change', async (e) => {
      const newStatus = e.target.value;
      if (newStatus === this.task.status) return;
      try {
        const res = await window.API.put(`/api/tasks/${this.taskId}`, { status: newStatus });
        if (res && res.ok) {
          window.API.toast('Task status updated', 'success');
          this.task = res.data;
          this.renderTask();
        } else {
          window.API.toast(res?.error || 'Failed to update status', 'danger');
          e.target.value = this.task.status;
        }
      } catch (err) {
        window.API.toast('Status update failed.', 'danger');
        e.target.value = this.task.status;
      }
    });

    document.getElementById('btn-edit-detail-task')?.addEventListener('click', () => {
      if (window.TaskManager && typeof window.TaskManager.openEditModal === 'function') {
        window.TaskManager.openEditModal(this.task.id);
      }
    });

    document.getElementById('btn-delete-detail-task')?.addEventListener('click', async () => {
      if (!confirm(`Are you sure you want to delete task "${this.task.title}"?`)) return;
      try {
        const res = await window.API.delete(`/api/tasks/${this.taskId}`);
        if (res && res.ok) {
          window.API.toast('Task deleted successfully', 'success');
          window.location.href = '/tasks';
        } else {
          window.API.toast(res?.error || 'Delete failed', 'danger');
        }
      } catch (err) {
        window.API.toast('Delete operation failed.', 'danger');
      }
    });
  },
};

document.addEventListener('DOMContentLoaded', () => {
  TaskDetail.init();
});

