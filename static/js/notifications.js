(function () {
  'use strict';

  const bell = document.getElementById('notification-bell');
  if (!bell) return;

  const badge = document.getElementById('notification-unread-count');
  let panel;

  function escapeHtml(value) {
    const el = document.createElement('div');
    el.textContent = value == null ? '' : String(value);
    return el.innerHTML;
  }

  function ensurePanel() {
    if (panel) return panel;
    panel = document.createElement('div');
    panel.className = 'notification-panel';
    panel.setAttribute('role', 'dialog');
    panel.innerHTML = '<div class="notification-panel-header"><strong>Notifications</strong><button class="btn btn-ghost btn-xs" id="mark-all-notifications">Mark all read</button></div><div id="notification-list" class="notification-list"></div><a class="notification-activity-link" href="/activity">View activity</a>';
    bell.parentElement.appendChild(panel);
    panel.querySelector('#mark-all-notifications').addEventListener('click', markAllRead);
    return panel;
  }

  async function loadNotifications() {
    const root = ensurePanel();
    const list = root.querySelector('#notification-list');
    list.innerHTML = '<p class="text-muted notification-empty">Loading...</p>';
    try {
      const result = await window.API.get('/api/notifications?per_page=10');
      const items = result.data.items || [];
      if (!items.length) {
        list.innerHTML = '<p class="text-muted notification-empty">No notifications yet.</p>';
      } else {
        list.innerHTML = items.map((item) => {
          const taskLink = item.task_id ? `/tasks/${item.task_id}` : '#';
          return `<div class="notification-item ${item.is_read ? '' : 'is-unread'}" data-id="${item.id}">
            <a href="${taskLink}" class="notification-item-link"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.message)}</span><small>${new Date(item.created_at).toLocaleString()}</small></a>
            ${item.is_read ? '' : '<button class="btn btn-ghost btn-xs mark-notification-read">Mark read</button>'}
          </div>`;
        }).join('');
        list.querySelectorAll('.mark-notification-read').forEach((button) => {
          button.addEventListener('click', () => markRead(button.closest('.notification-item').dataset.id));
        });
      }
      updateBadge(result.data.unread_count || 0);
    } catch (error) {
      list.innerHTML = `<p class="text-danger notification-empty">${escapeHtml(error.message)}</p>`;
    }
  }

  function updateBadge(count) {
    badge.textContent = count;
    badge.hidden = !count;
  }

  async function markRead(id) {
    await window.API.patch(`/api/notifications/${id}/read`);
    await loadNotifications();
  }

  async function markAllRead() {
    await window.API.post('/api/notifications/read-all');
    await loadNotifications();
  }

  bell.addEventListener('click', async () => {
    const open = panel && panel.classList.toggle('is-open');
    bell.setAttribute('aria-expanded', String(Boolean(open)));
    if (open) await loadNotifications();
  });

  document.addEventListener('click', (event) => {
    if (panel && panel.classList.contains('is-open') && !bell.contains(event.target) && !panel.contains(event.target)) {
      panel.classList.remove('is-open');
      bell.setAttribute('aria-expanded', 'false');
    }
  });

  window.API.get('/api/notifications/unread-count').then((result) => updateBadge(result.data.unread_count || 0)).catch(() => {});
})();
