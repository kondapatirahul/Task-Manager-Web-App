/**
 * Dashboard & Statistics UI Module (M7 Responsibility)
 * Task-Manager-Web-App
 *
 * Computes and renders:
 * 1. Summary Cards (Pending, Completed, Overdue, Total)
 * 2. Task Completion Progress Bar (% and ratio)
 * 3. Priority Breakdown (High, Medium, Low)
 *
 * Connects with existing APIs:
 * - Tasks.getAll() from static/js/tasks.js
 * - Handles loading, empty, and unauthorized states gracefully.
 * - Broadcasts 'tasks-loaded' for shared consumption by filters.js (zero duplicate requests).
 */

(function () {
    'use strict';

    let currentTasks = [];

    /**
     * Compute dashboard metrics from an array of task objects.
     * Pure function for easy testing and zero side-effects.
     */
    function calculateMetrics(tasks) {
        if (!Array.isArray(tasks)) {
            tasks = [];
        }

        const now = new Date();
        const total = tasks.length;

        let completed = 0;
        let pending = 0;
        let inProgress = 0;
        let overdue = 0;

        const priorityCounts = {
            high: 0,
            medium: 0,
            low: 0
        };

        for (const task of tasks) {
            const status = (task.status || 'pending').toLowerCase();
            const priority = (task.priority || 'medium').toLowerCase();

            // Status counts
            if (status === 'done') {
                completed++;
            } else if (status === 'in_progress') {
                inProgress++;
                pending++; // Counted under pending workflow
            } else {
                pending++;
            }

            // Overdue check: task has due_date in the past and is not completed
            if (task.due_date && status !== 'done') {
                const dueDate = new Date(task.due_date);
                if (!isNaN(dueDate.getTime()) && dueDate < now) {
                    overdue++;
                }
            }

            // Priority distribution
            if (priority === 'high') {
                priorityCounts.high++;
            } else if (priority === 'low') {
                priorityCounts.low++;
            } else {
                // 'medium' is the default in database schema
                priorityCounts.medium++;
            }
        }

        // Safe completion percentage without division by zero
        const completionRate = total > 0 ? Math.round((completed / total) * 100) : 0;

        return {
            total,
            completed,
            pending,
            inProgress,
            overdue,
            completionRate,
            priorityCounts
        };
    }

    /**
     * Locate or create the root DOM container for the dashboard.
     */
    function getOrCreateDashboardRoot() {
        let root = document.getElementById('dashboard-root');
        if (!root) {
            const main = document.querySelector('main');
            if (main) {
                root = document.createElement('div');
                root.id = 'dashboard-root';
                main.prepend(root);
            }
        }
        return root;
    }

    /**
     * Render the full dashboard HTML using the calculated metrics.
     */
    function renderDashboard(metrics) {
        const root = getOrCreateDashboardRoot();
        if (!root) return;

        const isComplete = metrics.completionRate === 100 && metrics.total > 0;
        const progressFillClass = isComplete ? 'progress-fill complete' : 'progress-fill';

        root.innerHTML = `
            <section class="dashboard-section" aria-label="Task Dashboard">
                <div class="dashboard-header">
                    <h2 class="dashboard-title">Dashboard Overview</h2>
                    <button type="button" class="dashboard-refresh-btn" id="dashboard-refresh-btn" title="Refresh statistics">
                        ↻ Refresh
                    </button>
                </div>

                <!-- Step 2: Summary Cards -->
                <div class="dashboard-grid">
                    <div class="dashboard-card dashboard-card-pending" role="region" aria-label="Pending Tasks">
                        <span class="metric-label">Pending Tasks</span>
                        <span class="metric-value" id="stat-pending-count">${metrics.pending}</span>
                        <span class="metric-sub">${metrics.inProgress} currently in progress</span>
                    </div>

                    <div class="dashboard-card dashboard-card-completed" role="region" aria-label="Completed Tasks">
                        <span class="metric-label">Completed Tasks</span>
                        <span class="metric-value" id="stat-completed-count">${metrics.completed}</span>
                        <span class="metric-sub">${metrics.total > 0 ? metrics.completionRate + '% of total' : 'No tasks yet'}</span>
                    </div>

                    <div class="dashboard-card dashboard-card-overdue" role="region" aria-label="Overdue Tasks">
                        <span class="metric-label">Overdue Tasks</span>
                        <span class="metric-value" id="stat-overdue-count">${metrics.overdue}</span>
                        <span class="metric-sub">${metrics.overdue > 0 ? 'Requires attention' : 'All deadlines met'}</span>
                    </div>

                    <div class="dashboard-card dashboard-card-total" role="region" aria-label="Total Tasks">
                        <span class="metric-label">Total Tasks</span>
                        <span class="metric-value" id="stat-total-count">${metrics.total}</span>
                        <span class="metric-sub">Across all categories</span>
                    </div>
                </div>

                <!-- Step 3: Task Completion Progress Bar -->
                <div class="progress-card card" role="region" aria-label="Task Completion Progress">
                    <div class="progress-header">
                        <div>
                            <strong>Task Completion Progress</strong>
                            <span class="progress-stats-text">(${metrics.completed} of ${metrics.total} completed)</span>
                        </div>
                        <span class="progress-percentage-text" id="stat-progress-percent">${metrics.completionRate}%</span>
                    </div>

                    <div class="progress-track"
                         role="progressbar"
                         aria-valuenow="${metrics.completionRate}"
                         aria-valuemin="0"
                         aria-valuemax="100"
                         aria-label="Task completion percentage">
                        <div class="${progressFillClass}" style="width: ${metrics.completionRate}%;"></div>
                    </div>
                </div>

                <!-- Step 4: Priority Breakdown -->
                <div class="priority-card card" role="region" aria-label="Tasks by Priority">
                    <strong style="display: block; margin-bottom: 0.75rem;">Priority Distribution</strong>
                    <div class="priority-breakdown">
                        <div class="priority-item" title="High priority tasks">
                            <span class="badge badge-high">High</span>
                            <span class="priority-count" id="stat-priority-high">${metrics.priorityCounts.high}</span>
                        </div>
                        <div class="priority-item" title="Medium priority tasks">
                            <span class="badge badge-medium">Medium</span>
                            <span class="priority-count" id="stat-priority-medium">${metrics.priorityCounts.medium}</span>
                        </div>
                        <div class="priority-item" title="Low priority tasks">
                            <span class="badge badge-low">Low</span>
                            <span class="priority-count" id="stat-priority-low">${metrics.priorityCounts.low}</span>
                        </div>
                    </div>
                </div>
            </section>
        `;

        // Attach listener for manual refresh button
        const refreshBtn = document.getElementById('dashboard-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                fetchAndRenderDashboard();
            });
        }
    }

    /**
     * Render loading message inside the dashboard container.
     */
    function renderLoading() {
        const root = getOrCreateDashboardRoot();
        if (!root) return;
        root.innerHTML = `
            <div class="card dashboard-message" role="status">
                Loading dashboard overview...
            </div>
        `;
    }

    /**
     * Render message when user is not authenticated.
     */
    function renderUnauthenticated() {
        const root = getOrCreateDashboardRoot();
        if (!root) return;
        root.innerHTML = `
            <div class="card dashboard-message">
                Please log in to view your task dashboard and statistics.
            </div>
        `;
    }

    /**
     * Render error message with retry button.
     */
    function renderError(errorMessage) {
        const root = getOrCreateDashboardRoot();
        if (!root) return;
        root.innerHTML = `
            <div class="card dashboard-message dashboard-error" role="alert">
                <p><strong>Failed to load dashboard:</strong> ${errorMessage}</p>
                <button type="button" id="dashboard-retry-btn" style="margin-top: 0.5rem;">Retry</button>
            </div>
        `;
        const retryBtn = document.getElementById('dashboard-retry-btn');
        if (retryBtn) {
            retryBtn.addEventListener('click', () => fetchAndRenderDashboard());
        }
    }

    /**
     * Main controller: fetches tasks from existing API and updates dashboard.
     */
    async function fetchAndRenderDashboard() {
        // If Tasks API client is not loaded yet, wait briefly
        if (typeof Tasks === 'undefined' || typeof Tasks.getAll !== 'function') {
            console.warn('[Dashboard] Tasks API helper is not yet available.');
            return;
        }

        renderLoading();

        try {
            const tasks = await Tasks.getAll();
            currentTasks = Array.isArray(tasks) ? tasks : [];
            const metrics = calculateMetrics(currentTasks);
            renderDashboard(metrics);

            // Broadcast tasks loaded event for shared consumption (e.g. by filters.js)
            // This guarantees zero duplicate network requests!
            document.dispatchEvent(new CustomEvent('tasks-loaded', { detail: { tasks: currentTasks } }));
        } catch (err) {
            console.error('[Dashboard] Error fetching task data:', err);
            if (err.message && (err.message.includes('401') || err.message.toLowerCase().includes('unauthorized'))) {
                renderUnauthenticated();
            } else {
                renderError(err.message || 'Unable to connect to the server.');
            }
        }
    }

    // Expose Dashboard module globally for testing and team coordination
    window.Dashboard = {
        calculateMetrics: calculateMetrics,
        render: renderDashboard,
        refresh: fetchAndRenderDashboard,
        getTasks: () => currentTasks
    };

    // Auto-mount when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', fetchAndRenderDashboard);
    } else {
        fetchAndRenderDashboard();
    }

    // Automatically update dashboard when tasks are modified elsewhere
    document.addEventListener('tasks-updated', fetchAndRenderDashboard);

})();
