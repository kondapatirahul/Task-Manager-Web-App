
const Tasks = {
    getAll: () => api("GET", "/tasks"),

    getById: (id) => api("GET", `/tasks/${id}`),

    create: (task) => api("POST", "/tasks", task),

    update: (id, task) => api("PUT", `/tasks/${id}`, task),

    remove: (id) => api("DELETE", `/tasks/${id}`),

    complete: (id) => api("PATCH", `/tasks/${id}/complete`)
};
