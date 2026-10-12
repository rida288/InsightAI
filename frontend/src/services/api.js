const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Core request helper.
 * @param {string} endpoint
 * @param {RequestInit} options
 * @param {number} timeoutMs  - Abort the request after this many milliseconds.
 *                              Chat requests use 95s (the backend gives up after 45s,
 *                              so the server's 504 normally arrives first).
 *                              All other requests use the default 15s.
 */
const request = async (endpoint, options = {}, timeoutMs = 15000) => {
  const token = localStorage.getItem('token');
  const headers = {
    ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token && { Authorization: `Bearer ${token}` }),
    ...options.headers,
  };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  let response;
  try {
    response = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers,
      signal: controller.signal,
    });
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error('Request timed out. Please try again.');
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }

  // Proxy errors (e.g. Render's 502/503 pages while the server restarts) are HTML, not JSON
  let data = null;
  try {
    data = await response.json();
  } catch {
    if (!response.ok) {
      throw new Error(`Server unavailable (HTTP ${response.status}). Please try again shortly.`);
    }
    throw new Error('Received an invalid response from the server.');
  }

  if (!response.ok) {
    const detail = data?.detail;
    // FastAPI validation errors (422) return detail as an array of { msg, ... }
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg).join('; ')
      : detail;
    throw new Error(message || 'Something went wrong');
  }
  return data;
};

export const api = {
  login: (email, password) =>
    request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  signup: (first_name, last_name, email, password) =>
    request('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ first_name, last_name, email, password }),
    }),
  logout: () => request('/auth/logout', { method: 'POST' }),

  // Admin — user management
  getPendingUsers: () => request('/admin/users/pending', { method: 'GET' }),
  getAllUsers: () => request('/admin/users', { method: 'GET' }),
  approveUser: (userId) => request(`/admin/users/${userId}/approve`, { method: 'PUT' }),
  suspendUser: (userId) => request(`/admin/users/${userId}/suspend`, { method: 'PUT' }),
  adminCreateUser: (data) =>
    request('/admin/users', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  editUser: (userId, data) =>
    request(`/admin/users/${userId}`, {
      method: 'PUT',
      body: JSON.stringify({ id: userId, ...data }),
    }),
  deleteUser: (userId) => request(`/admin/users/${userId}`, { method: 'DELETE' }),

  // Projects
  getProjects: () => request('/projects', { method: 'GET' }),
  getAllProjects: () => request('/projects/all', { method: 'GET' }),
  createProject: (formData) =>
    request('/projects', {
      method: 'POST',
      body: formData,
    }),
  getProjectData: (projectId) => request(`/projects/${projectId}/data`, { method: 'GET' }),
  deleteProject: (projectId) => request(`/projects/${projectId}`, { method: 'DELETE' }),

  // Chat uses a longer timeout than other requests; the backend itself stops at 45s.
  chatWithProject: (projectId, message) =>
    request(
      `/projects/${projectId}/chat`,
      {
        method: 'POST',
        body: JSON.stringify({ message }),
      },
      95000, // 95s client timeout (backend is 90s)
    ),

  getProtected: () => request('/protected', { method: 'GET' }),
};
