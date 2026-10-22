/**
 * static/js/teams.js
 * TaskNest Teams and Departments Client
 */

document.addEventListener('DOMContentLoaded', () => {
  let allDepartments = [];
  let allTeams = [];
  let allEmployees = [];
  let currentViewingTeam = null;

  // DOM Elements
  const deptsContainer = document.getElementById('departments-container');
  const deptsSummaryCount = document.getElementById('departments-summary-count');
  const teamsContainer = document.getElementById('teams-list-container');
  const teamSearchInput = document.getElementById('team-search');
  const filterTeamDept = document.getElementById('filter-team-dept');

  // Modals
  const createDeptModal = document.getElementById('create-dept-modal');
  const openCreateDeptBtn = document.getElementById('open-create-dept-btn');
  const closeDeptModalBtn = document.getElementById('close-dept-modal-btn');
  const cancelDeptBtn = document.getElementById('cancel-dept-btn');
  const createDeptForm = document.getElementById('create-dept-form');

  const createTeamModal = document.getElementById('create-team-modal');
  const openCreateTeamBtn = document.getElementById('open-create-team-btn');
  const closeTeamModalBtn = document.getElementById('close-team-modal-btn');
  const cancelTeamBtn = document.getElementById('cancel-team-btn');
  const createTeamForm = document.getElementById('create-team-form');

  const teamDetailModal = document.getElementById('team-detail-modal');
  const closeTeamDetailBtn = document.getElementById('close-team-detail-btn');
  const doneTeamDetailBtn = document.getElementById('done-team-detail-btn');
  const deleteTeamBtn = document.getElementById('delete-team-btn');

  // Tabs
  const tabMembersBtn = document.getElementById('tab-members-btn');
  const tabTasksBtn = document.getElementById('tab-tasks-btn');
  const tabMembersContent = document.getElementById('tab-members-content');
  const tabTasksContent = document.getElementById('tab-tasks-content');

  // Forms in detail modal
  const addMemberForm = document.getElementById('add-member-form');
  const addTeamTaskForm = document.getElementById('add-team-task-form');

  // ── Initial Load ───────────────────────────────────────────────────────────
  async function loadData() {
    try {
      const [deptRes, teamRes, empRes] = await Promise.all([
        api('GET', '/api/departments'),
        api('GET', '/api/teams'),
        api('GET', '/api/employees')
      ]);

      allDepartments = deptRes.data || [];
      allTeams = teamRes.data || [];
      allEmployees = empRes.data || [];

      renderDepartments();
      populateDeptFilter();
      renderTeams();
    } catch (err) {
      showToast(err.message || 'Failed to load team data.', 'error');
    }
  }

  // ── Render Departments ─────────────────────────────────────────────────────
  function renderDepartments() {
    if (!deptsContainer) return;
    if (deptsSummaryCount) {
      deptsSummaryCount.textContent = `${allDepartments.length} department${allDepartments.length === 1 ? '' : 's'}`;
    }

    if (allDepartments.length === 0) {
      deptsContainer.innerHTML = `
        <div class="text-muted" style="padding: var(--space-4); font-size: var(--font-size-sm);">
          No departments created yet.
        </div>
      `;
      return;
    }

    deptsContainer.innerHTML = allDepartments.map(dept => `
      <div class="card dept-card" style="min-width: 220px; flex: 1; padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-surface-raised);">
        <div style="font-weight: 700; color: var(--color-primary); font-size: var(--font-size-base); margin-bottom: var(--space-1);">${dept.name}</div>
        <div class="text-muted" style="font-size: var(--font-size-xs); margin-bottom: var(--space-2); min-height: 32px;">${dept.description || 'No description provided.'}</div>
        <div style="display: flex; justify-content: space-between; font-size: var(--font-size-xs); color: var(--color-text-muted);">
          <span>${dept.teams_count || 0} teams</span>
          <span>${dept.members_count || 0} members</span>
        </div>
        ${dept.head_name ? `<div style="font-size: 11px; margin-top: var(--space-2); color: var(--color-primary);">Head: <strong>${dept.head_name}</strong></div>` : ''}
      </div>
    `).join('');
  }

  function populateDeptFilter() {
    if (!filterTeamDept) return;
    const currentVal = filterTeamDept.value;
    filterTeamDept.innerHTML = '<option value="">All Departments</option>';
    allDepartments.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.id;
      opt.textContent = d.name;
      filterTeamDept.appendChild(opt);
    });
    filterTeamDept.value = currentVal;
  }

  // ── Render Teams ───────────────────────────────────────────────────────────
  function getFilteredTeams() {
    const q = (teamSearchInput ? teamSearchInput.value : '').toLowerCase().trim();
    const deptId = filterTeamDept ? filterTeamDept.value : '';

    return allTeams.filter(t => {
      if (q && !t.name.toLowerCase().includes(q)) return false;
      if (deptId && String(t.department_id) !== String(deptId)) return false;
      return true;
    });
  }

  function renderTeams() {
    if (!teamsContainer) return;
    const filtered = getFilteredTeams();

    if (filtered.length === 0) {
      teamsContainer.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1; padding: var(--space-8); text-align: center;">
          <svg class="icon icon-lg" style="stroke: var(--color-text-muted); width: 48px; height: 48px; margin-bottom: var(--space-3);" viewBox="0 0 24 24">
            <rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect>
            <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path>
          </svg>
          <div style="font-weight: 600; color: var(--color-primary); font-size: var(--font-size-lg);">No teams found</div>
          <p class="text-muted" style="font-size: var(--font-size-sm); margin-top: var(--space-1);">Create a new team or adjust your search filter.</p>
        </div>
      `;
      return;
    }

    teamsContainer.innerHTML = filtered.map(t => {
      const deptBadge = t.department_name
        ? `<span class="badge" style="background: rgba(36, 85, 72, 0.1); color: var(--color-primary);">${t.department_name}</span>`
        : '';

      const leadBadge = t.lead_name
        ? `<div style="font-size: var(--font-size-xs); color: var(--color-text-muted); margin-bottom: var(--space-2);">Lead: <strong style="color: var(--color-primary);">${t.lead_name}</strong></div>`
        : '';

      return `
        <div class="card team-card" style="display: flex; flex-direction: column; justify-content: space-between;">
          <div>
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: var(--space-2);">
              <h3 style="margin: 0; font-size: var(--font-size-base); font-weight: 700; color: var(--color-primary);">${t.name}</h3>
              ${deptBadge}
            </div>

            <p class="text-muted" style="font-size: var(--font-size-sm); margin-bottom: var(--space-3); min-height: 38px;">
              ${t.description || 'No description provided.'}
            </p>

            ${leadBadge}

            <div style="display: flex; gap: var(--space-4); font-size: var(--font-size-sm); color: var(--color-text-main); margin-bottom: var(--space-3);">
              <div><strong style="color: var(--color-primary);">${t.members_count || 0}</strong> Members</div>
              <div><strong style="color: var(--color-primary);">${t.tasks_count || 0}</strong> Tasks</div>
            </div>
          </div>

          <div style="border-top: 1px solid var(--color-border); padding-top: var(--space-3); display: flex; justify-content: flex-end;">
            <button class="btn btn-secondary btn-sm open-team-detail-btn" data-id="${t.id}">View Workspace</button>
          </div>
        </div>
      `;
    }).join('');

    // Attach workspace buttons
    document.querySelectorAll('.open-team-detail-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const tid = e.target.getAttribute('data-id');
        openTeamDetail(tid);
      });
    });
  }

  // Filter listeners
  if (teamSearchInput) {
    teamSearchInput.addEventListener('input', renderTeams);
  }
  if (filterTeamDept) {
    filterTeamDept.addEventListener('change', renderTeams);
  }

  // ── Create Department Modal ────────────────────────────────────────────────
  if (openCreateDeptBtn && createDeptModal) {
    openCreateDeptBtn.addEventListener('click', () => {
      const headSelect = document.getElementById('dept-head');
      if (headSelect) {
        headSelect.innerHTML = '<option value="">Select Department Head (Optional)</option>';
        allEmployees.filter(e => e.account_active).forEach(e => {
          const opt = document.createElement('option');
          opt.value = e.id;
          opt.textContent = `${e.full_name || e.username} (${e.role})`;
          headSelect.appendChild(opt);
        });
      }
      createDeptForm.reset();
      createDeptModal.style.display = 'flex';
    });
  }

  function closeDeptModal() {
    if (createDeptModal) createDeptModal.style.display = 'none';
  }

  if (closeDeptModalBtn) closeDeptModalBtn.addEventListener('click', closeDeptModal);
  if (cancelDeptBtn) cancelDeptBtn.addEventListener('click', closeDeptModal);

  if (createDeptForm) {
    createDeptForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        const payload = {
          name: document.getElementById('dept-name').value.trim(),
          description: document.getElementById('dept-desc').value.trim(),
          head_id: document.getElementById('dept-head').value ? parseInt(document.getElementById('dept-head').value, 10) : null
        };
        await api('POST', '/api/departments', payload);
        showToast('Department created successfully.', 'success');
        closeDeptModal();
        await loadData();
      } catch (err) {
        showToast(err.message || 'Failed to create department.', 'error');
      }
    });
  }

  // ── Create Team Modal ──────────────────────────────────────────────────────
  if (openCreateTeamBtn && createTeamModal) {
    openCreateTeamBtn.addEventListener('click', () => {
      const teamDept = document.getElementById('team-department');
      if (teamDept) {
        teamDept.innerHTML = '<option value="">No Department</option>';
        allDepartments.forEach(d => {
          const opt = document.createElement('option');
          opt.value = d.id;
          opt.textContent = d.name;
          teamDept.appendChild(opt);
        });
      }

      const teamLeadSelect = document.getElementById('team-lead');
      if (teamLeadSelect) {
        teamLeadSelect.innerHTML = '<option value="">Select Team Lead (Optional)</option>';
        allEmployees.filter(e => e.account_active).forEach(e => {
          const opt = document.createElement('option');
          opt.value = e.id;
          opt.textContent = `${e.full_name || e.username} (${e.role})`;
          teamLeadSelect.appendChild(opt);
        });
      }

      createTeamForm.reset();
      createTeamModal.style.display = 'flex';
    });
  }

  function closeTeamModal() {
    if (createTeamModal) createTeamModal.style.display = 'none';
  }

  if (closeTeamModalBtn) closeTeamModalBtn.addEventListener('click', closeTeamModal);
  if (cancelTeamBtn) cancelTeamBtn.addEventListener('click', closeTeamModal);

  if (createTeamForm) {
    createTeamForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        const payload = {
          name: document.getElementById('team-name').value.trim(),
          description: document.getElementById('team-desc').value.trim(),
          department_id: document.getElementById('team-department').value ? parseInt(document.getElementById('team-department').value, 10) : null,
          lead_id: document.getElementById('team-lead').value ? parseInt(document.getElementById('team-lead').value, 10) : null
        };
        await api('POST', '/api/teams', payload);
        showToast('Team created successfully.', 'success');
        closeTeamModal();
        await loadData();
      } catch (err) {
        showToast(err.message || 'Failed to create team.', 'error');
      }
    });
  }

  // ── Team Detail Modal & Workspace ──────────────────────────────────────────
  async function openTeamDetail(teamId) {
    try {
      const res = await api('GET', `/api/teams/${teamId}`);
      currentViewingTeam = res.data;

      document.getElementById('team-detail-name').textContent = currentViewingTeam.name;
      document.getElementById('team-detail-dept').textContent = currentViewingTeam.department_name
        ? `Department: ${currentViewingTeam.department_name}`
        : 'Cross-functional / General Team';

      // Switch to members tab by default
      switchTab('members');

      // Populate members roster
      renderTeamMembers(currentViewingTeam.members || []);

      // Populate available employees in add member dropdown
      populateAddMemberSelect(currentViewingTeam.members || []);

      // Load and render team tasks
      await loadTeamTasks(currentViewingTeam.id);

      // Show delete button for authorized managers
      if (deleteTeamBtn) {
        deleteTeamBtn.style.display = 'block';
      }

      if (teamDetailModal) teamDetailModal.style.display = 'flex';
    } catch (err) {
      showToast(err.message || 'Failed to load team workspace.', 'error');
    }
  }

  function switchTab(tabName) {
    if (tabName === 'members') {
      tabMembersBtn.classList.add('active');
      tabTasksBtn.classList.remove('active');
      tabMembersContent.style.display = 'block';
      tabTasksContent.style.display = 'none';
    } else {
      tabMembersBtn.classList.remove('active');
      tabTasksBtn.classList.add('active');
      tabMembersContent.style.display = 'none';
      tabTasksContent.style.display = 'block';
    }
  }

  if (tabMembersBtn) tabMembersBtn.addEventListener('click', () => switchTab('members'));
  if (tabTasksBtn) tabTasksBtn.addEventListener('click', () => switchTab('tasks'));

  function renderTeamMembers(members) {
    const listEl = document.getElementById('team-members-list-container');
    const countEl = document.getElementById('team-members-count');
    if (countEl) countEl.textContent = members.length;

    if (!listEl) return;
    if (members.length === 0) {
      listEl.innerHTML = '<div class="text-muted" style="padding: var(--space-3); font-size: var(--font-size-sm);">No members assigned yet.</div>';
      return;
    }

    listEl.innerHTML = members.map(m => {
      const isLead = m.team_role === 'lead';
      const roleBadge = isLead
        ? '<span class="badge badge-warning" style="font-size: 11px;">Team Lead</span>'
        : '<span class="badge" style="background: var(--color-surface-raised); font-size: 11px;">Member</span>';

      return `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: var(--space-2) 0; border-bottom: 1px solid var(--color-border);">
          <div style="display: flex; gap: var(--space-3); align-items: center;">
            <div class="user-avatar-badge" style="width: 32px; height: 32px; font-size: 13px;">
              ${(m.full_name || m.username || '?')[:1].toUpperCase()}
            </div>
            <div>
              <div style="font-weight: 600; font-size: var(--font-size-sm);">${m.full_name || m.username}</div>
              <div class="text-muted" style="font-size: var(--font-size-xs);">${m.email} ${m.job_title ? `• ${m.job_title}` : ''}</div>
            </div>
          </div>
          <div style="display: flex; gap: var(--space-2); align-items: center;">
            ${roleBadge}
            <button class="btn btn-ghost text-danger btn-sm remove-member-btn" data-uid="${m.id}" title="Remove member">&times;</button>
          </div>
        </div>
      `;
    }).join('');

    // Attach remove member listeners
    document.querySelectorAll('.remove-member-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        const uid = e.target.getAttribute('data-uid');
        if (!confirm('Remove member from team?')) return;
        try {
          await api('DELETE', `/api/teams/${currentViewingTeam.id}/members/${uid}`);
          showToast('Member removed from team.', 'success');
          // Reload team workspace
          await openTeamDetail(currentViewingTeam.id);
          await loadData();
        } catch (err) {
          showToast(err.message || 'Failed to remove member.', 'error');
        }
      });
    });
  }

  function populateAddMemberSelect(currentMembers) {
    const selectEl = document.getElementById('add-member-select');
    const taskAssigneeEl = document.getElementById('team-task-assignee');
    if (!selectEl) return;

    const existingIds = new Set(currentMembers.map(m => m.id));
    selectEl.innerHTML = '<option value="">Select employee to add to team...</option>';

    if (taskAssigneeEl) {
      taskAssigneeEl.innerHTML = '<option value="">Unassigned</option>';
      currentMembers.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = m.full_name || m.username;
        taskAssigneeEl.appendChild(opt);
      });
    }

    allEmployees.filter(e => !existingIds.has(e.id) && e.account_active).forEach(e => {
      const opt = document.createElement('option');
      opt.value = e.id;
      opt.textContent = `${e.full_name || e.username} (${e.email})`;
      selectEl.appendChild(opt);
    });
  }

  // Add Member submit
  if (addMemberForm) {
    addMemberForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const selectEl = document.getElementById('add-member-select');
      const uid = selectEl.value;
      if (!uid) {
        showToast('Please select an employee to add.', 'warning');
        return;
      }

      try {
        await api('POST', `/api/teams/${currentViewingTeam.id}/members`, {
          user_id: parseInt(uid, 10),
          role: 'member'
        });
        showToast('Member added to team.', 'success');
        await openTeamDetail(currentViewingTeam.id);
        await loadData();
      } catch (err) {
        showToast(err.message || 'Failed to add member.', 'error');
      }
    });
  }

  // ── Team Tasks ─────────────────────────────────────────────────────────────
  async function loadTeamTasks(teamId) {
    try {
      const res = await api('GET', `/api/teams/${teamId}/tasks`);
      const tasks = res.data || [];
      renderTeamTasks(tasks);
    } catch (err) {
      showToast('Failed to load team tasks.', 'error');
    }
  }

  function renderTeamTasks(tasks) {
    const listEl = document.getElementById('team-tasks-list-container');
    const countEl = document.getElementById('team-tasks-count');
    if (countEl) countEl.textContent = tasks.length;

    if (!listEl) return;
    if (tasks.length === 0) {
      listEl.innerHTML = '<div class="text-muted" style="padding: var(--space-3); font-size: var(--font-size-sm);">No tasks assigned to this team yet.</div>';
      return;
    }

    listEl.innerHTML = tasks.map(t => {
      const priorityClass = t.priority === 'high' ? 'badge-high' : t.priority === 'medium' ? 'badge-medium' : 'badge-low';
      const statusClass = t.status === 'completed' ? 'badge-success' : 'badge-pending';
      const assigneeName = t.assigned_to_name ? `Assigned: ${t.assigned_to_name}` : 'Unassigned';

      return `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: var(--space-2) 0; border-bottom: 1px solid var(--color-border);">
          <div>
            <div style="font-weight: 600; font-size: var(--font-size-sm); color: var(--color-text-main);">${t.title}</div>
            <div class="text-muted" style="font-size: var(--font-size-xs);">
              <span>${assigneeName}</span>
              ${t.due_date ? ` • Due ${t.due_date}` : ''}
            </div>
          </div>
          <div style="display: flex; gap: var(--space-2); align-items: center;">
            <span class="badge ${priorityClass}" style="font-size: 11px;">${t.priority}</span>
            <span class="badge ${statusClass}" style="font-size: 11px;">${t.status}</span>
          </div>
        </div>
      `;
    }).join('');
  }

  // Add Team Task submit
  if (addTeamTaskForm) {
    addTeamTaskForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        const payload = {
          title: document.getElementById('team-task-title').value.trim(),
          assigned_to_id: document.getElementById('team-task-assignee').value ? parseInt(document.getElementById('team-task-assignee').value, 10) : null,
          priority: document.getElementById('team-task-priority').value,
          due_date: document.getElementById('team-task-due').value || null,
        };

        await api('POST', `/api/teams/${currentViewingTeam.id}/tasks`, payload);
        showToast('Task assigned to team.', 'success');
        addTeamTaskForm.reset();
        await loadTeamTasks(currentViewingTeam.id);
        await loadData();
      } catch (err) {
        showToast(err.message || 'Failed to add team task.', 'error');
      }
    });
  }

  // Delete Team
  if (deleteTeamBtn) {
    deleteTeamBtn.addEventListener('click', async () => {
      if (!currentViewingTeam) return;
      if (!confirm(`Are you sure you want to delete the team "${currentViewingTeam.name}"? Tasks assigned to this team will be safely preserved.`)) return;

      try {
        await api('DELETE', `/api/teams/${currentViewingTeam.id}`);
        showToast('Team deleted successfully.', 'success');
        closeTeamDetailModal();
        await loadData();
      } catch (err) {
        showToast(err.message || 'Failed to delete team.', 'error');
      }
    });
  }

  function closeTeamDetailModal() {
    if (teamDetailModal) teamDetailModal.style.display = 'none';
    currentViewingTeam = null;
  }

  if (closeTeamDetailBtn) closeTeamDetailBtn.addEventListener('click', closeTeamDetailModal);
  if (doneTeamDetailBtn) doneTeamDetailBtn.addEventListener('click', closeTeamDetailModal);

  // Start initialization
  loadData();
});
