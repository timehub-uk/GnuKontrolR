import { useState, useEffect, useCallback } from 'react';
import { Bot, RefreshCw, Trash2, StopCircle, AlertTriangle, Loader, Activity } from 'lucide-react';
import api from '../utils/api';

function statusColor(status) {
  if (!status) return 'text-ink-muted';
  const s = status.toLowerCase();
  if (s.startsWith('up')) return 'text-ok-light';
  if (s.startsWith('exited') || s.startsWith('stopped')) return 'text-warn-light';
  return 'text-ink-muted';
}

export default function AiContainersPage() {
  const [containers, setContainers] = useState([]);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState('');
  const [confirm,    setConfirm]    = useState(null); // { name, action }

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    api.get('/api/ai-containers')
      .then(r => setContainers(r.data?.containers || []))
      .catch(() => setError('Failed to load AI containers'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const doStop = async (name) => {
    try {
      await api.post(`/api/ai-containers/${name}/stop`);
      load();
    } catch {
      setError(`Failed to stop ${name}`);
    }
    setConfirm(null);
  };

  const doRemove = async (name) => {
    try {
      await api.delete(`/api/ai-containers/${name}`);
      load();
    } catch {
      setError(`Failed to remove ${name}`);
    }
    setConfirm(null);
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-[20px] font-bold text-ink-primary flex items-center gap-2">
            <Bot size={20} className="text-brand" /> AI Containers
          </h1>
          <p className="text-[13px] text-ink-muted mt-0.5">
            Dedicated secure containers provisioned per-user for AI tool sessions
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="btn-ghost flex items-center gap-1.5 text-sm py-1.5 px-3"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-bad-light bg-bad/10 border border-bad/20 rounded-lg px-4 py-2.5 text-sm">
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {/* Confirm dialog */}
      {confirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-panel-card border border-panel-border rounded-xl p-6 max-w-sm w-full mx-4 space-y-4">
            <div className="flex items-center gap-2 text-warn-light">
              <AlertTriangle size={18} />
              <h3 className="font-semibold text-ink-primary">
                {confirm.action === 'stop' ? 'Stop container?' : 'Remove container?'}
              </h3>
            </div>
            <p className="text-[13px] text-ink-secondary">
              {confirm.action === 'stop'
                ? `Stop container ${confirm.name}? It can be restarted on next AI session.`
                : `Permanently remove ${confirm.name}? It will be recreated on next use.`}
            </p>
            <div className="flex gap-2 justify-end">
              <button className="btn-ghost text-sm py-1.5 px-4" onClick={() => setConfirm(null)}>
                Cancel
              </button>
              <button
                className={`text-sm py-1.5 px-4 rounded-lg font-medium ${confirm.action === 'stop' ? 'btn-secondary' : 'btn-danger'}`}
                onClick={() => confirm.action === 'stop' ? doStop(confirm.name) : doRemove(confirm.name)}
              >
                {confirm.action === 'stop' ? 'Stop' : 'Remove'}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="panel overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-panel-border">
              <th className="tbl-head">Container</th>
              <th className="tbl-head">Tool</th>
              <th className="tbl-head">User ID</th>
              <th className="tbl-head">Image</th>
              <th className="tbl-head">Status</th>
              <th className="tbl-head text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={6} className="text-center py-8 text-ink-muted">
                <Loader size={14} className="inline animate-spin mr-2" />Loading…
              </td></tr>
            )}
            {!loading && containers.length === 0 && (
              <tr><td colSpan={6} className="text-center py-10 text-ink-muted">
                <Activity size={16} className="inline mr-2 opacity-40" />
                No AI containers provisioned yet. They are created automatically when a user starts an AI session.
              </td></tr>
            )}
            {containers.map(c => (
              <tr key={c.name} className="border-b border-panel-border/50 hover:bg-panel-elevated transition-colors">
                <td className="tbl-cell font-mono text-xs text-ink-secondary">{c.name}</td>
                <td className="tbl-cell">
                  <span className="text-xs px-2 py-0.5 rounded-full bg-brand/10 text-brand-light font-medium">
                    {c.tool || '—'}
                  </span>
                </td>
                <td className="tbl-cell text-ink-muted">{c.user_id || '—'}</td>
                <td className="tbl-cell text-ink-muted text-xs font-mono">{c.image}</td>
                <td className={`tbl-cell text-xs font-medium ${statusColor(c.status)}`}>{c.status}</td>
                <td className="tbl-cell">
                  <div className="flex items-center justify-end gap-1.5">
                    <button
                      onClick={() => setConfirm({ name: c.name, action: 'stop' })}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs text-ink-muted hover:text-warn-light hover:bg-warn/10 transition-colors"
                      title="Stop container"
                    >
                      <StopCircle size={12} /> Stop
                    </button>
                    <button
                      onClick={() => setConfirm({ name: c.name, action: 'remove' })}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs text-ink-muted hover:text-bad-light hover:bg-bad/10 transition-colors"
                      title="Remove container"
                    >
                      <Trash2 size={12} /> Remove
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
