/**
 * Axios instance for all panel API calls.
 *
 * Request tracing
 * ───────────────
 * Every request is stamped with a UUID event ID in X-Request-ID.
 * The server echoes it back in the response header.
 * The last event ID is stored in api.lastEventId for display in error
 * messages / support UI so admins can correlate a UI error with server logs.
 */
import axios from 'axios';

function uuidv4() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = (crypto.getRandomValues(new Uint8Array(1))[0] & 15);
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
  });
}

const api = axios.create({ baseURL: '/' });

// Track the most recent event ID for error reporting
api.lastEventId = null;

// ── Outgoing: stamp every request with a fresh UUID event ID ─────────────────
api.interceptors.request.use(config => {
  const token   = localStorage.getItem('access_token');
  const eventId = uuidv4();

  if (token) config.headers.Authorization = `Bearer ${token}`;
  config.headers['X-Request-ID'] = eventId;

  // Stash it so the response interceptor can read it even if the server
  // doesn't echo it back (e.g. network error before a response arrives).
  config._eventId = eventId;
  return config;
});

// ── Incoming: capture echoed event ID, handle 401 ────────────────────────────
api.interceptors.response.use(
  res => {
    api.lastEventId = res.headers['x-request-id'] || res.config._eventId || null;
    return res;
  },
  err => {
    // Prefer the server-echoed ID; fall back to the one we generated
    api.lastEventId =
      err.response?.headers?.['x-request-id'] ||
      err.config?._eventId ||
      null;

    if (err.response?.status === 401) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

export default api;
