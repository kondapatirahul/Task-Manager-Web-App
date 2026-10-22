/**
 * static/js/employees.js
 * TaskNest Employee Directory and Administration Client
 */

document.addEventListener('DOMContentLoaded', () => {
  let allEmployees = [];
  let allDepartments = [];
  let allTeams = [];
  let currentViewingEmployee = null;

  // DOM Elements
  const employeeGrid = document.getElementById('employee-list-container');
  const searchInput = document.getElementById('employee-search');
  const filterDept = document.getElementById('filter-department');
  const filterTeam = document.getElementById('filter-team');
  const filterRole = document.getElementById('filter-role');
  const filterStatus = document.getElementById('filter-status');

  const statTotal = document.getElementById('stat-total-employees');
  const statActive = document.getElementById('stat-active-employees');
  const statDepts = document.getElementById('stat-departments-count');
  const statTeams = document.getElementById('stat-teams-count');

  // Modals
  const inviteModal = document.getElementById('invite-employee-modal');
  const openInviteBtn = document.getElementById('open-invite-employee-btn');
  const closeInviteBtn = document.getElementById('close-invite-modal-btn');
  const cancelInviteBtn = document.getElementById('cancel-invite-btn');
  const inviteForm = document.getElementById('invite-employee-form');

  const successModal = document.getElementById('activation-success-modal');
  const closeSuccessBtn = document.getElementById('close-success-modal-btn');
  const ackSuccessBtn = document.getElementById('ack-success-btn');

  const detailModal = document.getElementById('employee-detail-modal');
  const closeDetailBtn = document.getElementById('close-detail-modal-btn');
  const cancelDetailBtn = document.getElementById('cancel-detail-btn');
  const editForm = document.getElementById('edit-employee-form');
  const toggleStatusBtn = document.getElementById('toggle-account-status-btn');

  // ── Initial Load ───────────────────────────────────────────────────────────
  async function loadInitialData() {
    try {
      const [deptRes, teamRes] = await Promise.all([
        api('GET', '/api/departments'),
        api('GET', '/api/teams')
      ]);

      allDepartments = deptRes.data || [];
      allTeams = teamRes.data || [];

      // Populate filter dropdowns
      populateSelectOptions(filterDept, allDepartments, 'All Departments');
      populateSelectOptions(filterTeam, allTeams, 'All Teams');

      if (statDepts) statDepts.textContent = allDepartments.length;
      if (statTeams) statTeams.textContent = allTeams.length;

      await loadEmployees();
    } catch (err) {
      showToast(err.message || 'Failed to load initial directory data.', 'error');
    }
  }

  function populateSelectOptions(selectEl, items, defaultLabel) {
    if (!selectEl) return;
    const currentVal = selectEl.value;
    selectEl.innerHTML = `<option value="">${defaultLabel}</option>`;
    items.forEach(item => {
      const opt = document.createElement('option');
      opt.value = item.id;
      opt.textContent = item.name;
      selectEl.appendChild(opt);
    });
    selectEl.value = currentVal;
  }

  async function loadEmployees() {
    try {
      const res = await api('GET', '/api/employees');
      allEmployees = res.data || [];
      renderEmployees();
      updateStats();
    } catch (err) {
      showToast(err.message || 'Failed to load employees.', 'error');
    }
  }

  function updateStats() {
    if (statTotal) statTotal.textContent = allEmployees.length;
    if (statActive) statActive.textContent = allEmployees.filter(e => e.account_active).length;
  }

  // ── Filtering and Rendering ────────────────────────────────────────────────
  function getFilteredEmployees() {
    const q = (searchInput ? searchInput.value : '').toLowerCase().trim();
    const deptId = filterDept ? filterDept.value : '';
    const teamId = filterTeam ? filterTeam.value : '';
    const roleVal = filterRole ? filterRole.value : '';
    const statusVal = filterStatus ? filterStatus.value : 'active';

    return allEmployees.filter(emp => {
      // Query filter
      if (q) {
        const nameMatch = (emp.full_name || '').toLowerCase().includes(q);
        const emailMatch = (emp.email || '').toLowerCase().includes(q);
        const titleMatch = (emp.job_title || '').toLowerCase().includes(q);
        const userMatch = (emp.username || '').toLowerCase().includes(q);
        if (!nameMatch && !emailMatch && !titleMatch && !userMatch) return false;
      }

      // Department filter
      if (deptId && String(emp.department_id) !== String(deptId)) return false;

      // Team filter
      if (teamId) {
        const inTeam = emp.teams && emp.teams.some(t => String(t.id) === String(teamId));
        if (!inTeam) return false;
      }

      // Role filter
      if (roleVal && emp.role !== roleVal) return false;

      // Status filter
      if (statusVal === 'active' && !emp.account_active) return false;
      if (statusVal === 'inactive' && emp.account_active) return false;

      return true;
    });
  }

  function renderEmployees() {
    if (!employeeGrid) return;
    const filtered = getFilteredEmployees();

    if (filtered.length === 0) {
      employeeGrid.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1; padding: var(--space-8); text-align: center;">
          <svg class="icon icon-lg" style="stroke: var(--color-text-muted); width: 48px; height: 48px; margin-bottom: var(--space-3);" viewBox="0 0 24 24">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
            <circle cx="9" cy="7" r="4"></circle>
          </svg>
          <div style="font-weight: 600; color: var(--color-primary); font-size: var(--font-size-lg);">No employees found</div>
          <p class="text-muted" style="font-size: var(--font-size-sm); margin-top: var(--space-1);">Try adjusting your search criteria or invite a new employee.</p>
        </div>
      `;
      return;
    }

    employeeGrid.innerHTML = filtered.map(emp => {
      const initial = (emp.full_name || emp.username || '?')[:1].toUpperCase();
      const statusBadge = emp.account_active
        ? '<span class="badge badge-success" style="font-size: 11px;">Active</span>'
        : '<span class="badge badge-danger" style="font-size: 11px;">Deactivated</span>';

      const roleBadge = `<span class="badge badge-${emp.role}" style="font-size: 11px;">${emp.role.replace('_', ' ').toUpperCase()}</span>`;

      const deptChip = emp.department_name
        ? `<span class="chip-dept" style="background: var(--color-surface-raised); padding: 2px 8px; border-radius: var(--radius-sm); font-size: 12px; color: var(--color-text-muted);">${emp.department_name}</span>`
        : '';

      const teamsChips = (emp.teams || []).map(t =>
        `<span class="chip-team" style="background: rgba(36, 85, 72, 0.1); color: var(--color-primary); padding: 2px 8px; border-radius: var(--radius-sm); font-size: 11px; font-weight: 500;">${t.name}</span>`
      ).join(' ');

      return `
        <div class="card employee-card ${emp.account_active ? '' : 'account-deactivated'}" data-id="${emp.id}" style="display: flex; flex-direction: column; justify-content: space-between; position: relative;">
          <div>
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: var(--space-3);">
              <div style="display: flex; gap: var(--space-3); align-items: center;">
                <div class="user-avatar-badge" style="width: 44px; height: 44px; font-size: 18px; font-weight: 700;">
                  ${initial}
                </div>
                <div>
                  <div style="font-weight: 700; color: var(--color-primary); font-size: var(--font-size-base);">${emp.full_name || emp.username}</div>
                  <div class="text-muted" style="font-size: var(--font-size-xs);">${emp.email}</div>
                </div>
              </div>
              <div>${statusBadge}</div>
            </div>

            <div style="margin-bottom: var(--space-3);">
              <div style="font-size: var(--font-size-sm); font-weight: 600; color: var(--color-text-main); margin-bottom: var(--space-1);">
                ${emp.job_title || 'Employee'}
              </div>
              <div style="display: flex; gap: var(--space-2); flex-wrap: wrap; align-items: center;">
                ${roleBadge}
                ${deptChip}
              </div>
            </div>

            ${teamsChips ? `<div style="display: flex; gap: var(--space-1); flex-wrap: wrap; margin-bottom: var(--space-3);">${teamsChips}</div>` : ''}

            ${emp.reports_to_name ? `<div style="font-size: var(--font-size-xs); color: var(--color-text-muted); margin-bottom: var(--space-3);">Reports to: <strong>${emp.reports_to_name}</strong></div>` : ''}
          </div>

          <div style="border-top: 1px solid var(--color-border); padding-top: var(--space-3); display: flex; justify-content: flex-end; gap: var(--space-2);">
            <button class="btn btn-secondary btn-sm view-emp-btn" data-id="${emp.id}">View Profile</button>
          </div>
        </div>
      `;
    }).join('');

    // Attach card click handlers
    document.querySelectorAll('.view-emp-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const uid = e.target.getAttribute('data-id');
        openEmployeeDetail(uid);
      });
    });
  }

  // ── Debounced Search & Filter listeners ─────────────────────────────────────
  let searchTimeout = null;
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(renderEmployees, 200);
    });
  }

  [filterDept, filterTeam, filterRole, filterStatus].forEach(filterEl => {
    if (filterEl) filterEl.addEventListener('change', renderEmployees);
  });

  // ── Invite Employee Modal ──────────────────────────────────────────────────
  if (openInviteBtn && inviteModal) {
    openInviteBtn.addEventListener('click', () => {
      // Populate department dropdown
      const inviteDept = document.getElementById('invite-department');
      populateSelectOptions(inviteDept, allDepartments, 'No Department');

      // Populate reports_to manager dropdown
      const inviteMgr = document.getElementById('invite-reports-to');
      if (inviteMgr) {
        inviteMgr.innerHTML = '<option value="">No Manager Assigned</option>';
        allEmployees.filter(e => e.account_active).forEach(e => {
          const opt = document.createElement('option');
          opt.value = e.id;
          opt.textContent = `${e.full_name || e.username} (${e.role})`;
          inviteMgr.appendChild(opt);
        });
      }

      // Populate teams checkboxes
      const teamsContainer = document.getElementById('invite-teams-checkboxes');
      if (teamsContainer) {
        teamsContainer.innerHTML = allTeams.map(t => `
          <label style="display: flex; align-items: center; gap: var(--space-2); font-size: var(--font-size-sm); cursor: pointer;">
            <input type="checkbox" name="invite-teams" value="${t.id}">
            <span>${t.name}</span>
          </label>
        `).join('');
      }

      inviteForm.reset();
      inviteModal.style.display = 'flex';
    });
  }

  function closeInviteModal() {
    if (inviteModal) inviteModal.style.display = 'none';
  }

  if (closeInviteBtn) closeInviteBtn.addEventListener('click', closeInviteModal);
  if (cancelInviteBtn) cancelInviteBtn.addEventListener('click', closeInviteModal);

  if (inviteForm) {
    inviteForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const submitBtn = document.getElementById('submit-invite-btn');
      submitBtn.disabled = true;
      submitBtn.textContent = 'Creating...';

      try {
        const teamIds = Array.from(document.querySelectorAll('input[name="invite-teams"]:checked'))
          .map(cb => parseInt(cb.value, 10));

        const payload = {
          full_name: document.getElementById('invite-full-name').value.trim(),
          email: document.getElementById('invite-email').value.trim(),
          role: document.getElementById('invite-role').value,
          job_title: document.getElementById('invite-job-title').value.trim(),
          department_id: document.getElementById('invite-department').value ? parseInt(document.getElementById('invite-department').value, 10) : null,
          reports_to_id: document.getElementById('invite-reports-to').value ? parseInt(document.getElementById('invite-reports-to').value, 10) : null,
          team_ids: teamIds,
          password: document.getElementById('invite-password').value.trim() || undefined,
        };

        const res = await api('POST', '/api/employees', payload);
        closeInviteModal();

        // If activation credentials returned, show modal
        if (res.data && res.data.activation_token) {
          document.getElementById('success-email').textContent = res.data.email;
          document.getElementById('success-password').textContent = res.data.activation_token;
          if (successModal) successModal.style.display = 'flex';
        } else {
          showToast('Employee account created and activated successfully.', 'success');
        }

        await loadEmployees();
      } catch (err) {
        showToast(err.message || 'Failed to create employee.', 'error');
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Create & Activate Account';
      }
    });
  }

  if (closeSuccessBtn) closeSuccessBtn.addEventListener('click', () => { if (successModal) successModal.style.display = 'none'; });
  if (ackSuccessBtn) ackSuccessBtn.addEventListener('click', () => { if (successModal) successModal.style.display = 'none'; });

  // ── Employee Detail Modal ──────────────────────────────────────────────────
  async function openEmployeeDetail(userId) {
    try {
      const res = await api('GET', `/api/employees/${userId}`);
      const emp = res.data;
      currentViewingEmployee = emp;

      document.getElementById('edit-employee-id').value = emp.id;
      document.getElementById('detail-full-name').textContent = emp.full_name || emp.username;
      document.getElementById('detail-email').textContent = emp.email;

      const avatar = document.getElementById('detail-avatar');
      if (avatar) avatar.textContent = (emp.full_name || emp.username || '?')[:1].toUpperCase();

      const roleBadge = document.getElementById('detail-role-badge');
      if (roleBadge) {
        roleBadge.className = `badge badge-${emp.role}`;
        roleBadge.textContent = emp.role.replace('_', ' ').toUpperCase();
      }

      const statusBadge = document.getElementById('detail-status-badge');
      if (statusBadge) {
        statusBadge.className = emp.account_active ? 'badge badge-success' : 'badge badge-danger';
        statusBadge.textContent = emp.account_active ? 'Active' : 'Deactivated';
      }

      // Populate form fields
      document.getElementById('edit-job-title').value = emp.job_title || '';
      document.getElementById('edit-role').value = emp.role;

      // Populate department select
      const editDept = document.getElementById('edit-department');
      populateSelectOptions(editDept, allDepartments, 'No Department');
      editDept.value = emp.department_id || '';

      // Populate manager select
      const editMgr = document.getElementById('edit-reports-to');
      if (editMgr) {
        editMgr.innerHTML = '<option value="">No Manager Assigned</option>';
        allEmployees.filter(e => e.id !== emp.id && e.account_active).forEach(e => {
          const opt = document.createElement('option');
          opt.value = e.id;
          opt.textContent = `${e.full_name || e.username} (${e.role})`;
          editMgr.appendChild(opt);
        });
        editMgr.value = emp.reports_to_id || '';
      }

      // Populate team checkboxes
      const assignedTeamIds = new Set((emp.teams || []).map(t => t.id));
      const editTeamsContainer = document.getElementById('edit-teams-checkboxes');
      if (editTeamsContainer) {
        editTeamsContainer.innerHTML = allTeams.map(t => `
          <label style="display: flex; align-items: center; gap: var(--space-2); font-size: var(--font-size-sm); cursor: pointer;">
            <input type="checkbox" name="edit-teams" value="${t.id}" ${assignedTeamIds.has(t.id) ? 'checked' : ''}>
            <span>${t.name}</span>
          </label>
        `).join('');
      }

      // Populate task stats
      if (emp.task_stats) {
        document.getElementById('detail-tasks-total').textContent = emp.task_stats.total || 0;
        document.getElementById('detail-tasks-completed').textContent = emp.task_stats.completed || 0;
        document.getElementById('detail-tasks-pending').textContent = emp.task_stats.pending || 0;
      }

      // Toggle status button label
      if (toggleStatusBtn) {
        toggleStatusBtn.textContent = emp.account_active ? 'Deactivate Account' : 'Reactivate Account';
        toggleStatusBtn.className = emp.account_active ? 'btn btn-ghost text-danger btn-sm' : 'btn btn-secondary btn-sm';
      }

      if (detailModal) detailModal.style.display = 'flex';
    } catch (err) {
      showToast(err.message || 'Failed to load employee details.', 'error');
    }
  }

  function closeDetailModal() {
    if (detailModal) detailModal.style.display = 'none';
    currentViewingEmployee = null;
  }

  if (closeDetailBtn) closeDetailBtn.addEventListener('click', closeDetailModal);
  if (cancelDetailBtn) cancelDetailBtn.addEventListener('click', closeDetailModal);

  if (editForm) {
    editForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!currentViewingEmployee) return;

      try {
        const teamIds = Array.from(document.querySelectorAll('input[name="edit-teams"]:checked'))
          .map(cb => parseInt(cb.value, 10));

        const payload = {
          job_title: document.getElementById('edit-job-title').value.trim(),
          department_id: document.getElementById('edit-department').value ? parseInt(document.getElementById('edit-department').value, 10) : null,
          reports_to_id: document.getElementById('edit-reports-to').value ? parseInt(document.getElementById('edit-reports-to').value, 10) : null,
          role: document.getElementById('edit-role').value,
          team_ids: teamIds,
        };

        await api('PUT', `/api/employees/${currentViewingEmployee.id}`, payload);
        showToast('Employee profile updated successfully.', 'success');
        closeDetailModal();
        await loadEmployees();
      } catch (err) {
        showToast(err.message || 'Failed to update employee.', 'error');
      }
    });
  }

  // Account Status Toggle (Deactivate / Activate)
  if (toggleStatusBtn) {
    toggleStatusBtn.addEventListener('click', async () => {
      if (!currentViewingEmployee) return;
      const willDeactivate = currentViewingEmployee.account_active;
      const confirmMsg = willDeactivate
        ? `Are you sure you want to deactivate ${currentViewingEmployee.full_name || currentViewingEmployee.username}'s account? All historical tasks and records will be preserved, but they will not be able to log in.`
        : `Reactivate ${currentViewingEmployee.full_name || currentViewingEmployee.username}'s account?`;

      if (!confirm(confirmMsg)) return;

      try {
        const res = await api('PATCH', `/api/employees/${currentViewingEmployee.id}/status`, {
          account_active: !willDeactivate
        });
        showToast(res.message || 'Account status updated.', 'success');
        closeDetailModal();
        await loadEmployees();
      } catch (err) {
        showToast(err.message || 'Failed to change account status.', 'error');
      }
    });
  }

  // Start initialization
  loadInitialData();
});
