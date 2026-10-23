/**
 * TaskNest Leaves & Time-Off Management Module (HR & Operations).
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const openApplyBtn = document.getElementById('open-apply-modal-btn');
  const applyModal = document.getElementById('apply-leave-modal');
  const closeApplyBtns = document.querySelectorAll('.close-apply-modal-btn');
  const applyForm = document.getElementById('apply-leave-form');

  const startDateInput = document.getElementById('leave-start-date');
  const endDateInput = document.getElementById('leave-end-date');
  const calcDaysBadge = document.getElementById('calc-days-badge');

  const reviewModal = document.getElementById('review-leave-modal');
  const closeReviewBtns = document.querySelectorAll('.close-review-modal-btn');
  const reviewForm = document.getElementById('review-leave-form');

  const tabBtns = document.querySelectorAll('.leave-tab-btn');
  const tabPanes = document.querySelectorAll('.leave-tab-pane');

  // Set default dates in form (today to today)
  if (startDateInput && endDateInput) {
    const today = new Date().toISOString().split('T')[0];
    startDateInput.value = today;
    endDateInput.value = today;
    startDateInput.min = today;
    endDateInput.min = today;

    function updateCalculatedDays() {
      const s = new Date(startDateInput.value);
      const e = new Date(endDateInput.value);
      if (!isNaN(s) && !isNaN(e) && e >= s) {
        const diffTime = Math.abs(e - s);
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)) + 1;
        calcDaysBadge.textContent = `${diffDays} day(s)`;
        calcDaysBadge.className = 'badge badge-in_progress';
      } else {
        calcDaysBadge.textContent = 'Invalid date range';
        calcDaysBadge.className = 'badge badge-overdue';
      }
    }

    startDateInput.addEventListener('change', () => {
      if (endDateInput.value < startDateInput.value) {
        endDateInput.value = startDateInput.value;
      }
      endDateInput.min = startDateInput.value;
      updateCalculatedDays();
    });
    endDateInput.addEventListener('change', updateCalculatedDays);
  }

  // Modal Open / Close Handlers
  if (openApplyBtn && applyModal) {
    openApplyBtn.addEventListener('click', () => {
      applyModal.style.display = 'flex';
    });
  }

  closeApplyBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      if (applyModal) applyModal.style.display = 'none';
    });
  });

  closeReviewBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      if (reviewModal) reviewModal.style.display = 'none';
    });
  });

  // Tab switching
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetTab = btn.getAttribute('data-tab');
      tabBtns.forEach(b => {
        b.classList.remove('active');
        b.style.fontWeight = '600';
        b.style.color = '';
      });
      btn.classList.add('active');
      btn.style.fontWeight = '700';
      btn.style.color = 'var(--color-primary)';

      tabPanes.forEach(pane => {
        pane.style.display = (pane.id === `tab-${targetTab}`) ? 'block' : 'none';
      });

      if (targetTab === 'pending-reviews') {
        loadPendingReviews();
      } else if (targetTab === 'all-history') {
        loadAllHistory();
      } else if (targetTab === 'team-calendar') {
        loadLeaveCalendar();
      }
    });
  });

  // Load Balance Cards
  async function loadBalances() {
    try {
      const res = await api('GET', '/leaves/balance');
      if (res && res.ok && res.data) {
        const b = res.data;
        document.getElementById('bal-annual-avail').textContent = b.annual_available.toFixed(1);
        document.getElementById('bal-annual-used').textContent = b.annual_used.toFixed(1);
        document.getElementById('bal-annual-total').textContent = b.annual_total.toFixed(1);

        document.getElementById('bal-sick-avail').textContent = b.sick_available.toFixed(1);
        document.getElementById('bal-sick-used').textContent = b.sick_used.toFixed(1);
        document.getElementById('bal-sick-total').textContent = b.sick_total.toFixed(1);

        document.getElementById('bal-casual-avail').textContent = b.casual_available.toFixed(1);
        document.getElementById('bal-casual-used').textContent = b.casual_used.toFixed(1);
        document.getElementById('bal-casual-total').textContent = b.casual_total.toFixed(1);
      }
    } catch (err) {
      console.warn('Could not load leave balances:', err);
    }
  }

  // Load My Leave Requests
  async function loadMyRequests() {
    const container = document.getElementById('my-requests-list');
    if (!container) return;

    try {
      const res = await api('GET', '/leaves/my');
      if (!res || !res.ok) throw new Error(res.error || 'Failed to load requests');

      const requests = res.data || [];
      const pendingCount = requests.filter(r => r.status === 'pending').length;
      const countEl = document.getElementById('leaves-pending-count');
      if (countEl) countEl.textContent = pendingCount;

      if (requests.length === 0) {
        container.innerHTML = `
          <div style="text-align: center; padding: 2.5rem; color: var(--color-muted);">
            <svg class="icon icon-xl" viewBox="0 0 24 24" style="margin-bottom: 0.5rem; opacity: 0.5;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
            <p>You have not submitted any leave applications yet.</p>
          </div>
        `;
        return;
      }

      container.innerHTML = requests.map(req => {
        let badgeClass = 'badge-pending';
        if (req.status === 'approved') badgeClass = 'badge-completed';
        else if (req.status === 'rejected') badgeClass = 'badge-overdue';
        else if (req.status === 'cancelled') badgeClass = 'badge-category';

        const canCancel = req.status === 'pending';

        return `
          <div class="card" style="padding: 1rem 1.25rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; border-left: 4px solid ${
            req.status === 'approved' ? 'var(--color-primary)' :
            req.status === 'rejected' ? 'var(--color-danger)' :
            req.status === 'cancelled' ? 'var(--color-muted)' : 'var(--color-accent)'
          };">
            <div style="display: flex; flex-direction: column; gap: 0.25rem;">
              <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
                <strong style="font-size: var(--font-size-sm); text-transform: capitalize; color: var(--color-primary);">
                  ${req.leave_type.replace('_', ' ')} Leave
                </strong>
                <span class="badge ${badgeClass}">${req.status.toUpperCase()}</span>
                <span style="font-size: var(--font-size-xs); color: var(--color-muted); font-weight: 600;">
                  ${req.days_count} day(s)
                </span>
              </div>
              <div style="font-size: var(--font-size-xs); color: var(--color-text-light);">
                <strong>Dates:</strong> ${req.start_date} to ${req.end_date}
              </div>
              <p style="font-size: var(--font-size-xs); color: var(--color-text); margin: 0; line-height: 1.4;">
                <em>"${escapeHtml(req.reason)}"</em>
              </p>
              ${req.review_notes ? `
                <div style="font-size: var(--font-size-xs); color: var(--color-muted); background: var(--color-surface-subtle); padding: 0.25rem 0.5rem; border-radius: var(--radius-xs); border: 1px solid var(--color-border);">
                  <strong>Reviewer (${req.reviewer_name || 'Supervisor'}):</strong> ${escapeHtml(req.review_notes)}
                </div>
              ` : ''}
            </div>
            <div>
              ${canCancel ? `
                <button class="btn btn-secondary btn-sm cancel-leave-btn" data-id="${req.id}" style="color: var(--color-danger); border-color: var(--color-danger);">
                  Cancel Request
                </button>
              ` : ''}
            </div>
          </div>
        `;
      }).join('');

      // Wire cancel buttons
      container.querySelectorAll('.cancel-leave-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
          const leaveId = btn.getAttribute('data-id');
          if (!confirm('Are you sure you want to cancel this pending leave application?')) return;
          try {
            await api('PUT', `/leaves/${leaveId}/cancel`);
            showToast('Leave request cancelled successfully.', 'success');
            loadMyRequests();
            loadBalances();
          } catch (err) {
            showToast(err.message || 'Could not cancel leave request.', 'error');
          }
        });
      });

    } catch (err) {
      container.innerHTML = `<p style="color: var(--color-danger); text-align: center; padding: 1rem;">Failed to load leave requests: ${err.message}</p>`;
    }
  }

  // Load Pending Reviews (Management)
  async function loadPendingReviews() {
    const container = document.getElementById('pending-reviews-list');
    if (!container) return;

    try {
      const res = await api('GET', '/leaves/pending');
      if (!res || !res.ok) throw new Error(res.error || 'Failed to load pending reviews');

      const requests = res.data || [];
      const badgeEl = document.getElementById('tab-pending-badge');
      if (badgeEl) {
        if (requests.length > 0) {
          badgeEl.textContent = requests.length;
          badgeEl.style.display = 'inline-block';
        } else {
          badgeEl.style.display = 'none';
        }
      }

      if (requests.length === 0) {
        container.innerHTML = `
          <div style="text-align: center; padding: 2.5rem; color: var(--color-muted);">
            <svg class="icon icon-xl" viewBox="0 0 24 24" style="margin-bottom: 0.5rem; color: var(--color-primary);"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
            <p>No pending leave applications awaiting review.</p>
          </div>
        `;
        return;
      }

      container.innerHTML = requests.map(req => `
        <div class="card" style="padding: 1.25rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; border-left: 4px solid var(--color-accent);">
          <div style="display: flex; flex-direction: column; gap: 0.35rem;">
            <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
              <strong style="font-size: var(--font-size-sm); color: var(--color-primary);">
                ${escapeHtml(req.user_name || 'Employee')}
              </strong>
              <span class="badge badge-employee">${escapeHtml(req.designation || 'Member')}</span>
              <span class="badge badge-pending" style="text-transform: capitalize;">${req.leave_type} Leave</span>
              <span style="font-size: var(--font-size-xs); font-weight: 700; color: var(--color-text);">
                ${req.days_count} day(s)
              </span>
            </div>
            <div style="font-size: var(--font-size-xs); color: var(--color-text-light);">
              <strong>Schedule:</strong> ${req.start_date} to ${req.end_date}
              ${req.department_name ? ` · <em>Dept: ${escapeHtml(req.department_name)}</em>` : ''}
              ${req.team_name ? ` · <em>Team: ${escapeHtml(req.team_name)}</em>` : ''}
            </div>
            <p style="font-size: var(--font-size-xs); color: var(--color-text); margin: 0; line-height: 1.4;">
              <strong>Reason:</strong> ${escapeHtml(req.reason)}
            </p>
          </div>
          <div style="display: flex; gap: 0.5rem;">
            <button class="btn btn-primary btn-sm review-decision-btn" data-id="${req.id}" data-action="approved" data-user="${escapeHtml(req.user_name || 'Employee')}" data-type="${req.leave_type}" data-days="${req.days_count}">
              Approve
            </button>
            <button class="btn btn-secondary btn-sm review-decision-btn" data-id="${req.id}" data-action="rejected" data-user="${escapeHtml(req.user_name || 'Employee')}" data-type="${req.leave_type}" data-days="${req.days_count}" style="color: var(--color-danger); border-color: var(--color-danger);">
              Reject
            </button>
          </div>
        </div>
      `).join('');

      // Wire decision buttons
      container.querySelectorAll('.review-decision-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          const leaveId = btn.getAttribute('data-id');
          const action = btn.getAttribute('data-action');
          const applicant = btn.getAttribute('data-user');
          const leaveType = btn.getAttribute('data-type');
          const days = btn.getAttribute('data-days');

          document.getElementById('review-leave-id').value = leaveId;
          document.getElementById('review-decision-action').value = action;
          document.getElementById('review-modal-title').textContent = `${action === 'approved' ? 'Approve' : 'Reject'} Leave Request`;
          document.getElementById('review-applicant-summary').innerHTML = `
            <strong>Applicant:</strong> ${applicant}<br>
            <strong>Request:</strong> ${days} day(s) of ${leaveType} leave.<br>
            <strong>Action:</strong> <span style="font-weight: 700; color: ${action === 'approved' ? 'var(--color-primary)' : 'var(--color-danger)'};">${action.toUpperCase()}</span>
          `;
          document.getElementById('confirm-review-btn').textContent = action === 'approved' ? 'Confirm Approval' : 'Confirm Rejection';
          document.getElementById('confirm-review-btn').className = action === 'approved' ? 'btn btn-primary btn-sm' : 'btn btn-secondary btn-sm';
          if (action === 'rejected') {
            document.getElementById('confirm-review-btn').style.borderColor = 'var(--color-danger)';
            document.getElementById('confirm-review-btn').style.color = 'var(--color-danger)';
          } else {
            document.getElementById('confirm-review-btn').style.borderColor = '';
            document.getElementById('confirm-review-btn').style.color = '';
          }

          document.getElementById('review-notes-input').value = '';
          reviewModal.style.display = 'flex';
        });
      });

    } catch (err) {
      container.innerHTML = `<p style="color: var(--color-danger); text-align: center; padding: 1rem;">Failed to load pending reviews: ${err.message}</p>`;
    }
  }

  // Handle Review Decision Submit
  if (reviewForm) {
    reviewForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const leaveId = document.getElementById('review-leave-id').value;
      const decision = document.getElementById('review-decision-action').value;
      const review_notes = document.getElementById('review-notes-input').value;

      try {
        await api('PUT', `/leaves/${leaveId}/review`, { decision, review_notes });
        showToast(`Leave application ${decision} successfully.`, 'success');
        reviewModal.style.display = 'none';
        loadPendingReviews();
        loadBalances();
        loadMyRequests();
      } catch (err) {
        showToast(err.message || 'Error processing review decision.', 'error');
      }
    });
  }

  // Load All History (Management)
  async function loadAllHistory() {
    const container = document.getElementById('all-history-list');
    if (!container) return;

    const statusFilter = document.getElementById('filter-all-status')?.value || '';
    const typeFilter = document.getElementById('filter-all-type')?.value || '';

    try {
      let url = '/leaves/all?';
      if (statusFilter) url += `status=${encodeURIComponent(statusFilter)}&`;
      if (typeFilter) url += `leave_type=${encodeURIComponent(typeFilter)}&`;

      const res = await api('GET', url);
      if (!res || !res.ok) throw new Error(res.error || 'Failed to load leave history');

      const requests = res.data || [];
      if (requests.length === 0) {
        container.innerHTML = '<p class="text-muted" style="text-align: center; padding: 2rem;">No matching leave records found.</p>';
        return;
      }

      container.innerHTML = requests.map(req => {
        let badgeClass = 'badge-pending';
        if (req.status === 'approved') badgeClass = 'badge-completed';
        else if (req.status === 'rejected') badgeClass = 'badge-overdue';
        else if (req.status === 'cancelled') badgeClass = 'badge-category';

        return `
          <div class="card" style="padding: 1rem; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
            <div>
              <div style="display: flex; gap: 0.5rem; align-items: center; margin-bottom: 0.25rem;">
                <strong>${escapeHtml(req.user_name || 'Employee')}</strong>
                <span class="badge ${badgeClass}">${req.status.toUpperCase()}</span>
                <span style="font-size: var(--font-size-xs); color: var(--color-muted);">${req.leave_type} · ${req.days_count}d</span>
              </div>
              <div style="font-size: var(--font-size-xs); color: var(--color-text-light);">
                ${req.start_date} to ${req.end_date} · <em>"${escapeHtml(req.reason)}"</em>
              </div>
            </div>
            ${req.reviewer_name ? `
              <div style="font-size: var(--font-size-xs); color: var(--color-muted); text-align: right;">
                Reviewed by <strong>${escapeHtml(req.reviewer_name)}</strong>
              </div>
            ` : ''}
          </div>
        `;
      }).join('');
    } catch (err) {
      container.innerHTML = `<p style="color: var(--color-danger); text-align: center; padding: 1rem;">Failed to load history: ${err.message}</p>`;
    }
  }

  // Filter change listeners
  document.getElementById('filter-all-status')?.addEventListener('change', loadAllHistory);
  document.getElementById('filter-all-type')?.addEventListener('change', loadAllHistory);

  // Load Leave Calendar (Who's Away)
  async function loadLeaveCalendar() {
    const container = document.getElementById('calendar-leaves-list');
    if (!container) return;

    try {
      const res = await api('GET', '/leaves/calendar');
      if (!res || !res.ok) throw new Error(res.error || 'Failed to load leave calendar');

      const leaves = res.data || [];
      if (leaves.length === 0) {
        container.innerHTML = `
          <div style="text-align: center; padding: 2.5rem; color: var(--color-muted);">
            <svg class="icon icon-xl" viewBox="0 0 24 24" style="margin-bottom: 0.5rem; color: var(--color-primary);"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
            <p>No upcoming approved absences scheduled.</p>
          </div>
        `;
        return;
      }

      container.innerHTML = leaves.map(l => `
        <div class="card" style="padding: 1rem 1.25rem; display: flex; justify-content: space-between; align-items: center; border-left: 4px solid var(--color-primary);">
          <div>
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem;">
              <strong style="color: var(--color-primary);">${escapeHtml(l.user_name || 'Team Member')}</strong>
              <span class="badge badge-completed">On Leave</span>
              <span style="font-size: var(--font-size-xs); text-transform: capitalize; color: var(--color-muted);">${l.leave_type} (${l.days_count}d)</span>
            </div>
            <div style="font-size: var(--font-size-xs); color: var(--color-text-light);">
              ${l.start_date} &rarr; ${l.end_date}
              ${l.team_name ? ` · <em>Team: ${escapeHtml(l.team_name)}</em>` : ''}
            </div>
          </div>
          <div style="font-size: var(--font-size-xs); color: var(--color-muted);">
            Approved
          </div>
        </div>
      `).join('');
    } catch (err) {
      container.innerHTML = `<p style="color: var(--color-danger); text-align: center; padding: 1rem;">Failed to load calendar: ${err.message}</p>`;
    }
  }

  // Handle Apply Form Submit
  if (applyForm) {
    applyForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const submitBtn = document.getElementById('submit-leave-btn');
      submitBtn.disabled = true;
      submitBtn.textContent = 'Submitting...';

      const leave_type = document.getElementById('leave-type-select').value;
      const start_date = document.getElementById('leave-start-date').value;
      const end_date = document.getElementById('leave-end-date').value;
      const reason = document.getElementById('leave-reason').value;

      try {
        const res = await api('POST', '/leaves', {
          leave_type,
          start_date,
          end_date,
          reason
        });

        showToast(res.message || 'Leave application submitted successfully!', 'success');
        applyModal.style.display = 'none';
        applyForm.reset();
        loadBalances();
        loadMyRequests();
      } catch (err) {
        showToast(err.message || 'Could not submit leave application.', 'error');
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Submit Application';
      }
    });
  }

  function escapeHtml(text) {
    if (!text) return '';
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // Initial loads
  loadBalances();
  loadMyRequests();
});
