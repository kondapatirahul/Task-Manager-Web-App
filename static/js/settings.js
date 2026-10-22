/**
 * TaskNest — Settings Page Controller
 *
 * Handles:
 *  - Profile form: display name update via PUT /api/auth/profile
 *  - Password form: password change via POST /api/auth/change-password
 *  - Password strength indicator
 *  - Password visibility toggles
 *  - Immediate DOM updates after successful profile save
 */

document.addEventListener('DOMContentLoaded', () => {

  /* ── Utilities ─────────────────────────────────────────────────────────── */

  function showAlert(el, message, type = 'error') {
    el.textContent  = message;
    el.className    = `alert alert-${type}`;
    el.style.display = 'flex';
    el.setAttribute('role', 'alert');
  }

  function clearAlert(el) {
    el.style.display = 'none';
    el.textContent   = '';
  }

  function setLoading(btn, originalHtml, loading) {
    btn.disabled   = loading;
    btn.innerHTML  = loading ? '<span>Saving…</span>' : originalHtml;
  }

  /* ── Password visibility toggles ───────────────────────────────────────── */

  document.querySelectorAll('.password-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const container = btn.closest('.password-wrapper, .input-password-wrapper') || btn.parentElement;
      const input = container ? container.querySelector('input') : (btn.previousElementSibling?.tagName === 'INPUT' ? btn.previousElementSibling : btn.previousElementSibling?.querySelector('input'));
      if (!input) return;
      const isHidden = input.type === 'password';
      input.type = isHidden ? 'text' : 'password';
      btn.setAttribute('aria-label', isHidden ? 'Hide password' : 'Show password');
      btn.innerHTML = isHidden
        ? `<svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>`
        : `<svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;
    });
  });

  /* ── Password strength indicator ───────────────────────────────────────── */

  const newPasswordInput = document.getElementById('new-password');
  const strengthFill     = document.getElementById('pw-strength-fill');
  const strengthLabel    = document.getElementById('pw-strength-label');

  function scorePassword(pw) {
    if (!pw) return 0;
    let score = 0;
    if (pw.length >= 8)  score++;
    if (pw.length >= 12) score++;
    if (/[A-Z]/.test(pw)) score++;
    if (/[0-9]/.test(pw)) score++;
    if (/[^A-Za-z0-9]/.test(pw)) score++;
    return score; // 0-5
  }

  const strengthConfig = [
    { label: '',          color: 'transparent', pct: 0   },
    { label: 'Weak',      color: '#D94C4C',     pct: 20  },
    { label: 'Fair',      color: '#E6A23C',     pct: 40  },
    { label: 'Good',      color: '#25845A',     pct: 60  },
    { label: 'Strong',    color: '#173F35',     pct: 80  },
    { label: 'Excellent', color: '#173F35',     pct: 100 },
  ];

  if (newPasswordInput && strengthFill && strengthLabel) {
    newPasswordInput.addEventListener('input', () => {
      const score  = scorePassword(newPasswordInput.value);
      const config = strengthConfig[score];
      strengthFill.style.width           = `${config.pct}%`;
      strengthFill.style.backgroundColor = config.color;
      strengthLabel.textContent          = config.label;
      strengthLabel.style.color          = config.color;
    });
  }

  /* ── Profile Form ──────────────────────────────────────────────────────── */

  const profileForm    = document.getElementById('profile-form');
  const profileError   = document.getElementById('profile-error');
  const profileSuccess = document.getElementById('profile-success');
  const profileSaveBtn = document.getElementById('profile-save-btn');
  const saveBtnHtml    = profileSaveBtn ? profileSaveBtn.innerHTML : '';

  if (profileForm) {
    profileForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      clearAlert(profileError);
      clearAlert(profileSuccess);

      const fullName = (document.getElementById('settings-full-name')?.value || '').trim();

      if (!fullName) {
        showAlert(profileError, 'Display name is required.');
        return;
      }
      if (fullName.length < 2) {
        showAlert(profileError, 'Display name must be at least 2 characters.');
        return;
      }
      if (fullName.length > 100) {
        showAlert(profileError, 'Display name must be 100 characters or fewer.');
        return;
      }

      setLoading(profileSaveBtn, saveBtnHtml, true);

      try {
        const res = await api('PUT', '/auth/profile', { full_name: fullName });

        showAlert(profileSuccess, res.message || 'Profile updated successfully.', 'success');

        // Update DOM immediately so sidebar and avatar reflect the change
        const updatedName = res.data?.full_name || fullName;
        const initial = updatedName[0]?.toUpperCase() || '?';

        const avatarPreview = document.getElementById('settings-avatar-preview');
        const displayName   = document.getElementById('settings-display-name');
        const sidebarName   = document.querySelector('.sidebar-user-name');
        const headerAvatar  = document.querySelector('.user-avatar-badge');

        if (avatarPreview) avatarPreview.textContent = initial;
        if (displayName)   displayName.textContent   = updatedName;
        if (sidebarName)   sidebarName.textContent   = updatedName;
        if (headerAvatar)  headerAvatar.textContent   = initial;

        showToast('Profile updated successfully!', 'success');
      } catch (err) {
        showAlert(profileError, err.message || 'Failed to update profile.');
        showToast(err.message || 'Profile update failed.', 'error');
      } finally {
        setLoading(profileSaveBtn, saveBtnHtml, false);
      }
    });
  }

  /* ── Password Form ─────────────────────────────────────────────────────── */

  const passwordForm    = document.getElementById('password-form');
  const passwordError   = document.getElementById('password-error');
  const passwordSuccess = document.getElementById('password-success');
  const passwordSaveBtn = document.getElementById('password-save-btn');
  const pwBtnHtml       = passwordSaveBtn ? passwordSaveBtn.innerHTML : '';

  if (passwordForm) {
    passwordForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      clearAlert(passwordError);
      clearAlert(passwordSuccess);

      const currentPw  = document.getElementById('current-password')?.value || '';
      const newPw      = document.getElementById('new-password')?.value     || '';
      const confirmPw  = document.getElementById('confirm-password')?.value  || '';

      // Client-side pre-validation (server enforces all rules too)
      if (!currentPw || !newPw || !confirmPw) {
        showAlert(passwordError, 'All password fields are required.');
        return;
      }
      if (newPw.length < 8) {
        showAlert(passwordError, 'New password must be at least 8 characters.');
        return;
      }
      if (newPw !== confirmPw) {
        showAlert(passwordError, 'New password and confirmation do not match.');
        return;
      }

      setLoading(passwordSaveBtn, pwBtnHtml, true);

      try {
        const res = await api('POST', '/auth/change-password', {
          current_password: currentPw,
          new_password:     newPw,
          confirm_password: confirmPw,
        });

        showAlert(passwordSuccess, res.message || 'Password changed successfully.', 'success');
        passwordForm.reset();

        // Reset strength indicator
        if (strengthFill)  { strengthFill.style.width = '0%'; }
        if (strengthLabel) { strengthLabel.textContent = ''; }

        showToast('Password changed successfully!', 'success');
      } catch (err) {
        showAlert(passwordError, err.message || 'Failed to change password.');
        showToast(err.message || 'Password change failed.', 'error');
      } finally {
        setLoading(passwordSaveBtn, pwBtnHtml, false);
      }
    });
  }

});
