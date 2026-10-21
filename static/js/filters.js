
/**
 * Dashboard & Filters Module (M7)
 * Task-Manager-Web-App
 *
 * Features:
 * - Search tasks
 * - Filter by status, priority, category and due date
 * - Sort tasks
 * - Reset filters
 * - Receives tasks from dashboard.js through tasks-loaded
 * - Broadcasts filtered results through tasks-filtered
 */

(function () {
    'use strict';

    let allTasks = [];
    let categories = [];
    let filterSubscribers = [];

    const filterState = {
        search: '',
        status: 'all',
        priority: 'all',
        category: 'all',
        dueDate: 'all',
        sortBy: 'due_asc'
    };

    const PRIORITY_WEIGHTS = {
        high: 3,
        medium: 2,
        low: 1
    };

    // Safely convert a value to a comparable date.
    function getDate(value) {
        if (!value) return null;

        const date = new Date(value);

        return Number.isNaN(date.getTime()) ? null : date;
    }

    function startOfDay(date) {
        const result = new Date(date);
        result.setHours(0, 0, 0, 0);
        return result;
    }

    function isSameDay(first, second) {
        if (!first || !second) return false;

        return (
            first.getFullYear() === second.getFullYear() &&
            first.getMonth() === second.getMonth() &&
            first.getDate() === second.getDate()
        );
    }

    function getTaskStatus(task) {
        return String(task.status || 'pending').toLowerCase();
    }

    function getTaskPriority(task) {
        return String(task.priority || 'medium').toLowerCase();
    }

    function getTaskDueDate(task) {
        return getDate(task.due_date || task.dueDate);
    }

    function getTaskCategory(task) {
        return task.category_id ??
            task.categoryId ??
            task.category?.id ??
            task.category ??
            null;
    }

    function getTaskCreatedDate(task) {
        return getDate(task.created_at || task.createdAt);
    }

    function isCompleted(task) {
        const status = getTaskStatus(task);

        return status === 'completed' ||
            status === 'complete' ||
            status === 'done';
    }

    function isOverdue(task) {
        const dueDate = getTaskDueDate(task);

        return Boolean(
            dueDate &&
            startOfDay(dueDate) < startOfDay(new Date()) &&
            !isCompleted(task)
        );
    }

    function matchesDueDate(task, selectedDate) {
        if (selectedDate === 'all') return true;

        const dueDate = getTaskDueDate(task);

        if (selectedDate === 'no_date') {
            return !dueDate;
        }

        if (!dueDate) return false;

        const today = startOfDay(new Date());
        const dueDay = startOfDay(dueDate);

        if (selectedDate === 'overdue') {
            return dueDay < today && !isCompleted(task);
        }

        if (selectedDate === 'today') {
            return isSameDay(dueDate, today);
        }

        if (selectedDate === 'week') {
            const endOfWeek = new Date(today);
            endOfWeek.setDate(endOfWeek.getDate() + 7);

            return dueDay >= today && dueDay <= endOfWeek;
        }

        return true;
    }

    /**
     * Filter and sort a task array without changing the original array.
     */
    function filterAndSortTasks(tasks, filters) {
        const sourceTasks = Array.isArray(tasks) ? tasks : [];
        const currentFilters = filters || filterState;

        const searchText = String(
            currentFilters.search || ''
        ).trim().toLowerCase();

        const filtered = sourceTasks.filter(function (task) {
            if (!task || typeof task !== 'object') {
                return false;
            }

            // Search task title and description.
            if (searchText) {
                const title = String(task.title || '').toLowerCase();
                const description = String(
                    task.description || ''
                ).toLowerCase();

                if (
                    !title.includes(searchText) &&
                    !description.includes(searchText)
                ) {
                    return false;
                }
            }

            // Status filter.
            if (currentFilters.status !== 'all') {
                if (
                    currentFilters.status === 'completed' &&
                    !isCompleted(task)
                ) {
                    return false;
                }

                if (
                    currentFilters.status === 'pending' &&
                    (
                        isCompleted(task) ||
                        getTaskStatus(task) !== 'pending'
                    )
                ) {
                    return false;
                }

                if (
                    currentFilters.status === 'in_progress' &&
                    getTaskStatus(task) !== 'in_progress'
                ) {
                    return false;
                }

                if (
                    currentFilters.status === 'overdue' &&
                    !isOverdue(task)
                ) {
                    return false;
                }
            }

            // Priority filter.
            if (
                currentFilters.priority !== 'all' &&
                getTaskPriority(task) !==
                    String(currentFilters.priority).toLowerCase()
            ) {
                return false;
            }

            // Category filter.
            if (currentFilters.category !== 'all') {
                const taskCategory = getTaskCategory(task);

                if (currentFilters.category === 'uncategorized') {
                    if (
                        taskCategory !== null &&
                        taskCategory !== undefined &&
                        taskCategory !== ''
                    ) {
                        return false;
                    }
                } else if (
                    String(taskCategory) !==
                    String(currentFilters.category)
                ) {
                    return false;
                }
            }

            // Due-date filter.
            if (!matchesDueDate(task, currentFilters.dueDate)) {
                return false;
            }

            return true;
        });

        // Sort without modifying the source array.
        filtered.sort(function (a, b) {
            const sortBy = currentFilters.sortBy;

            if (sortBy === 'due_asc' || sortBy === 'due_desc') {
                const dateA = getTaskDueDate(a);
                const dateB = getTaskDueDate(b);

                if (!dateA && dateB) return 1;
                if (dateA && !dateB) return -1;

                if (dateA && dateB) {
                    const difference = dateA - dateB;

                    if (difference !== 0) {
                        return sortBy === 'due_asc'
                            ? difference
                            : -difference;
                    }
                }
            }

            if (
                sortBy === 'priority_asc' ||
                sortBy === 'priority_desc'
            ) {
                const priorityA =
                    PRIORITY_WEIGHTS[getTaskPriority(a)] || 0;

                const priorityB =
                    PRIORITY_WEIGHTS[getTaskPriority(b)] || 0;

                const difference = priorityA - priorityB;

                if (difference !== 0) {
                    return sortBy === 'priority_asc'
                        ? difference
                        : -difference;
                }
            }

            if (
                sortBy === 'created_asc' ||
                sortBy === 'created_desc'
            ) {
                const dateA = getTaskCreatedDate(a);
                const dateB = getTaskCreatedDate(b);

                if (!dateA && dateB) return 1;
                if (dateA && !dateB) return -1;

                if (dateA && dateB) {
                    const difference = dateA - dateB;

                    if (difference !== 0) {
                        return sortBy === 'created_asc'
                            ? difference
                            : -difference;
                    }
                }
            }

            // Stable fallback.
            return String(a.id ?? '').localeCompare(
                String(b.id ?? ''),
                undefined,
                { numeric: true }
            );
        });

        return filtered;
    }

    function getFilteredTasks() {
        return filterAndSortTasks(allTasks, filterState);
    }

    function getActiveFilters() {
        return { ...filterState };
    }

    function escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, function (char) {
            const entities = {
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '"': '&quot;',
                "'": '&#39;'
            };

            return entities[char];
        });
    }

    function dispatchFilteredTasks() {
        const filteredTasks = getFilteredTasks();

        document.dispatchEvent(
            new CustomEvent('tasks-filtered', {
                detail: {
                    tasks: filteredTasks,
                    filters: getActiveFilters(),
                    total: allTasks.length,
                    filteredCount: filteredTasks.length
                }
            })
        );

        filterSubscribers.forEach(function (callback) {
            try {
                callback(filteredTasks, getActiveFilters());
            } catch (error) {
                console.error('Filter subscriber error:', error);
            }
        });

        updateResultCount(filteredTasks.length);
    }

    function updateFilter(name, value) {
        if (!Object.prototype.hasOwnProperty.call(filterState, name)) {
            return;
        }

        filterState[name] = value;
        dispatchFilteredTasks();
    }

    function resetFilters() {
        filterState.search = '';
        filterState.status = 'all';
        filterState.priority = 'all';
        filterState.category = 'all';
        filterState.dueDate = 'all';
        filterState.sortBy = 'due_asc';

        const root = document.getElementById('filters-root');

        if (root) {
            root.querySelectorAll('[data-filter]').forEach(function (input) {
                const name = input.dataset.filter;

                if (name === 'search') {
                    input.value = '';
                } else if (Object.prototype.hasOwnProperty.call(filterState, name)) {
                    input.value = filterState[name];
                }
            });
        }

        dispatchFilteredTasks();
    }

    function updateResultCount(count) {
        const element = document.getElementById('filter-result-count');

        if (element) {
            element.textContent =
                'Showing ' + count + ' of ' + allTasks.length + ' tasks';
        }
    }

    function getCategoryOptions() {
        return categories.map(function (category) {
            const id = category.id ?? category._id ?? category.name;
            const name = category.name || category.title || 'Category';

            return (
                '<option value="' + escapeHtml(id) + '">' +
                escapeHtml(name) +
                '</option>'
            );
        }).join('');
    }

    /**
     * Render the filters toolbar.
     * Add <div id="filters-root"></div> to the task page if needed.
     */
    function render() {
        const root = document.getElementById('filters-root');

        if (!root) {
            console.warn(
                'TaskFilters: #filters-root not found. ' +
                'Add <div id="filters-root"></div> to the task page.'
            );
            return;
        }

        root.innerHTML = `
            <section class="task-filters" aria-label="Task filters">
                <div class="task-filters__search">
                    <input
                        type="search"
                        data-filter="search"
                        placeholder="Search tasks..."
                        aria-label="Search tasks"
                        value="${escapeHtml(filterState.search)}"
                    >
                </div>

                <div class="task-filters__controls">
                    <select data-filter="status" aria-label="Filter by status">
                        <option value="all">All statuses</option>
                        <option value="pending">Pending</option>
                        <option value="in_progress">In progress</option>
                        <option value="completed">Completed</option>
                        <option value="overdue">Overdue</option>
                    </select>

                    <select data-filter="priority" aria-label="Filter by priority">
                        <option value="all">All priorities</option>
                        <option value="high">High priority</option>
                        <option value="medium">Medium priority</option>
                        <option value="low">Low priority</option>
                    </select>

                    <select data-filter="category" aria-label="Filter by category">
                        <option value="all">All categories</option>
                        <option value="uncategorized">Uncategorized</option>
                        ${getCategoryOptions()}
                    </select>

                    <select data-filter="dueDate" aria-label="Filter by due date">
                        <option value="all">Any due date</option>
                        <option value="today">Due today</option>
                        <option value="week">Due within 7 days</option>
                        <option value="overdue">Overdue</option>
                        <option value="no_date">No due date</option>
                    </select>

                    <select data-filter="sortBy" aria-label="Sort tasks">
                        <option value="due_asc">Due date: earliest first</option>
                        <option value="due_desc">Due date: latest first</option>
                        <option value="priority_desc">Priority: high to low</option>
                        <option value="priority_asc">Priority: low to high</option>
                        <option value="created_desc">Newest first</option>
                        <option value="created_asc">Oldest first</option>
                    </select>

                    <button type="button" data-filter-reset>
                        Reset filters
                    </button>
                </div>

                <p id="filter-result-count" aria-live="polite"></p>
            </section>
        `;

        // Set current selected values.
        root.querySelectorAll('[data-filter]').forEach(function (input) {
            const name = input.dataset.filter;

            if (Object.prototype.hasOwnProperty.call(filterState, name)) {
                input.value = filterState[name];
            }
        });

        dispatchFilteredTasks();
    }

    function handleFilterInput(event) {
        const target = event.target;

        if (!target || !target.dataset.filter) return;

        const name = target.dataset.filter;

        if (!Object.prototype.hasOwnProperty.call(filterState, name)) {
            return;
        }

        updateFilter(name, target.value);
    }

    function handleTasksLoaded(event) {
        const detail = event.detail || {};

        // Supports either { tasks: [...] } or { detail: [...] } event shapes.
        if (Array.isArray(detail)) {
            allTasks = detail;
        } else if (Array.isArray(detail.tasks)) {
            allTasks = detail.tasks;
        } else if (Array.isArray(detail.data)) {
            allTasks = detail.data;
        }

        render();
    }

    function onFilterChange(callback) {
        if (typeof callback !== 'function') return function () {};

        filterSubscribers.push(callback);

        return function unsubscribe() {
            filterSubscribers = filterSubscribers.filter(
                function (subscriber) {
                    return subscriber !== callback;
                }
            );
        };
    }

    function setTasks(tasks) {
        allTasks = Array.isArray(tasks) ? tasks : [];
        dispatchFilteredTasks();
    }

    function setFilter(name, value) {
        updateFilter(name, value);
    }

    function loadCategories() {
        // Categories can also be supplied by the existing application.
        if (Array.isArray(window.taskCategories)) {
            categories = window.taskCategories;
            render();
            return;
        }

        // Use the existing API helper if available.
        if (typeof window.api === 'function') {
            window.api('GET', '/categories')
                .then(function (response) {
                    if (Array.isArray(response)) {
                        categories = response;
                    } else if (response && Array.isArray(response.categories)) {
                        categories = response.categories;
                    } else if (response && Array.isArray(response.data)) {
                        categories = response.data;
                    }

                    render();
                })
                .catch(function () {
                    // Categories are optional; other filters still work.
                    render();
                });
        }
    }

    function initialize() {
        const root = document.getElementById('filters-root');

        if (root) {
            root.addEventListener('input', handleFilterInput);
            root.addEventListener('change', handleFilterInput);

            root.addEventListener('click', function (event) {
                if (event.target.closest('[data-filter-reset]')) {
                    resetFilters();
                }
            });
        }

        // Dashboard is responsible for fetching tasks and broadcasting them.
        document.addEventListener('tasks-loaded', handleTasksLoaded);

        // Do not call Dashboard.refresh() here.
        // dashboard.js already handles tasks-updated and fetches tasks.

        loadCategories();
    }

    window.TaskFilters = {
        filterAndSortTasks: filterAndSortTasks,
        getFilteredTasks: getFilteredTasks,
        getActiveFilters: getActiveFilters,
        setFilter: setFilter,
        resetFilters: resetFilters,
        onFilterChange: onFilterChange,
        render: render,
        setTasks: setTasks
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initialize);
    } else {
        initialize();
    }
})();