import { useState, useEffect, useCallback } from 'react';
import { BrainCircuit, RefreshCw, Trash2, ShieldOff, UserX } from 'lucide-react';
import api from '../utils/api';
import Toggle from '../components/Toggle';

// ── Stat Card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, children }) {
  return (
    <div className="card flex-1 min-w-0">
      <div className="text-xs text-ink-muted mb-1">{label}</div>
      {children ?? <div className="text-2xl font-bold text-ink-primary">{value ?? '—'}</div>}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function AiAdminPage() {
  const [sessions, setSessions]           = useState([]);
  const [blocked, setBlocked]             = useState([]);
  const [aiEnabled, setAiEnabled]         = useState(null);
  const [sessionCount, setSessionCount]   = useState(null);
  const [abuseCount, setAbuseCount]       = useState(null);

  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingBlocked, setLoadingBlocked]   = useState(false);
  const [togglingAi, setTogglingAi]           = useState(false);

  const [blockUserId, setBlockUserId]   = useState('');
  const [blockTtl, setBlockTtl]         = useState('');
  const [blocking, setBlocking]         = useState(false);

  const [msg, setMsg] = useState(null);

  const showMsg = (text, type = 'ok') => {
    setMsg({ text, type });
    setTimeout(() => setMsg(null), 3000);
  };

  // ── Load settings ────────────────────────────────────────────────────────
  const loadSettings = useCallback(async () => {
    try {
      const { data } = await api.get('/api/ai/admin/settings');
      setAiEnabled(data.enabled ?? false);
    } catch {
      setAiEnabled(false);
    }
  }, []);

  // ── Load sessions ─────────────────────────────────────────────────────────
  const loadSessions = useCallback(async () => {
    setLoadingSessions(true);
    try {
      const { data } = await api.get('/api/ai/admin/sessions');
      const list = Array.isArray(data) ? data : (data.sessions ?? []);
      setSessions(list);
      setSessionCount(list.length);
    } catch {
      setSessions([]);
      setSessionCount(0);
    } finally {
      setLoadingSessions(false);
    }
  }, []);

  // ── Load blocked ──────────────────────────────────────────────────────────
  const loadBlocked = useCallback(async () => {
    setLoadingBlocked(true);
    try {
      const { data } = await api.get('/api/ai/admin/abuse');
      const list = Array.isArray(data) ? data : (data.blocked ?? []);
      setBlocked(list);
      setAbuseCount(list.length);
    } catch {
      setBlocked([]);
      setAbuseCount(0);
    } finally {
      setLoadingBlocked(false);
    }
  }, []);

  useEffect(() => {
    loadSettings();
    loadSessions();
    loadBlocked();
  }, [loadSettings, loadSessions, loadBlocked]);

  // ── Toggle AI ─────────────────────────────────────────────────────────────
  const handleToggleAi = async (newVal) => {
    setTogglingAi(true);
    try {
      await api.patch('/api/ai/admin/settings', { enabled: newVal });
      setAiEnabled(newVal);
      showMsg(`AI ${newVal ? 'enabled' : 'disabled'} globally.`);
    } catch (err) {
      showMsg(err.response?.data?.detail || 'Failed to update setting.', 'err');
    } finally {
      setTogglingAi(false);
    }
  };

  // ── Terminate session ─────────────────────────────────────────────────────
  const terminateSession = async (owner_id, domain, agent) => {
    if (!confirm(`Terminate session for owner ${owner_id} (${domain} / ${agent})?`)) return;
    try {
      await api.delete(`/api/ai/admin/sessions/${owner_id}/${domain}/${agent}`);
      showMsg('Session terminated.');
      loadSessions();
    } catch (err) {
      showMsg(err.response?.data?.detail || 'Failed to terminate session.', 'err');
    }
  };

  // ── Unblock user ──────────────────────────────────────────────────────────
  const unblockUser = async (user_id) => {
    if (!confirm(`Unblock user ${user_id}?`)) return;
    try {
      await api.delete(`/api/ai/admin/block/${user_id}`);
      showMsg('User unblocked.');
      loadBlocked();
    } catch (err) {
      showMsg(err.response?.data?.detail || 'Failed to unblock user.', 'err');
    }
  };

  // ── Manual block ──────────────────────────────────────────────────────────
  const blockUser = async () => {
    const uid = blockUserId.trim();
    if (!uid) return;
    setBlocking(true);
    try {
      const params = blockTtl.trim() ? { ttl_secs: parseInt(blockTtl, 10) } : {};
      await api.post(`/api/ai/admin/block/${uid}`, params);
      showMsg(`User ${uid} blocked.`);
      setBlockUserId('');
      setBlockTtl('');
      loadBlocked();
    } catch (err) {
      showMsg(err.response?.data?.detail || 'Failed to block user.', 'err');
    } finally {
      setBlocking(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Page header */}
      <h1 className="text-xl font-bold text-ink-primary flex items-center gap-2">
        <BrainCircuit size={20} /> AI Admin
      </h1>

      {/* Inline message */}
      {msg && (
        <div className={`text-sm px-4 py-2 rounded-md ${msg.type === 'ok' ? 'bg-ok/15 text-ok-light' : 'bg-bad/15 text-bad-light'}`}>
          {msg.text}
        </div>
      )}

      {/* ── Stats row ────────────────────────────────────────────────────── */}
      <div className="flex gap-4 flex-wrap">
        <StatCard label="Active Sessions" value={sessionCount} />
        <StatCard label="AI Status">
          <div className="flex items-center gap-3 mt-1">
            <span className={`text-lg font-semibold ${aiEnabled ? 'text-ok' : 'text-bad-light'}`}>
              {aiEnabled === null ? '…' : aiEnabled ? 'Enabled' : 'Disabled'}
            </span>
            <Toggle checked={!!aiEnabled} onChange={handleToggleAi} disabled={togglingAi || aiEnabled === null} colorOn="brand" size="sm" />
          </div>
        </StatCard>
        <StatCard label="Abuse Blocks" value={abuseCount} />
      </div>

      {/* ── Global Settings card ─────────────────────────────────────────── */}
      <div className="card space-y-3">
        <h2 className="text-sm font-semibold text-ink-primary flex items-center gap-2">
          <BrainCircuit size={14} /> Global AI Settings
        </h2>
        <div className="flex items-center justify-between py-2 border-b border-panel-subtle">
          <div>
            <div className="text-sm text-ink-primary">AI Feature</div>
            <div className="text-xs text-ink-muted">Enable or disable AI assistance panel-wide.</div>
          </div>
          <Toggle checked={!!aiEnabled} onChange={handleToggleAi} disabled={togglingAi || aiEnabled === null} colorOn="brand" size="sm" />
        </div>
      </div>

      {/* ── Active Sessions table ────────────────────────────────────────── */}
      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink-primary">Active Sessions</h2>
          <button
            onClick={loadSessions}
            disabled={loadingSessions}
            className="flex items-center gap-1.5 text-xs text-ink-muted hover:text-ink-primary transition-colors disabled:opacity-50"
          >
            <RefreshCw size={12} className={loadingSessions ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        {sessions.length === 0 ? (
          <p className="text-sm text-ink-muted py-2">{loadingSessions ? 'Loading…' : 'No active sessions.'}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-panel-subtle text-left text-xs text-ink-muted">
                  <th className="pb-2 pr-4 font-medium">Owner ID</th>
                  <th className="pb-2 pr-4 font-medium">Domain</th>
                  <th className="pb-2 pr-4 font-medium">Agent</th>
                  <th className="pb-2 pr-4 font-medium">TTL (s)</th>
                  <th className="pb-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-panel-subtle">
                {sessions.map((s, i) => (
                  <tr key={i} className="text-ink-secondary">
                    <td className="py-2 pr-4 font-mono text-xs">{s.owner_id ?? s.owner ?? '—'}</td>
                    <td className="py-2 pr-4 text-xs truncate max-w-[160px]">{s.domain ?? '—'}</td>
                    <td className="py-2 pr-4 text-xs">{s.agent ?? '—'}</td>
                    <td className="py-2 pr-4 text-xs">{s.ttl_secs ?? '—'}</td>
                    <td className="py-2">
                      <button
                        onClick={() => terminateSession(s.owner_id ?? s.owner, s.domain, s.agent)}
                        className="flex items-center gap-1 text-xs text-bad-light hover:text-bad transition-colors"
                        title="Terminate session"
                      >
                        <Trash2 size={12} /> Terminate
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ── Blocked Users table ──────────────────────────────────────────── */}
      <div className="card space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink-primary">Blocked Users</h2>
          <button
            onClick={loadBlocked}
            disabled={loadingBlocked}
            className="flex items-center gap-1.5 text-xs text-ink-muted hover:text-ink-primary transition-colors disabled:opacity-50"
          >
            <RefreshCw size={12} className={loadingBlocked ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        {/* Manual block input */}
        <div className="flex gap-2 flex-wrap">
          <input
            className="input flex-1 min-w-[140px] text-sm"
            placeholder="User ID to block"
            value={blockUserId}
            onChange={e => setBlockUserId(e.target.value)}
          />
          <input
            className="input w-28 text-sm"
            placeholder="TTL (s, opt.)"
            type="number"
            min={0}
            value={blockTtl}
            onChange={e => setBlockTtl(e.target.value)}
          />
          <button
            onClick={blockUser}
            disabled={blocking || !blockUserId.trim()}
            className="btn-primary flex items-center gap-1.5 text-xs px-3 disabled:opacity-50"
          >
            <UserX size={12} />
            {blocking ? 'Blocking…' : 'Block'}
          </button>
        </div>

        {blocked.length === 0 ? (
          <p className="text-sm text-ink-muted py-2">{loadingBlocked ? 'Loading…' : 'No blocked users.'}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-panel-subtle text-left text-xs text-ink-muted">
                  <th className="pb-2 pr-4 font-medium">Owner ID</th>
                  <th className="pb-2 pr-4 font-medium">TTL (s)</th>
                  <th className="pb-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-panel-subtle">
                {blocked.map((b, i) => (
                  <tr key={i} className="text-ink-secondary">
                    <td className="py-2 pr-4 font-mono text-xs">{b.user_id ?? b.owner_id ?? b.id ?? '—'}</td>
                    <td className="py-2 pr-4 text-xs">
                      {b.ttl_secs === -1 ? 'Permanent' : (b.ttl_secs ?? '—')}
                    </td>
                    <td className="py-2">
                      <button
                        onClick={() => unblockUser(b.user_id ?? b.owner_id ?? b.id)}
                        className="flex items-center gap-1 text-xs text-warn-light hover:text-warn transition-colors"
                        title="Unblock user"
                      >
                        <ShieldOff size={12} /> Unblock
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
