/**
 * TaskNest Authentication Controller
 */

document.addEventListener('DOMContentLoaded', () => {
  // Setup password toggles
  document.querySelectorAll('.password-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const wrapper = btn.closest('.password-wrapper');
      const input = wrapper ? wrapper.querySelector('input') : btn.previousElementSibling;
      if (!input) return;
      if (input.type === 'password') {
        input.type = 'text';
        btn.innerHTML = `<svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>`;
      } else {
        input.type = 'password';
        btn.innerHTML = `<svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;
      }
    });
  });

  // Login Form
  const loginForm = document.getElementById('login-form');
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const submitBtn = loginForm.querySelector('button[type="submit"]');
      const errorBanner = document.getElementById('login-error');
      if (errorBanner) {
        errorBanner.style.display = 'none';
        errorBanner.textContent = '';
      }

      const email = document.getElementById('email').value.trim();
      const password = document.getElementById('password').value;
      const remember = document.getElementById('remember')?.checked || false;

      if (!email || !password) {
        if (errorBanner) {
          errorBanner.textContent = 'Please enter both email and password.';
          errorBanner.style.display = 'flex';
        }
        return;
      }

      submitBtn.disabled = true;
      submitBtn.innerHTML = 'Signing in...';

      try {
        const requiredRole = loginForm.dataset.requiredRole || '';
        const result = await api('POST', '/auth/login', { email, password, remember, required_role: requiredRole });
        const user = result.data || {};
        showToast('Welcome back to TaskNest!', 'success');
        if (user.role === 'super_admin' || user.role === 'admin' || user.role === 'admin_hr') {
          window.location.href = '/admin/dashboard';
        } else if (user.role === 'team_lead') {
          window.location.href = '/lead/dashboard';
        } else {
          window.location.href = '/employee/dashboard';
        }
      } catch (err) {
        if (errorBanner) {
          errorBanner.textContent = err.message || 'Invalid email or password.';
          errorBanner.style.display = 'flex';
        }
        submitBtn.disabled = false;
        submitBtn.innerHTML = 'Sign In';
      }
    });
  }

  // Signup Form
  const signupForm = document.getElementById('signup-form');
  if (signupForm) {
    signupForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const submitBtn = signupForm.querySelector('button[type="submit"]');
      const errorBanner = document.getElementById('signup-error');
      if (errorBanner) {
        errorBanner.style.display = 'none';
        errorBanner.textContent = '';
      }

      const fullName = document.getElementById('full_name').value.trim();
      const email = document.getElementById('email').value.trim();
      const password = document.getElementById('password').value;
      const confirmPassword = document.getElementById('confirm_password').value;

      if (!fullName || !email || !password) {
        if (errorBanner) {
          errorBanner.textContent = 'Please fill in all required fields.';
          errorBanner.style.display = 'flex';
        }
        return;
      }

      if (password.length < 6) {
        if (errorBanner) {
          errorBanner.textContent = 'Password must be at least 6 characters.';
          errorBanner.style.display = 'flex';
        }
        return;
      }

      if (password !== confirmPassword) {
        if (errorBanner) {
          errorBanner.textContent = 'Passwords do not match.';
          errorBanner.style.display = 'flex';
        }
        return;
      }

      submitBtn.disabled = true;
      submitBtn.innerHTML = 'Creating account...';

      try {
        await api('POST', '/auth/signup', {
          full_name: fullName,
          email,
          password
        });
        showToast('Account created successfully!', 'success');
        window.location.href = '/employee/dashboard';
      } catch (err) {
        if (errorBanner) {
          errorBanner.textContent = err.message || 'Registration failed.';
          errorBanner.style.display = 'flex';
        }
        submitBtn.disabled = false;
        submitBtn.innerHTML = 'Create Account';
      }
    });
  }

  // Logout Handlers
  document.querySelectorAll('.logout-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      try {
        await api('POST', '/auth/logout');
        window.location.href = '/login';
      } catch (err) {
        window.location.href = '/login';
      }
    });
  });

  // Mobile Sidebar Toggle
  const mobileToggle = document.getElementById('mobile-sidebar-toggle');
  const sidebar = document.querySelector('.app-sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');

  if (mobileToggle && sidebar && backdrop) {
    mobileToggle.addEventListener('click', () => {
      sidebar.classList.toggle('is-open');
      backdrop.classList.toggle('is-open');
    });
    backdrop.addEventListener('click', () => {
      sidebar.classList.remove('is-open');
      backdrop.classList.remove('is-open');
    });
  }
});
