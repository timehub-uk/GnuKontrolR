import { createContext, useContext, useState, useEffect } from 'react';
import { toast } from 'sonner';
import api from '../utils/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser]     = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      api.get('/api/auth/me')
        .then(r => setUser(r.data))
        .catch(() => logout())
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (username, password) => {
    const form = new URLSearchParams({ username, password });
    const { data } = await api.post('/api/auth/token', form);
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    api.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`;
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

  const logout = () => {
    api.post('/api/auth/logout').catch(() => {});
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    delete api.defaults.headers.common['Authorization'];
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
