async function login(email, password) {
    const data = await api('POST', '/auth/login', { email, password });
    localStorage.setItem('user', JSON.stringify(data.user));
    return data.user;
}

async function register(username, email, password) {
    return api('POST', '/auth/register', { username, email, password });
}

async function logout() {
    await api('POST', '/auth/logout');
    localStorage.removeItem('user');
    location.reload();
}

function getUser() {
    const u = localStorage.getItem('user');
    return u ? JSON.parse(u) : null;
}
