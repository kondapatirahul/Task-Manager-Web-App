/**
 * TaskNest Enterprise — Employee Dashboard Controller
 * Powers My Day Planner, Personal Productivity, Task Organization, Daily Schedule, and Collaboration Center.
 * Strictly scoped and inactive outside of .employee-dashboard-wrapper.
 */

(function () {
  'use strict';

  // Strict isolation check: Only run if the employee dashboard wrapper is present in the DOM
  const wrapper = document.querySelector('.employee-dashboard-wrapper');
  if (!wrapper) {
    return;
  }

  // Local state container
  const state = {
    tasks: [],
    stats: null,
    attendance: null,
    meetings: [],
    notifications: [],
    currentView: 'all',
    priorityFilter: '',
    searchQuery: '',
    shiftTicker: null,
    activeShiftStartedAt: null
  };

  /**
   * Helper: Escape HTML strings to prevent XSS
   */
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /**
   * Helper: Format Date to YYYY-MM-DD in local time
   */
  function getLocalDateString(d = new Date()) {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  /**
   * Helper: Relative time formatter (e.g., '5m ago', '2h ago')
   */
  function timeAgo(dateInput) {
    if (!dateInput) return '';
    const date = new Date(dateInput);
    if (isNaN(date.getTime())) return '';
    const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return 'Just now';
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 7) return `${days}d ago`;
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  /**
   * Helper: Format seconds to HH:MM:SS
   */
  function formatHMS(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
  }

  /**
   * Helper: Check if two date objects or ISO strings fall on the same calendar day
   */
  function isSameDay(d1, d2) {
    if (!d1 || !d2) return false;
    const date1 = new Date(d1);
    const date2 = new Date(d2);
    return date1.getFullYear() === date2.getFullYear() &&
           date1.getMonth() === date2.getMonth() &&
           date1.getDate() === date2.getDate();
  }

  /**
   * Load all core dataset for the employee dashboard
   */
  async function loadAllData() {
    try {
      const [tasksRes, statsRes, attendanceRes, meetingsRes, notificationsRes] = await Promise.allSettled([
        api('GET', '/tasks'),
        api('GET', '/stats'),
        api('GET', '/attendance/today'),
        api('GET', '/meetings?upcoming=1'),
        api('GET', '/notifications')
      ]);

      if (tasksRes.status === 'fulfilled' && tasksRes.value && tasksRes.value.data) {
        state.tasks = Array.isArray(tasksRes.value.data) ? tasksRes.value.data : (tasksRes.value.data.tasks || []);
      }

      if (statsRes.status === 'fulfilled' && statsRes.value && statsRes.value.data) {
        state.stats = statsRes.value.data;
      }

      if (attendanceRes.status === 'fulfilled' && attendanceRes.value && attendanceRes.value.data) {
        state.attendance = attendanceRes.value.data;
      }

      if (meetingsRes.status === 'fulfilled' && meetingsRes.value && meetingsRes.value.data) {
        state.meetings = Array.isArray(meetingsRes.value.data) ? meetingsRes.value.data : (meetingsRes.value.data.meetings || []);
      }

      if (notificationsRes.status === 'fulfilled' && notificationsRes.value && notificationsRes.value.data) {
        state.notifications = Array.isArray(notificationsRes.value.data) ? notificationsRes.value.data : (notificationsRes.value.data.notifications || []);
      }

      renderAll();
    } catch (err) {
      console.error('[EmployeeDashboard] Error loading dashboard data:', err);
    }
  }

  /**
   * Render all components
   */
  function renderAll() {
    renderDateBadge();
    renderMyDayTasks();
    renderProductivityDashboard();
    renderDailySchedule();
    renderCollaborationCenter();
    renderNotificationPill();
  }

  /**
   * Render Today's Date Badge
   */
  function renderDateBadge() {
    const badge = document.getElementById('emp-today-date-badge');
    if (!badge) return;
    const today = new Date();
    const options = { weekday: 'short', month: 'short', day: 'numeric' };
    badge.textContent = today.toLocaleDateString(undefined, options);
  }

  /**
   * Feature 1 & 3: Render My Day Planner & Task Organization
   */
  function renderMyDayTasks() {
    const listContainer = document.getElementById('emp-my-day-task-list');
    if (!listContainer) return;

    const todayStr = getLocalDateString(new Date());

    // 1. Calculate counts for filter tab badges
    let dueTodayCount = 0;
    let highCount = 0;
    let overdueCount = 0;

    state.tasks.forEach(task => {
      const isCompleted = task.status === 'completed';
      const isOverdue = !isCompleted && (task.is_overdue || (task.due_date && task.due_date < todayStr));
      const isHigh = !isCompleted && (task.priority === 'high' || task.priority === 'urgent');
      const isDueToday = !isCompleted && task.due_date === todayStr;

      if (isDueToday) dueTodayCount++;
      if (isHigh) highCount++;
      if (isOverdue) overdueCount++;
    });

    const dueTodayBadge = document.getElementById('emp-tab-due-today-count');
    if (dueTodayBadge) dueTodayBadge.textContent = dueTodayCount;

    const highBadge = document.getElementById('emp-tab-high-count');
    if (highBadge) highBadge.textContent = highCount;

    const overdueBadge = document.getElementById('emp-tab-overdue-count');
    if (overdueBadge) overdueBadge.textContent = overdueCount;

    // 2. Calculate Daily Progress (tasks due today or completed today)
    const todayTasks = state.tasks.filter(t => {
      if (t.due_date === todayStr) return true;
      if (t.status === 'completed' && t.completed_at && isSameDay(t.completed_at, new Date())) return true;
      return false;
    });

    // If no tasks explicitly marked for today, use active + completed tasks to show meaningful progress
    const progressTasks = todayTasks.length > 0 ? todayTasks : state.tasks.slice(0, 8);
    const completedDaily = progressTasks.filter(t => t.status === 'completed').length;
    const totalDaily = progressTasks.length;
    const dailyPct = totalDaily > 0 ? Math.round((completedDaily / totalDaily) * 100) : 0;

    const progCountEl = document.getElementById('emp-progress-count');
    const progPctEl = document.getElementById('emp-progress-percent');
    const progFillEl = document.getElementById('emp-progress-fill');

    if (progCountEl) progCountEl.textContent = `${completedDaily} / ${totalDaily}`;
    if (progPctEl) progPctEl.textContent = `(${dailyPct}%)`;
    if (progFillEl) progFillEl.style.width = `${dailyPct}%`;

    // 3. Filter tasks based on active controls
    let filtered = state.tasks.slice();

    // View filter
    if (state.currentView === 'due_today') {
      filtered = filtered.filter(t => t.due_date === todayStr && t.status !== 'completed');
    } else if (state.currentView === 'high_priority') {
      filtered = filtered.filter(t => (t.priority === 'high' || t.priority === 'urgent') && t.status !== 'completed');
    } else if (state.currentView === 'in_progress') {
      filtered = filtered.filter(t => t.status === 'in_progress');
    } else if (state.currentView === 'overdue') {
      filtered = filtered.filter(t => t.status !== 'completed' && (t.is_overdue || (t.due_date && t.due_date < todayStr)));
    } else if (state.currentView === 'all') {
      // Default view: prioritize active tasks, but include completed
      filtered = filtered.filter(t => t.status !== 'completed');
      if (filtered.length === 0) {
        filtered = state.tasks.slice(); // Fallback to all tasks if no active ones
      }
    }

    // Priority filter dropdown
    if (state.priorityFilter) {
      filtered = filtered.filter(t => (t.priority || '').toLowerCase() === state.priorityFilter.toLowerCase());
    }

    // Inline search filter
    if (state.searchQuery) {
      const q = state.searchQuery.toLowerCase();
      filtered = filtered.filter(t =>
        (t.title && t.title.toLowerCase().includes(q)) ||
        (t.description && t.description.toLowerCase().includes(q))
      );
    }

    // 4. Render items or empty state (Feature 7)
    if (filtered.length === 0) {
      let emptyTitle = "You're all caught up!";
      let emptySubtitle = "No tasks match your selected view. Have a productive day or create a new goal.";
      if (state.currentView === 'overdue') {
        emptyTitle = "Zero overdue tasks!";
        emptySubtitle = "Excellent work staying on top of all deadlines.";
      } else if (state.searchQuery) {
        emptyTitle = "No matching tasks found";
        emptySubtitle = `No tasks matched "${escapeHtml(state.searchQuery)}".`;
      }

      listContainer.innerHTML = `
        <div class="emp-empty-state">
          <div class="emp-empty-icon">
            <svg class="icon icon-lg" viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
          </div>
          <h4 class="emp-empty-title">${emptyTitle}</h4>
          <p class="emp-empty-desc">${emptySubtitle}</p>
          <div class="emp-empty-actions">
            <button type="button" class="emp-action-btn emp-action-primary open-add-task-btn">
              <svg class="icon icon-sm" viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
              <span>Create New Task</span>
            </button>
            <a href="/tasks" class="emp-action-btn">Open Full Board</a>
          </div>
        </div>
      `;
      return;
    }

    // Render task items list
    listContainer.innerHTML = filtered.map(t => {
      const isCompleted = t.status === 'completed';
      const isOverdue = !isCompleted && (t.is_overdue || (t.due_date && t.due_date < todayStr));
      const priorityClass = `badge-${t.priority || 'medium'}`;
      const statusClass = `badge-${(t.status || 'pending').replace('_', '-')}`;

      let dueBadgeHtml = '';
      if (t.due_date) {
        const isTodayDue = t.due_date === todayStr;
        dueBadgeHtml = `
          <span class="emp-meta-item ${isOverdue ? 'emp-overdue' : (isTodayDue ? 'emp-due-today' : '')}">
            <svg class="icon icon-xs" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
            <span>${isOverdue ? 'Overdue: ' : ''}${isTodayDue ? 'Due Today' : t.due_date}</span>
          </span>
        `;
      }

      const categoryHtml = t.category_name ? `
        <span class="emp-meta-item">
          <svg class="icon icon-xs" viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
          <span>${escapeHtml(t.category_name)}</span>
        </span>
      ` : '';

      return `
        <div class="emp-task-item ${isCompleted ? 'completed' : ''}" data-task-id="${t.id}">
          <label class="emp-task-checkbox-label" title="${isCompleted ? 'Mark incomplete' : 'Complete task'}">
            <input type="checkbox" class="emp-task-checkbox" data-id="${t.id}" ${isCompleted ? 'checked' : ''}>
          </label>
          <div class="emp-task-body">
            <div class="emp-task-main">
              <span class="emp-task-title ${isCompleted ? 'completed' : ''}" title="${escapeHtml(t.title)}">${escapeHtml(t.title)}</span>
              <div class="emp-task-meta">
                <span class="badge ${priorityClass}">${escapeHtml((t.priority || 'medium').toUpperCase())}</span>
                <span class="badge ${statusClass}">${escapeHtml((t.status || 'pending').replace('_', ' ').toUpperCase())}</span>
                ${dueBadgeHtml}
                ${categoryHtml}
              </div>
            </div>
            <div class="emp-task-actions">
              <a href="/tasks?task_id=${t.id}" class="emp-btn-icon" title="View Details">
                <svg class="icon icon-sm" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg>
              </a>
            </div>
          </div>
        </div>
      `;
    }).join('');

    // Bind checkbox events for completing/updating tasks
    listContainer.querySelectorAll('.emp-task-checkbox').forEach(cb => {
      cb.addEventListener('change', async (e) => {
        const taskId = e.target.dataset.id;
        const willComplete = e.target.checked;
        await toggleTaskStatus(taskId, willComplete, e.target);
      });
    });
  }

  /**
   * Action: Toggle task completion status
   */
  async function toggleTaskStatus(taskId, willComplete, checkboxEl) {
    try {
      const res = await api('PATCH', `/tasks/${taskId}/complete`, {
        status: willComplete ? 'completed' : 'in_progress'
      });

      if (res && res.data) {
        showToast(willComplete ? 'Task marked as completed!' : 'Task marked as in progress.', 'success');
        await loadAllData();
      }
    } catch (err) {
      // If employee lacks direct complete permission (assigned task requiring submission)
      if (err.status === 403) {
        checkboxEl.checked = !willComplete; // revert checkbox
        showToast('Assigned tasks require submitting work for review before completion.', 'info');
        if (window.TaskManager && typeof window.TaskManager.openTaskModal === 'function') {
          const task = state.tasks.find(t => String(t.id) === String(taskId));
          if (task) window.TaskManager.openTaskModal(task);
        } else {
          window.location.href = `/tasks?task_id=${taskId}`;
        }
      } else {
        checkboxEl.checked = !willComplete;
        showToast(err.message || 'Failed to update task status.', 'error');
      }
    }
  }

  /**
   * Feature 2: Personal Productivity Dashboard
   */
  function renderProductivityDashboard() {
    const totalCount = state.tasks.length;
    const completedTasks = state.tasks.filter(t => t.status === 'completed');
    const remainingTasks = state.tasks.filter(t => t.status !== 'completed');

    // Completed this week: check last 7 days
    const sevenDaysAgo = new Date();
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

    const completedWeek = completedTasks.filter(t => {
      const finishDate = t.completed_at ? new Date(t.completed_at) : (t.updated_at ? new Date(t.updated_at) : null);
      return finishDate && finishDate >= sevenDaysAgo;
    }).length;

    // Set stat values
    const statCompletedWeek = document.getElementById('emp-stat-completed-week');
    if (statCompletedWeek) statCompletedWeek.textContent = completedWeek;

    const statRemaining = document.getElementById('emp-stat-remaining');
    if (statRemaining) statRemaining.textContent = remainingTasks.length;

    // Completion percentage & Donut Chart
    const completionRate = totalCount > 0 ? Math.round((completedTasks.length / totalCount) * 100) : (state.stats?.completion_rate || 0);

    const donutStroke = document.getElementById('emp-donut-stroke');
    if (donutStroke) {
      donutStroke.setAttribute('stroke-dasharray', `${completionRate}, 100`);
    }

    const rateText = document.getElementById('emp-completion-rate-text');
    if (rateText) {
      rateText.textContent = `${completionRate}%`;
    }

    // Active shift ticker
    updateShiftDisplay();

    // Milestones logic
    const todayStr = getLocalDateString(new Date());
    const overdueCount = remainingTasks.filter(t => t.is_overdue || (t.due_date && t.due_date < todayStr)).length;
    const milestoneOverdue = document.getElementById('milestone-zero-overdue');
    if (milestoneOverdue) {
      if (overdueCount === 0) {
        milestoneOverdue.innerHTML = `
          <svg class="icon icon-sm text-success" viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
          <span>All deadlines on track (0 overdue)</span>
        `;
        milestoneOverdue.style.display = 'inline-flex';
      } else {
        milestoneOverdue.innerHTML = `
          <svg class="icon icon-sm text-warning" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
          <span>${overdueCount} task${overdueCount > 1 ? 's' : ''} require attention</span>
        `;
        milestoneOverdue.style.display = 'inline-flex';
      }
    }

    const milestoneCompleted = document.getElementById('milestone-completed-today');
    const milestoneLabel = document.getElementById('milestone-completed-label');
    if (milestoneCompleted && milestoneLabel) {
      if (completedWeek >= 5) {
        milestoneLabel.textContent = `High Performer (${completedWeek} completed this week)`;
        milestoneCompleted.style.display = 'inline-flex';
      } else if (completedTasks.length > 0) {
        milestoneLabel.textContent = `${completedTasks.length} total tasks completed`;
        milestoneCompleted.style.display = 'inline-flex';
      } else {
        milestoneLabel.textContent = 'Ready for a productive week';
        milestoneCompleted.style.display = 'inline-flex';
      }
    }

    // Personal Activity History
    renderActivityStream(completedTasks);
  }

  /**
   * Render Recent Personal Activity History
   */
  function renderActivityStream(completedTasks) {
    const streamContainer = document.getElementById('emp-activity-stream-list');
    if (!streamContainer) return;

    const activities = [];

    // Add recent completed tasks
    completedTasks.slice(0, 4).forEach(t => {
      activities.push({
        type: 'completed',
        title: `Completed task "${t.title}"`,
        time: t.completed_at || t.updated_at,
        icon: '<svg class="icon icon-sm text-success" viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>'
      });
    });

    // Add recent shift session if available
    if (state.attendance?.is_checked_in && state.attendance.active_session?.check_in) {
      activities.push({
        type: 'attendance',
        title: 'Checked in for today\'s shift',
        time: state.attendance.active_session.check_in,
        icon: '<svg class="icon icon-sm text-primary" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>'
      });
    }

    if (activities.length === 0) {
      streamContainer.innerHTML = '<p class="text-muted" style="font-size: var(--font-size-xs); padding: 0.5rem 0;">No recent activity yet today. Complete a task or start a shift to see milestones.</p>';
      return;
    }

    streamContainer.innerHTML = activities.map(act => `
      <div class="emp-activity-item">
        <div class="emp-activity-icon">${act.icon}</div>
        <div class="emp-activity-content">
          <span class="emp-activity-title">${escapeHtml(act.title)}</span>
          <span class="emp-activity-time">${timeAgo(act.time)}</span>
        </div>
      </div>
    `).join('');
  }

  /**
   * Update active shift time display
   */
  function updateShiftDisplay() {
    const shiftEl = document.getElementById('emp-stat-shift-time');
    if (!shiftEl) return;

    if (state.shiftTicker) {
      clearInterval(state.shiftTicker);
      state.shiftTicker = null;
    }

    if (state.attendance && state.attendance.is_checked_in && state.attendance.active_session?.check_in) {
      state.activeShiftStartedAt = new Date(state.attendance.active_session.check_in);
      const tick = () => {
        if (!state.activeShiftStartedAt) return;
        const elapsed = Math.max(0, Math.floor((Date.now() - state.activeShiftStartedAt.getTime()) / 1000));
        shiftEl.textContent = formatHMS(elapsed);
      };
      tick();
      state.shiftTicker = setInterval(tick, 1000);
    } else if (state.attendance && state.attendance.has_completed_shift) {
      const completedSecs = state.attendance.completed_duration_seconds || ((state.attendance.today_duration_hours || 0) * 3600);
      shiftEl.textContent = formatHMS(completedSecs);
    } else {
      shiftEl.textContent = '00:00:00';
    }
  }

  /**
   * Feature 5: Daily Schedule (Meetings + Today's Deadlines)
   */
  function renderDailySchedule() {
    const timeline = document.getElementById('emp-daily-timeline');
    if (!timeline) return;

    const todayStr = getLocalDateString(new Date());
    const items = [];

    // 1. Add meetings
    state.meetings.forEach(m => {
      items.push({
        type: 'meeting',
        time: m.start_time || m.scheduled_at || m.date || 'Today',
        title: m.title || 'Team Sync',
        location: m.location || m.meeting_link || 'Online',
        link: '/calendar'
      });
    });

    // 2. Add tasks due today
    state.tasks.filter(t => t.due_date === todayStr && t.status !== 'completed').forEach(t => {
      items.push({
        type: 'deadline',
        time: 'Deadline',
        title: t.title,
        location: t.category_name || 'Assigned Task',
        link: `/tasks?task_id=${t.id}`
      });
    });

    // Empty state (Feature 7)
    if (items.length === 0) {
      timeline.innerHTML = `
        <div class="emp-empty-state" style="padding: 1.5rem 0;">
          <div class="emp-empty-icon" style="width: 40px; height: 40px;">
            <svg class="icon" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
          </div>
          <h4 class="emp-empty-title" style="font-size: var(--font-size-sm);">Clear Schedule Today</h4>
          <p class="emp-empty-desc" style="font-size: var(--font-size-xs);">No meetings or due dates scheduled for today.</p>
          <div class="emp-empty-actions">
            <a href="/calendar" class="emp-action-btn">Open Calendar</a>
          </div>
        </div>
      `;
      return;
    }

    timeline.innerHTML = items.map(item => {
      const isMeeting = item.type === 'meeting';
      const markerClass = isMeeting ? 'marker-meeting' : 'marker-deadline';
      const tagClass = isMeeting ? 'badge-primary' : 'badge-urgent';
      const tagLabel = isMeeting ? 'Meeting' : 'Due Today';

      return `
        <div class="emp-timeline-item">
          <div class="emp-timeline-marker ${markerClass}"></div>
          <div class="emp-timeline-content">
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.5rem;">
              <span class="emp-timeline-time">${escapeHtml(item.time)}</span>
              <span class="badge ${tagClass}" style="font-size: 0.65rem;">${tagLabel}</span>
            </div>
            <a href="${item.link}" class="emp-timeline-desc" style="display: block; font-weight: 600; text-decoration: none; color: var(--color-text);">
              ${escapeHtml(item.title)}
            </a>
            <span class="text-muted" style="font-size: var(--font-size-xs);">${escapeHtml(item.location)}</span>
          </div>
        </div>
      `;
    }).join('');
  }

  /**
   * Feature 4: Employee Collaboration Center
   */
  function renderCollaborationCenter() {
    const container = document.getElementById('emp-collab-items-container');
    if (!container) return;

    if (state.notifications.length === 0) {
      container.innerHTML = `
        <div class="emp-empty-state" style="padding: 1.5rem 0;">
          <div class="emp-empty-icon" style="width: 40px; height: 40px;">
            <svg class="icon" viewBox="0 0 24 24"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path><path d="M13.73 21a2 2 0 0 1-3.46 0"></path></svg>
          </div>
          <h4 class="emp-empty-title" style="font-size: var(--font-size-sm);">No New Notifications</h4>
          <p class="emp-empty-desc" style="font-size: var(--font-size-xs);">You're up to date on all team mentions and reviews.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = state.notifications.slice(0, 5).map(n => {
      const isUnread = !n.is_read;
      return `
        <div class="emp-collab-item ${isUnread ? 'unread' : ''}" data-id="${n.id}">
          <div class="emp-collab-dot ${isUnread ? 'active' : ''}"></div>
          <div class="emp-collab-body">
            <span class="emp-collab-item-title">${escapeHtml(n.title || 'Update')}</span>
            <p class="emp-collab-item-msg">${escapeHtml(n.message || '')}</p>
            <span class="emp-collab-item-time">${timeAgo(n.created_at)}</span>
          </div>
          ${n.link ? `<a href="${n.link}" class="emp-btn-icon" title="View"><svg class="icon icon-xs" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg></a>` : ''}
        </div>
      `;
    }).join('');
  }

  /**
   * Render notification badge count in Quick Actions
   */
  function renderNotificationPill() {
    const pill = document.getElementById('emp-notif-pill');
    if (!pill) return;
    const unread = state.notifications.filter(n => !n.is_read).length;
    if (unread > 0) {
      pill.textContent = unread;
      pill.style.display = 'inline-flex';
    } else {
      pill.style.display = 'none';
    }
  }

  /**
   * Bind all event handlers
   */
  function bindEvents() {
    // 1. Task View Filter Tabs
    document.querySelectorAll('.emp-tab-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        document.querySelectorAll('.emp-tab-btn').forEach(b => {
          b.classList.remove('active');
          b.setAttribute('aria-selected', 'false');
        });
        const target = e.currentTarget;
        target.classList.add('active');
        target.setAttribute('aria-selected', 'true');
        state.currentView = target.dataset.view || 'all';
        renderMyDayTasks();
      });
    });

    // 2. Priority Select Filter
    const prioritySelect = document.getElementById('emp-priority-select-filter');
    if (prioritySelect) {
      prioritySelect.addEventListener('change', (e) => {
        state.priorityFilter = e.target.value;
        renderMyDayTasks();
      });
    }

    // 3. Search Filter
    const searchInput = document.getElementById('emp-task-inline-search');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        state.searchQuery = e.target.value.trim();
        renderMyDayTasks();
      });
    }

    // 4. Collaboration: Mark All Read
    const markReadBtn = document.getElementById('emp-collab-mark-read');
    if (markReadBtn) {
      markReadBtn.addEventListener('click', async () => {
        try {
          await api('POST', '/notifications/mark-all-read');
          state.notifications.forEach(n => { n.is_read = true; });
          renderCollaborationCenter();
          renderNotificationPill();
          showToast('All notifications marked as read.', 'success');
        } catch (err) {
          showToast(err.message || 'Failed to mark notifications read.', 'error');
        }
      });
    }

    // 5. Quick Actions: Notifications button scrolls to collaboration section
    const notifBtn = document.getElementById('emp-action-notifications-btn');
    if (notifBtn) {
      notifBtn.addEventListener('click', () => {
        const collabSection = document.getElementById('emp-collab-section');
        if (collabSection) {
          collabSection.scrollIntoView({ behavior: 'smooth' });
        }
      });
    }

    // 6. Quick Action: New Task Trigger
    const newTaskBtn = document.getElementById('emp-action-new-task');
    if (newTaskBtn) {
      newTaskBtn.addEventListener('click', () => {
        if (window.TaskManager && typeof window.TaskManager.openTaskModal === 'function') {
          window.TaskManager.openTaskModal();
        } else {
          const baseModal = document.getElementById('task-modal');
          if (baseModal) {
            baseModal.classList.add('active');
          } else {
            window.location.href = '/tasks?action=new';
          }
        }
      });
    }
  }

  // Initial Boot
  document.addEventListener('DOMContentLoaded', () => {
    bindEvents();
    loadAllData();
  });

  // Expose global hook for refresh if other scripts perform updates
  window.EmployeeDashboard = {
    refresh: loadAllData
  };

})();
