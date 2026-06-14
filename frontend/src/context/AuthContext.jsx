import { createContext, useContext, useState, useEffect } from 'react';
import { toast } from 'sonner';
import api, { setAccessToken, clearAccessToken, getAccessToken } from '../utils/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]     = useState(null);
  const [loading, setLoading] = useState(true);

  // On mount: try to restore session via httpOnly cookie
  useEffect(() => {
    const existingToken = getAccessToken();
    if (existingToken) {
      // Token already in memory — verify it
      setLoading(true);
      api.get('/api/auth/me')
        .then(r => setUser(r.data))
        .catch(() => { clearAccessToken(); setUser(null); })
        .finally(() => setLoading(false));
    } else {
      // No in-memory token — try httpOnly cookie session recovery
      api.get('/api/auth/session')
        .then(r => {
          if (r.data.access_token) {
            setAccessToken(r.data.access_token);
            setUser({ id: r.data.id, username: r.data.username, role: r.data.role, email: r.data.email });
          }
        })
        .catch(() => { /* No session — user is logged out */ })
        .finally(() => setLoading(false));
    }
  }, []);

  const login = async (username, password) => {
    const form = new URLSearchParams({ username, password });
    const { data } = await api.post('/api/auth/token', form);

    // Store access token in memory only (XSS-safe)
    setAccessToken(data.access_token);

    // Fetch full user profile
    const me = await api.get('/api/auth/me');
    setUser(me.data);
    return me.data;
  };

  const refreshUser = async () => {
    try {
      const me = await api.get('/api/auth/me');
      setUser(me.data);
    } catch { /* non-fatal */ }
  };

  const logout = async () => {
    try {
      await api.post('/api/auth/logout');
    } catch { /* server logout is best-effort */ }
    clearAccessToken();
    setUser(null);
  };

  // Enforce SOC 2 session timeout: auto-logout after 15 minutes of inactivity
  useEffect(() => {
    if (!user) return;

    let timeoutId;
    const INACTIVITY_TIMEOUT = 15 * 60 * 1000; // 15 minutes in ms

    const resetTimer = () => {
      if (timeoutId) clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        logout();
        toast.warning('Logged out due to 15 minutes of inactivity.');
      }, INACTIVITY_TIMEOUT);
    };

    // Human activity listeners
    const events = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'];
    events.forEach(name => document.addEventListener(name, resetTimer));

    // Initialize timer
    resetTimer();

    return () => {
      if (timeoutId) clearTimeout(timeoutId);
      events.forEach(name => document.removeEventListener(name, resetTimer));
    };
  }, [user]);

  return (
    <AuthContext.Provider value={{ user, login, logout, loading, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
