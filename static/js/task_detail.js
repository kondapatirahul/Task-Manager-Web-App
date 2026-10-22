/**
 * TaskNest Task Detail, Collaboration & File Engine
 */

const TaskDetail = {
  taskId: null,
  task: null,
  currentUser: null,
  comments: [],
  submissions: [],
  composerFiles: [],
  submitFiles: [],
  refFiles: [],

  async init() {
    const pageEl = document.querySelector('.task-detail-page');
    if (!pageEl) return;

    this.taskId = pageEl.getAttribute('data-task-id');
    if (!this.taskId) return;

    this.bindEvents();

    try {
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
        await Promise.all([
          this.loadComments(),
          this.loadSubmissions(),
        ]);
      } else {
        this.showError(taskRes?.error || 'Task not found or access denied.');
      }
    } catch (err) {
      console.error('Failed to load task detail:', err);
      this.showError('Unable to load task details. Please check your connection.');
    }
  },

  bindEvents() {
    // Submit review modal controls
    document.querySelectorAll('.close-submit-modal').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.getElementById('submit-review-modal')?.classList.remove('active');
        this.clearSubmitStagedFiles();
      });
    });

    // Deliverables dropzone / file picker in submit modal
    const submitDropArea = document.getElementById('submit-drop-area');
    const submitFileInput = document.getElementById('submit-files-input');
    if (submitDropArea && submitFileInput) {
      submitDropArea.addEventListener('click', () => submitFileInput.click());
      submitFileInput.addEventListener('change', (e) => {
        this.handleStagedFiles(Array.from(e.target.files), 'submit');
        submitFileInput.value = '';
      });
    }

    // Submit work form
    const submitForm = document.getElementById('submit-review-form');
    if (submitForm) {
      submitForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await this.handleWorkSubmission();
      });
    }

    // Review action modal controls
    document.querySelectorAll('.close-review-modal').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.getElementById('review-action-modal')?.classList.remove('active');
      });
    });

    const reviewForm = document.getElementById('review-action-form');
    if (reviewForm) {
      reviewForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await this.handleReviewDecision();
      });
    }

    // Upload reference modal controls
    document.getElementById('btn-open-upload-ref-modal')?.addEventListener('click', () => {
      this.clearRefStagedFiles();
      document.getElementById('upload-reference-modal')?.classList.add('active');
    });

    document.querySelectorAll('.close-upload-ref-modal').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.getElementById('upload-reference-modal')?.classList.remove('active');
        this.clearRefStagedFiles();
      });
    });

    const refDropArea = document.getElementById('ref-drop-area');
    const refFileInput = document.getElementById('ref-files-input');
    if (refDropArea && refFileInput) {
      refDropArea.addEventListener('click', () => refFileInput.click());
      refFileInput.addEventListener('change', (e) => {
        this.handleStagedFiles(Array.from(e.target.files), 'reference');
        refFileInput.value = '';
      });
    }

    const refUploadForm = document.getElementById('upload-reference-form');
    if (refUploadForm) {
      refUploadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await this.handleReferenceUpload();
      });
    }

    // Discussion composer file attachment
    const commentFilesInput = document.getElementById('comment-files-input');
    document.getElementById('btn-trigger-comment-files')?.addEventListener('click', () => {
      commentFilesInput?.click();
    });

    commentFilesInput?.addEventListener('change', (e) => {
      this.handleStagedFiles(Array.from(e.target.files), 'composer');
      commentFilesInput.value = '';
    });

    // Discussion comment form submit
    const commentForm = document.getElementById('comment-composer-form');
    if (commentForm) {
      commentForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        await this.handlePostComment();
      });
    }

    // File preview modal close
    document.querySelectorAll('.close-preview-modal').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.getElementById('file-preview-modal')?.classList.remove('active');
        const container = document.getElementById('file-preview-content');
        if (container) container.innerHTML = '';
      });
    });

    // Close preview modal on ESC or backdrop click
    document.getElementById('file-preview-modal')?.addEventListener('click', (e) => {
      if (e.target.id === 'file-preview-modal') {
        document.getElementById('file-preview-modal').classList.remove('active');
      }
    });
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

  formatBytes(bytes) {
    if (!bytes || bytes <= 0) return '0 B';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  },

  getFileBadgeIcon(ext) {
    ext = (ext || '').toLowerCase();
    if (['jpg', 'jpeg', 'png'].includes(ext)) return 'IMG';
    if (ext === 'pdf') return 'PDF';
    if (['doc', 'docx'].includes(ext)) return 'DOC';
    if (['xls', 'xlsx'].includes(ext)) return 'XLS';
    if (ext === 'txt') return 'TXT';
    return 'FILE';
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
    const createdStr = t.created_at
      ? new Date(t.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
      : 'recently';
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

    // Render Reference Attachments
    this.renderReferenceAttachments(t.reference_attachments || []);

    // Timeline
    this.renderTimeline(t.status_history || []);

    // Action buttons in top-bar
    this.renderActions();
  },

  // =========================================================================
  // Discussion Thread & Comments
  // =========================================================================

  async loadComments() {
    try {
      const res = await window.API.get(`/api/tasks/${this.taskId}/comments`);
      if (res && res.ok) {
        this.comments = res.data || [];
        this.renderDiscussion(this.comments);
      }
    } catch (err) {
      console.error('Failed to load comments:', err);
    }
  },

  renderDiscussion(comments) {
    const threadEl = document.getElementById('detail-discussion-thread');
    const countBadge = document.getElementById('detail-comments-count');
    if (countBadge) countBadge.textContent = comments.length;

    if (!threadEl) return;

    if (!comments || comments.length === 0) {
      threadEl.innerHTML = `
        <div class="empty-state-sm">
          <p class="text-muted">No messages yet. Be the first to start the discussion or ask a question!</p>
        </div>
      `;
      return;
    }

    threadEl.innerHTML = comments
      .map((c) => {
        const initial = (c.author_name || 'U').charAt(0).toUpperCase();
        const roleStr = c.author_role ? c.author_role.replace('_', ' ').toUpperCase() : '';
        const timeStr = c.created_at
          ? new Date(c.created_at).toLocaleString(undefined, {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })
          : '';

        // Format @mentions with highlighted tags
        const formattedContent = this.formatMentions(c.content || '');

        // Render attachments chips & image thumbnails
        let attachmentsHtml = '';
        if (c.attachments && c.attachments.length > 0) {
          attachmentsHtml = `
            <div class="message-attachments-wrap">
              ${c.attachments
                .map((att) => {
                  if (att.is_image) {
                    return `
                      <div class="attachment-image-thumb-card">
                        <img src="${att.preview_url}" alt="${att.original_filename}" class="comment-img-thumb" onclick="TaskDetail.openPreview(${att.id})">
                        <div class="thumb-meta">
                          <span class="thumb-name" title="${att.original_filename}">${att.original_filename}</span>
                          <span class="thumb-size">${att.file_size_human}</span>
                        </div>
                      </div>
                    `;
                  } else {
                    return `
                      <div class="attachment-file-chip">
                        <span class="file-chip-icon">${this.getFileBadgeIcon(att.file_extension)}</span>
                        <div class="file-chip-info">
                          <div class="file-chip-name" title="${att.original_filename}">${att.original_filename}</div>
                          <div class="file-chip-size text-muted">${att.file_size_human}</div>
                        </div>
                        <div class="file-chip-actions">
                          ${
                            att.is_previewable
                              ? `<button type="button" class="btn btn-ghost btn-xs" onclick="TaskDetail.openPreview(${att.id})" title="Preview">Preview</button>`
                              : ''
                          }
                          <a href="${att.download_url}" class="btn btn-ghost btn-xs" download title="Download">
                            <svg class="icon icon-xs" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                          </a>
                        </div>
                      </div>
                    `;
                  }
                })
                .join('')}
            </div>
          `;
        }

        return `
          <div class="discussion-message" id="comment-${c.id}">
            <div class="message-avatar">${initial}</div>
            <div class="message-content-box">
              <div class="message-header">
                <span class="message-author">${c.author_name}</span>
                ${roleStr ? `<span class="badge badge-neutral message-role-badge">${roleStr}</span>` : ''}
                <span class="message-time text-muted">${timeStr}</span>
              </div>
              <div class="message-body">${formattedContent}</div>
              ${attachmentsHtml}
            </div>
          </div>
        `;
      })
      .join('');

    // Scroll to bottom of thread
    threadEl.scrollTop = threadEl.scrollHeight;
  },

  formatMentions(text) {
    if (!text) return '';
    const escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');

    return escaped.replace(/(?:^|[\s(])@([a-zA-Z0-9_.-]+)/g, (match, username) => {
      return ` <span class="mention-tag" data-username="${username}">@${username}</span>`;
    });
  },

  async handlePostComment() {
    const input = document.getElementById('comment-content-input');
    const content = input?.value?.trim() || '';
    const files = this.composerFiles;

    if (!content && files.length === 0) {
      window.API.toast('Please enter a message or attach a file.', 'danger');
      return;
    }

    const sendBtn = document.getElementById('btn-send-comment');
    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.innerHTML = '<span>Sending...</span>';
    }

    try {
      let res;
      if (files.length > 0) {
        const formData = new FormData();
        formData.append('content', content);
        for (const file of files) {
          formData.append('files', file);
        }
        res = await window.API.post(`/api/tasks/${this.taskId}/comments`, formData);
      } else {
        res = await window.API.post(`/api/tasks/${this.taskId}/comments`, { content });
      }

      if (res && res.ok) {
        input.value = '';
        this.clearComposerStagedFiles();
        window.API.toast('Message posted!', 'success');
        await this.loadComments();
        // Also refresh task history
        const refreshedTask = await window.API.get(`/api/tasks/${this.taskId}`);
        if (refreshedTask && refreshedTask.ok) {
          this.task = refreshedTask.data;
          this.renderTimeline(this.task.status_history || []);
        }
      } else {
        window.API.toast(res?.error || 'Failed to post message', 'danger');
      }
    } catch (err) {
      console.error('Error posting comment:', err);
      window.API.toast('Failed to send message. Please try again.', 'danger');
    } finally {
      if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.innerHTML = `
          <svg class="icon icon-sm" viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
          <span>Send Message</span>
        `;
      }
    }
  },

  // =========================================================================
  // Reference Attachments
  // =========================================================================

  renderReferenceAttachments(attachments) {
    const listEl = document.getElementById('detail-references-list');
    const countBadge = document.getElementById('detail-references-count');
    const uploadBtn = document.getElementById('btn-open-upload-ref-modal');

    if (countBadge) countBadge.textContent = attachments.length;

    // Show upload button for managers
    const u = this.currentUser;
    const isManager = u && (['super_admin', 'admin', 'team_lead'].includes(u.role) || this.task.user_id === u.id);
    if (uploadBtn) {
      uploadBtn.style.display = isManager ? 'inline-flex' : 'none';
    }

    if (!listEl) return;

    if (!attachments || attachments.length === 0) {
      listEl.innerHTML = '<p class="text-muted" style="margin: 0.5rem 0;">No reference attachments provided yet.</p>';
      return;
    }

    listEl.innerHTML = attachments
      .map((att) => {
        return `
        <div class="reference-file-card" id="attachment-${att.id}">
          <div class="ref-file-icon">${this.getFileBadgeIcon(att.file_extension)}</div>
          <div class="ref-file-info">
            <div class="ref-file-name" title="${att.original_filename}">${att.original_filename}</div>
            <div class="ref-file-meta text-muted">
              <span>${att.file_size_human}</span>
              <span>•</span>
              <span>Uploaded by ${att.uploader_name || 'Team Lead'}</span>
            </div>
          </div>
          <div class="ref-file-actions">
            ${
              att.is_previewable
                ? `<button type="button" class="btn btn-secondary btn-xs" onclick="TaskDetail.openPreview(${att.id})">Preview</button>`
                : ''
            }
            <a href="${att.download_url}" class="btn btn-primary btn-xs" download>Download</a>
            ${
              isManager
                ? `<button type="button" class="btn btn-ghost btn-xs text-danger" onclick="TaskDetail.deleteAttachment(${att.id})" title="Delete attachment">
                     <svg class="icon icon-xs" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                   </button>`
                : ''
            }
          </div>
        </div>
      `;
      })
      .join('');
  },

  async handleReferenceUpload() {
    if (this.refFiles.length === 0) {
      window.API.toast('Please select at least one file to upload.', 'danger');
      return;
    }

    const confirmBtn = document.getElementById('btn-upload-ref-confirm');
    if (confirmBtn) {
      confirmBtn.disabled = true;
      confirmBtn.textContent = 'Uploading...';
    }

    try {
      const formData = new FormData();
      formData.append('attachment_type', 'reference');
      for (const f of this.refFiles) {
        formData.append('files', f);
      }

      const res = await window.API.post(`/api/tasks/${this.taskId}/attachments`, formData);
      if (res && res.ok) {
        window.API.toast('Reference files uploaded successfully!', 'success');
        document.getElementById('upload-reference-modal')?.classList.remove('active');
        this.clearRefStagedFiles();

        // Refresh task to get new reference attachments
        const taskRes = await window.API.get(`/api/tasks/${this.taskId}`);
        if (taskRes && taskRes.ok) {
          this.task = taskRes.data;
          this.renderTask();
        }
      } else {
        window.API.toast(res?.error || 'Failed to upload files', 'danger');
      }
    } catch (err) {
      console.error('Error uploading reference files:', err);
      window.API.toast('File upload failed.', 'danger');
    } finally {
      if (confirmBtn) {
        confirmBtn.disabled = false;
        confirmBtn.textContent = 'Upload Files';
      }
    }
  },

  // =========================================================================
  // Submissions & Review History
  // =========================================================================

  async loadSubmissions() {
    try {
      const res = await window.API.get(`/api/tasks/${this.taskId}/submissions`);
      if (res && res.ok) {
        this.submissions = res.data || [];
        this.renderSubmissions(this.submissions);
      }
    } catch (err) {
      console.error('Failed to load submissions:', err);
    }
  },

  renderSubmissions(submissions) {
    const listEl = document.getElementById('detail-submissions-list');
    const countBadge = document.getElementById('detail-submissions-count');

    if (countBadge) countBadge.textContent = submissions.length;
    if (!listEl) return;

    if (!submissions || submissions.length === 0) {
      listEl.innerHTML = '<p class="text-muted" style="margin: 0.5rem 0;">No work submissions recorded yet.</p>';
      return;
    }

    listEl.innerHTML = submissions
      .map((sub, idx) => {
        const cycleNum = submissions.length - idx;
        const submittedTime = sub.created_at
          ? new Date(sub.created_at).toLocaleString(undefined, {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })
          : '';

        let statusBadge = '<span class="badge badge-warning">Under Review</span>';
        if (sub.status === 'approved') {
          statusBadge = '<span class="badge badge-success">Approved</span>';
        } else if (sub.status === 'changes_requested') {
          statusBadge = '<span class="badge badge-danger">Changes Requested</span>';
        }

        // Render deliverables attached to this submission
        let deliverablesHtml = '';
        if (sub.attachments && sub.attachments.length > 0) {
          deliverablesHtml = `
            <div class="submission-deliverables">
              <div class="deliverables-title">Deliverable Files (${sub.attachments.length}):</div>
              <div class="deliverables-grid">
                ${sub.attachments
                  .map((att) => `
                    <div class="attachment-file-chip">
                      <span class="file-chip-icon">${this.getFileBadgeIcon(att.file_extension)}</span>
                      <div class="file-chip-info">
                        <div class="file-chip-name" title="${att.original_filename}">${att.original_filename}</div>
                        <div class="file-chip-size text-muted">${att.file_size_human}</div>
                      </div>
                      <div class="file-chip-actions">
                        ${
                          att.is_previewable
                            ? `<button type="button" class="btn btn-ghost btn-xs" onclick="TaskDetail.openPreview(${att.id})">Preview</button>`
                            : ''
                        }
                        <a href="${att.download_url}" class="btn btn-ghost btn-xs" download title="Download">
                          <svg class="icon icon-xs" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                        </a>
                      </div>
                    </div>
                  `)
                  .join('')}
              </div>
            </div>
          `;
        }

        // Render lead review section if reviewed
        let reviewBlock = '';
        if (sub.reviewed_at) {
          const revTime = new Date(sub.reviewed_at).toLocaleString(undefined, {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          });
          const isApproved = sub.status === 'approved';
          reviewBlock = `
            <div class="submission-review-card ${isApproved ? 'review-card-approved' : 'review-card-changes'}">
              <div class="review-card-header">
                <span class="review-author">Reviewed by ${sub.reviewed_by_name || 'Team Lead'}</span>
                <span class="review-time text-muted">${revTime}</span>
              </div>
              <div class="review-feedback-text">
                ${sub.review_feedback ? sub.review_feedback : (isApproved ? 'Work approved and completed.' : 'Changes requested.')}
              </div>
            </div>
          `;
        }

        return `
          <div class="submission-history-item">
            <div class="submission-item-header">
              <div class="submission-item-title-wrap">
                <span class="submission-cycle-badge">Submission #${cycleNum}</span>
                <span class="submission-submitter">Submitted by <strong>${sub.submitted_by_name}</strong></span>
                <span class="submission-time text-muted">${submittedTime}</span>
              </div>
              <div>${statusBadge}</div>
            </div>

            <div class="submission-summary-box">
              <div class="submission-summary-label">Summary of Work Completed:</div>
              <div class="submission-summary-content">${sub.summary || '<span class="text-muted">No notes provided.</span>'}</div>
            </div>

            ${deliverablesHtml}
            ${reviewBlock}
          </div>
        `;
      })
      .join('');
  },

  async handleWorkSubmission() {
    const notes = document.getElementById('submit-notes-input')?.value?.trim() || '';
    if (!notes) {
      window.API.toast('Please detail the completed work in the summary notes.', 'danger');
      return;
    }

    const submitBtn = document.getElementById('btn-submit-work-confirm');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span>Submitting...</span>';
    }

    try {
      let res;
      if (this.submitFiles.length > 0) {
        const formData = new FormData();
        formData.append('notes', notes);
        for (const f of this.submitFiles) {
          formData.append('files', f);
        }
        res = await window.API.post(`/api/tasks/${this.taskId}/submit`, formData);
      } else {
        res = await window.API.post(`/api/tasks/${this.taskId}/submit`, { notes });
      }

      if (res && res.ok) {
        window.API.toast('Work submitted for review successfully!', 'success');
        document.getElementById('submit-review-modal')?.classList.remove('active');
        document.getElementById('submit-notes-input').value = '';
        this.clearSubmitStagedFiles();

        this.task = res.data;
        this.renderTask();
        await this.loadSubmissions();
      } else {
        window.API.toast(res?.error || 'Failed to submit work for review', 'danger');
      }
    } catch (err) {
      console.error('Error submitting work:', err);
      window.API.toast('Submission failed.', 'danger');
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `
          <svg class="icon icon-sm" viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
          <span>Submit for Review</span>
        `;
      }
    }
  },

  async handleReviewDecision() {
    const action = document.getElementById('review-action-type')?.value || 'approve';
    const notes = document.getElementById('review-notes-input')?.value?.trim() || '';

    const submitBtn = document.getElementById('review-submit-btn');
    if (submitBtn) submitBtn.disabled = true;

    try {
      const res = await window.API.post(`/api/tasks/${this.taskId}/review`, { action, notes });
      if (res && res.ok) {
        const msg = action === 'approve' ? 'Task approved and completed!' : 'Changes requested.';
        window.API.toast(msg, 'success');
        document.getElementById('review-action-modal')?.classList.remove('active');
        document.getElementById('review-notes-input').value = '';

        this.task = res.data;
        this.renderTask();
        await this.loadSubmissions();
      } else {
        window.API.toast(res?.error || 'Failed to submit review', 'danger');
      }
    } catch (err) {
      console.error('Error submitting review:', err);
      window.API.toast('Review action failed.', 'danger');
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  },

  // =========================================================================
  // Staged Files Handling
  // =========================================================================

  handleStagedFiles(newFiles, target) {
    if (!newFiles || newFiles.length === 0) return;

    if (target === 'composer') {
      this.composerFiles = this.composerFiles.concat(newFiles);
      this.renderStagedFiles(this.composerFiles, 'composer-files-tray', 'composer');
    } else if (target === 'submit') {
      this.submitFiles = this.submitFiles.concat(newFiles);
      this.renderStagedFiles(this.submitFiles, 'submit-selected-files', 'submit');
    } else if (target === 'reference') {
      this.refFiles = this.refFiles.concat(newFiles);
      this.renderStagedFiles(this.refFiles, 'ref-selected-files', 'reference');
    }
  },

  renderStagedFiles(files, containerId, target) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (!files || files.length === 0) {
      container.style.display = 'none';
      container.innerHTML = '';
      return;
    }

    container.style.display = 'flex';
    container.innerHTML = files
      .map((f, i) => `
        <div class="selected-file-chip">
          <span class="file-name" title="${f.name}">${f.name}</span>
          <span class="file-size text-muted">${this.formatBytes(f.size)}</span>
          <button type="button" class="remove-file-btn" onclick="TaskDetail.removeStagedFile(${i}, '${target}')" title="Remove file">&times;</button>
        </div>
      `)
      .join('');
  },

  removeStagedFile(index, target) {
    if (target === 'composer') {
      this.composerFiles.splice(index, 1);
      this.renderStagedFiles(this.composerFiles, 'composer-files-tray', 'composer');
    } else if (target === 'submit') {
      this.submitFiles.splice(index, 1);
      this.renderStagedFiles(this.submitFiles, 'submit-selected-files', 'submit');
    } else if (target === 'reference') {
      this.refFiles.splice(index, 1);
      this.renderStagedFiles(this.refFiles, 'ref-selected-files', 'reference');
    }
  },

  clearComposerStagedFiles() {
    this.composerFiles = [];
    this.renderStagedFiles([], 'composer-files-tray', 'composer');
  },

  clearSubmitStagedFiles() {
    this.submitFiles = [];
    this.renderStagedFiles([], 'submit-selected-files', 'submit');
  },

  clearRefStagedFiles() {
    this.refFiles = [];
    this.renderStagedFiles([], 'ref-selected-files', 'reference');
  },

  // =========================================================================
  // Safe File Previews & Deletion
  // =========================================================================

  async openPreview(attachmentId) {
    const modal = document.getElementById('file-preview-modal');
    const content = document.getElementById('file-preview-content');
    const nameEl = document.getElementById('preview-file-name');
    const metaEl = document.getElementById('preview-file-meta');
    const iconEl = document.getElementById('preview-file-icon');
    const dlBtn = document.getElementById('preview-download-btn');

    if (!modal || !content) return;

    // Show modal in loading state
    modal.classList.add('active');
    content.innerHTML = '<div class="preview-loading"><div class="loading-spinner"></div><p>Loading document preview...</p></div>';

    // Search for attachment in task or comments
    let att = null;
    if (this.task?.reference_attachments) {
      att = this.task.reference_attachments.find((a) => a.id === attachmentId);
    }
    if (!att && this.comments) {
      for (const c of this.comments) {
        if (c.attachments) {
          att = c.attachments.find((a) => a.id === attachmentId);
          if (att) break;
        }
      }
    }
    if (!att && this.submissions) {
      for (const s of this.submissions) {
        if (s.attachments) {
          att = s.attachments.find((a) => a.id === attachmentId);
          if (att) break;
        }
      }
    }

    const filename = att?.original_filename || `Attachment #${attachmentId}`;
    const ext = att?.file_extension || filename.split('.').pop();
    const downloadUrl = `/api/tasks/${this.taskId}/attachments/${attachmentId}/download`;
    const previewUrl = `/api/tasks/${this.taskId}/attachments/${attachmentId}/preview`;

    if (nameEl) nameEl.textContent = filename;
    if (metaEl) metaEl.textContent = att ? `${att.file_size_human} • ${att.file_type}` : '';
    if (iconEl) iconEl.textContent = this.getFileBadgeIcon(ext);
    if (dlBtn) dlBtn.href = downloadUrl;

    const lowerExt = ext.toLowerCase();

    // 1. Image preview
    if (['jpg', 'jpeg', 'png'].includes(lowerExt)) {
      content.innerHTML = `
        <div class="image-preview-wrapper">
          <img src="${previewUrl}" alt="${filename}" class="preview-full-image">
        </div>
      `;
      return;
    }

    // 2. PDF preview
    if (lowerExt === 'pdf') {
      content.innerHTML = `
        <iframe src="${previewUrl}" class="preview-pdf-frame" title="${filename}"></iframe>
      `;
      return;
    }

    // 3. Text preview
    if (lowerExt === 'txt') {
      try {
        const textRes = await fetch(previewUrl);
        if (textRes.ok) {
          const text = await textRes.text();
          content.innerHTML = `<pre class="preview-text-block">${text.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>`;
          return;
        }
      } catch (e) {
        console.error('Failed to fetch text preview:', e);
      }
    }

    // 4. Fallback for office documents (DOCX, XLSX)
    content.innerHTML = `
      <div class="preview-unsupported-card">
        <div class="file-type-icon-lg">${this.getFileBadgeIcon(ext)}</div>
        <h3>${filename}</h3>
        <p class="text-muted">In-browser preview is not supported for .${ext} files. Please download the document to view it in your application.</p>
        <a href="${downloadUrl}" class="btn btn-primary" download>
          <svg class="icon" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
          <span>Download ${filename}</span>
        </a>
      </div>
    `;
  },

  async deleteAttachment(attachmentId) {
    if (!confirm('Are you sure you want to delete this attachment?')) return;

    try {
      const res = await window.API.delete(`/api/tasks/${this.taskId}/attachments/${attachmentId}`);
      if (res && res.ok) {
        window.API.toast('Attachment deleted successfully', 'success');
        // Refresh comments and task
        await Promise.all([
          this.loadComments(),
          this.loadSubmissions(),
        ]);
        const taskRes = await window.API.get(`/api/tasks/${this.taskId}`);
        if (taskRes && taskRes.ok) {
          this.task = taskRes.data;
          this.renderTask();
        }
      } else {
        window.API.toast(res?.error || 'Failed to delete attachment', 'danger');
      }
    } catch (err) {
      window.API.toast('Failed to delete attachment.', 'danger');
    }
  },

  // =========================================================================
  // Timeline & Top Bar Actions
  // =========================================================================

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
        const newLabel = item.new_status ? item.new_status.replace('_', ' ').toUpperCase() : '';

        return `
        <div class="timeline-item">
          <div class="timeline-marker"></div>
          <div class="timeline-content">
            <div class="timeline-header">
              <span class="timeline-author">${item.changed_by_name}</span>
              ${newLabel ? `<span class="timeline-transition">status: <strong>${newLabel}</strong></span>` : ''}
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

    // If task is in review and user has review privileges
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
      document.getElementById('review-action-modal')?.classList.add('active');
    });

    document.getElementById('btn-request-changes')?.addEventListener('click', () => {
      document.getElementById('review-action-type').value = 'request_changes';
      document.getElementById('review-action-title').textContent = 'Request Changes on Task';
      document.getElementById('review-notes-label').textContent = 'Required Fixes & Feedback';
      const submitBtn = document.getElementById('review-submit-btn');
      submitBtn.textContent = 'Send Changes Requested';
      submitBtn.className = 'btn btn-danger';
      document.getElementById('review-action-modal')?.classList.add('active');
    });

    document.getElementById('btn-open-submit-modal')?.addEventListener('click', () => {
      document.getElementById('submit-review-modal')?.classList.add('active');
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
