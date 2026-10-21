/**
 * TaskNest Authentication Integration (auth.js)
 * Created by M5 (Frontend 1 - Layout & Auth UI)
 *
 * Connects to Flask backend endpoints:
 * - POST /api/auth/register  {username, email, password}
 * - POST /api/auth/login     {email, password}
 * - POST /api/auth/logout
 *
 * Strictly uses session cookies (credentials: 'same-origin').
 * No passwords or authentication proof stored in localStorage.
 */

// Email regex pattern
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Clear all inline and global form errors
 * @param {HTMLFormElement} form 
 * @param {string} alertId 
 */
function clearFormErrors(form, alertId) {
  if (!form) return;
  const groups = form.querySelectorAll('.form-group');
  groups.forEach(group => {
    group.classList.remove('has-error');
    const input = group.querySelector('.input');
    if (input) {
      input.removeAttribute('aria-invalid');
      input.classList.remove('input-error');
    }
    const errEl = group.querySelector('.form-error-msg');
    if (errEl) {
      errEl.textContent = '';
      errEl.style.display = 'none';
    }
  });

  if (alertId) {
    const alertEl = document.getElementById(alertId);
    if (alertEl) {
      alertEl.style.display = 'none';
      alertEl.className = 'auth-alert';
      alertEl.innerHTML = '';
    }
  }
}

/**
 * Display inline error for an input field
 * @param {string} fieldId 
 * @param {string} message 
 */
function setFieldError(fieldId, message) {
  const input = document.getElementById(fieldId);
  const group = document.getElementById(`group-${fieldId}`);
  const errorEl = document.getElementById(`${fieldId}-error`);

  if (group) group.classList.add('has-error');
  if (input) {
    input.classList.add('input-error');
    input.setAttribute('aria-invalid', 'true');
  }
  if (errorEl) {
    errorEl.textContent = message;
    errorEl.style.display = 'block';
  }
}

/**
 * Display a banner alert on the auth card
 * @param {string} alertId 
 * @param {string} message 
 * @param {'error' | 'success'} type 
 */
function setGlobalAlert(alertId, message, type = 'error') {
  const alertEl = document.getElementById(alertId);
  if (!alertEl) return;

  const isError = type === 'error';
  alertEl.className = `auth-alert ${isError ? 'auth-alert-error' : 'auth-alert-success'}`;
  
  const iconSvg = isError
    ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`
    : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;"><polyline points="20 6 9 17 4 12"/></svg>`;

  alertEl.innerHTML = `${iconSvg}<span>${typeof escapeHtml === 'function' ? escapeHtml(message) : message}</span>`;
  alertEl.style.display = 'flex';
}

/**
 * Initialize Signup Form
 */
function initSignup() {
  const form = document.getElementById('signupForm');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearFormErrors(form, 'signupAlert');

    const usernameInput = document.getElementById('username');
    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');
    const confirmPasswordInput = document.getElementById('confirmPassword');
    const termsInput = document.getElementById('terms');
    const submitBtn = document.getElementById('signupSubmitBtn');

    const username = (usernameInput?.value || '').trim();
    const email = (emailInput?.value || '').trim();
    const password = passwordInput?.value || '';
    const confirmPassword = confirmPasswordInput?.value || '';
    const terms = termsInput ? termsInput.checked : false;

    let hasErrors = false;
    let firstErrorField = null;

    // Validate Username
    if (!username) {
      setFieldError('username', 'Full name is required.');
      hasErrors = true;
      if (!firstErrorField) firstErrorField = usernameInput;
    } else if (username.length < 2) {
      setFieldError('username', 'Name must be at least 2 characters.');
      hasErrors = true;
      if (!firstErrorField) firstErrorField = usernameInput;
    }

    // Validate Email
    if (!email) {
      setFieldError('email', 'Email address is required.');
      hasErrors = true;
      if (!firstErrorField) firstErrorField = emailInput;
    } else if (!EMAIL_REGEX.test(email)) {
      setFieldError('email', 'Please enter a valid email address.');
      hasErrors = true;
      if (!firstErrorField) firstErrorField = emailInput;
    }

    // Validate Password
    if (!password) {
      setFieldError('password', 'Password is required.');
      hasErrors = true;
      if (!firstErrorField) firstErrorField = passwordInput;
    } else if (password.length < 8) {
      setFieldError('password', 'Password must be at least 8 characters long.');
      hasErrors = true;
      if (!firstErrorField) firstErrorField = passwordInput;
    }

    // Validate Confirm Password
    if (!confirmPassword) {
      setFieldError('confirmPassword', 'Please confirm your password.');
      hasErrors = true;
      if (!firstErrorField) firstErrorField = confirmPasswordInput;
    } else if (password !== confirmPassword) {
      setFieldError('confirmPassword', 'Passwords do not match.');
      hasErrors = true;
      if (!firstErrorField) firstErrorField = confirmPasswordInput;
    }

    // Validate Terms
    if (!terms) {
      setFieldError('terms', 'You must agree to the Terms of Service and Privacy Policy.');
      hasErrors = true;
      if (!firstErrorField) firstErrorField = termsInput;
    }

    if (hasErrors) {
      if (firstErrorField) firstErrorField.focus();
      return;
    }

    // Submit payload to POST /api/auth/register
    setLoading(submitBtn, true, 'Creating account...');
    try {
      const response = await fetch('/api/auth/register', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        credentials: 'same-origin',
        body: JSON.stringify({
          username,
          email,
          password
        })
      });

      const data = await response.json().catch(() => ({}));

      if (response.status === 201) {
        if (typeof toast === 'function') {
          toast('Account created successfully! Redirecting to login...', 'success');
        }
        setGlobalAlert('signupAlert', 'Account created successfully! Redirecting to login...', 'success');
        setTimeout(() => {
          window.location.href = '/login?registered=1';
        }, 1200);
      } else if (response.status === 409) {
        setFieldError('email', data.error || 'Email is already registered.');
        setGlobalAlert('signupAlert', data.error || 'This email is already registered. Please log in instead.', 'error');
        if (emailInput) emailInput.focus();
        setLoading(submitBtn, false);
      } else {
        const errorMsg = data.error || 'Registration failed. Please check your details and try again.';
        setGlobalAlert('signupAlert', errorMsg, 'error');
        setLoading(submitBtn, false);
      }
    } catch (err) {
      console.error('Registration network error:', err);
      setGlobalAlert('signupAlert', 'Network error. Please check your internet connection and try again.', 'error');
      setLoading(submitBtn, false);
    }
  });
}

/**
 * Initialize Login Form
 */
function initLogin() {
  const form = document.getElementById('loginForm');
  if (!form) return;

  // Check URL query parameters for registration notice
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('registered') === '1') {
    setGlobalAlert('loginAlert', 'Account created successfully! Please log in with your credentials.', 'success');
    if (typeof toast === 'function') {
      toast('Registration complete! Please log in.', 'success');
    }
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearFormErrors(form, 'loginAlert');

    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');
    const submitBtn = document.getElementById('loginSubmitBtn');

    const email = (emailInput?.value || '').trim();
    const password = passwordInput?.value || '';

    let hasErrors = false;
    let firstErrorField = null;

    // Validate Email
    if (!email) {
      setFieldError('email', 'Email address is required.');
      hasErrors = true;
      if (!firstErrorField) firstErrorField = emailInput;
    } else if (!EMAIL_REGEX.test(email)) {
      setFieldError('email', 'Please enter a valid email address.');
      hasErrors = true;
      if (!firstErrorField) firstErrorField = emailInput;
    }

    // Validate Password
    if (!password) {
      setFieldError('password', 'Password is required.');
      hasErrors = true;
      if (!firstErrorField) firstErrorField = passwordInput;
    }

    if (hasErrors) {
      if (firstErrorField) firstErrorField.focus();
      return;
    }

    // Submit payload to POST /api/auth/login
    setLoading(submitBtn, true, 'Logging in...');
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        credentials: 'same-origin',
        body: JSON.stringify({
          email,
          password
        })
      });

      const data = await response.json().catch(() => ({}));

      if (response.status === 200) {
        if (typeof toast === 'function') {
          toast('Welcome back! Redirecting...', 'success');
        }
        setGlobalAlert('loginAlert', 'Logged in successfully! Redirecting...', 'success');
        setTimeout(() => {
          window.location.href = '/dashboard';
        }, 800);
      } else if (response.status === 401) {
        setFieldError('password', 'Invalid email or password.');
        setGlobalAlert('loginAlert', data.error || 'Invalid credentials. Please verify your email and password.', 'error');
        setLoading(submitBtn, false);
      } else {
        const errorMsg = data.error || 'Unable to log in. Please try again later.';
        setGlobalAlert('loginAlert', errorMsg, 'error');
        setLoading(submitBtn, false);
      }
    } catch (err) {
      console.error('Login network error:', err);
      setGlobalAlert('loginAlert', 'Network error. Please check your internet connection and try again.', 'error');
      setLoading(submitBtn, false);
    }
  });
}

/**
 * Handle Logout
 */
async function handleLogout() {
  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn && typeof setLoading === 'function') {
    setLoading(logoutBtn, true, 'Logging out...');
  }

  try {
    const res = await fetch('/api/auth/logout', {
      method: 'POST',
      headers: {
        'Accept': 'application/json'
      },
      credentials: 'same-origin'
    });

    if (res.ok) {
      if (typeof toast === 'function') {
        toast('Logged out successfully', 'info');
      }
    }
  } catch (err) {
    console.error('Logout error:', err);
  } finally {
    window.location.href = '/login';
  }
}

/**
 * Bind global events
 */
document.addEventListener('DOMContentLoaded', () => {
  initSignup();
  initLogin();

  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', (e) => {
      e.preventDefault();
      handleLogout();
    });
  }
});

