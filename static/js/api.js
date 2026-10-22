/**
 * TaskNest API Client and Toast Notification System
 */

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return null;
}

function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta && meta.content) return meta.content;
  return getCookie('csrf_token') || '';
}

async function api(method, path, body = null) {
  const headers = {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
  };

  const upperMethod = method.toUpperCase();
  if (!['GET', 'HEAD', 'OPTIONS'].includes(upperMethod)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      headers['X-CSRFToken'] = csrfToken;
      headers['X-CSRF-Token'] = csrfToken;
    }
  }

  const opts = {
    method: upperMethod,
    headers,
    credentials: 'same-origin'
  };

  if (body !== null && upperMethod !== 'GET') {
    opts.body = JSON.stringify(body);
  }

  try {
    const url = path.startsWith('/api') ? path : `/api${path.startsWith('/') ? '' : '/'}${path}`;
    const res = await fetch(url, opts);
    let data;
    try {
      data = await res.json();
    } catch (e) {
      data = { ok: false, error: 'Server response could not be parsed.' };
    }

    if (!res.ok || data.ok === false) {
      const errorMsg = data.error || (data.data && data.data.error) || `Request failed (${res.status})`;
      // Do not globally redirect on 401: public pages and optional widgets may
      // legitimately call protected endpoints. The calling page decides what to do.
      const err = new Error(errorMsg);
      err.status = res.status;
      err.data = data;
      throw err;
    }

    return data;
  } catch (err) {
    throw err;
  }
}

/** Toast Notifications */
function showToast(message, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <svg class="icon" viewBox="0 0 24 24">
      ${type === 'success' ? '<path d="M20 6L9 17l-5-5"></path>' :
        type === 'error' ? '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line>' :
        '<circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line>'}
    </svg>
    <span>${message}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(8px)';
    toast.style.transition = 'all 0.2s ease-out';
    setTimeout(() => toast.remove(), 200);
  }, 3500);
}
