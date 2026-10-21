const Tasks = {
    getAll: () => api('GET', '/tasks'),
    create: (task) => api('POST', '/tasks', task),
    update: (id, data) => api('PUT', `/tasks/${id}`, data),
    remove: (id) => api('DELETE', `/tasks/${id}`),
};
