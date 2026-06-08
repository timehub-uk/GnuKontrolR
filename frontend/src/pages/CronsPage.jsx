import { useState, useEffect, useCallback } from 'react';
import { Clock, Plus, Trash2, ToggleLeft, ToggleRight, Edit3, RefreshCw, Shield, Terminal } from 'lucide-react';
import api from '../utils/api';
import { toast } from 'sonner';

function fmtSchedule(schedule) {
  const shortcuts = {
    '@reboot': 'At reboot',
    '@daily': 'Daily (midnight)',
    '@hourly': 'Every hour',
    '@weekly': 'Weekly (Sunday)',
    '@monthly': 'Monthly (1st)',
    '@yearly': 'Yearly',
    '@annually': 'Yearly',
  };
  if (shortcuts[schedule]) return shortcuts[schedule];
  const parts = schedule.split(/\s+/);
  if (parts.length === 5) {
    const [min, hour, dom, mon, dow] = parts;
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    let label = '';
    if (min !== '*' && hour !== '*' && dom === '*' && mon === '*' && dow === '*') label = `At ${hour.padStart(2, '0')}:${min.padStart(2, '0')}`;
    else if (min === '0' && hour === '*' && dom === '*' && mon === '*' && dow === '*') label = 'Every hour';
    else if (min === '0' && hour === '*' && dom === '*' && mon === '*' && dow !== '*') label = `Every ${days[parseInt(dow)] || dow}`;
    else if (dom === '*' && mon === '*' && dow === '*') label = `At ${hour.padStart(2, '0')}:${min.padStart(2, '0')}`;
    else label = schedule;
    return label;
  }
  return schedule;
}

export default function CronsPage() {
  const [entries, setEntries] = useState([]);
  const [managedIds, setManagedIds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({ schedule: '', command: '', comment: '' });

  const loadCrons = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/crons/');
      setEntries(data.entries || []);
      setManagedIds(data.managed_ids || []);
    } catch { toast.error('Failed to load crons'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadCrons(); }, [loadCrons]);

  const isManaged = (id) => managedIds.includes(id);

  const handleToggle = async (entry) => {
    try {
      const { data } = await api.post(`/api/crons/${entry.id}/toggle`);
      setEntries(prev => prev.map(e => e.id === entry.id ? { ...e, enabled: data.enabled } : e));
      toast.success(data.enabled ? 'Cron enabled' : 'Cron disabled');
    } catch { toast.error('Toggle failed'); }
  };

  const handleDelete = async (id) => {
    try {
      await api.delete(`/api/crons/${id}`);
      setEntries(prev => prev.filter(e => e.id !== id));
      toast.success('Cron deleted');
    } catch { toast.error('Delete failed'); }
  };

  const handleSave = async () => {
    if (!form.schedule.trim() || !form.command.trim()) {
      toast.error('Schedule and command are required');
      return;
    }
    try {
      if (editingId) {
        const { data } = await api.put(`/api/crons/${editingId}`, form);
        setEntries(prev => prev.map(e => e.id === editingId ? { ...e, ...data } : e));
        toast.success('Cron updated');
      } else {
        const { data } = await api.post('/api/crons/', form);
        setEntries(prev => [...prev, data]);
        toast.success('Cron added');
      }
      setShowAdd(false);
      setEditingId(null);
      setForm({ schedule: '', command: '', comment: '' });
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Save failed');
    }
  };

  const openEdit = (entry) => {
    setForm({ schedule: entry.schedule, command: entry.command, comment: entry.comment || '' });
    setEditingId(entry.id);
    setShowAdd(true);
  };

  const userCrons = entries.filter(e => !isManaged(e.id));
  const autoCrons = entries.filter(e => isManaged(e.id));

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-brand/15 flex items-center justify-center">
            <Clock size={18} className="text-brand-light" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-ink-primary">Cron Jobs</h1>
            <p className="text-xs text-ink-muted">Manage scheduled tasks for backup, monitoring, and maintenance</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={loadCrons}
            className="p-2 rounded-lg text-ink-muted hover:text-ink-secondary hover:bg-panel-elevated transition-colors"
            title="Refresh"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={() => { setEditingId(null); setForm({ schedule: '', command: '', comment: '' }); setShowAdd(true); }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-light transition-colors"
          >
            <Plus size={15} /> Add Cron
          </button>
        </div>
      </div>

      {/* Auto-managed crons (from setup) */}
      {autoCrons.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Shield size={14} className="text-ok" />
            <h2 className="text-sm font-semibold text-ink-primary">Auto-Managed (Setup Wizard)</h2>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-ok/10 text-ok border border-ok/20">{autoCrons.length}</span>
          </div>
          <div className="space-y-1.5">
            {autoCrons.map(entry => (
              <CronRow key={entry.id} entry={entry} managed onToggle={handleToggle} onEdit={openEdit} />
            ))}
          </div>
        </div>
      )}

      {/* User crons */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Terminal size={14} className="text-brand-light" />
          <h2 className="text-sm font-semibold text-ink-primary">Custom Crons</h2>
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-brand/10 text-brand-light border border-brand/20">{userCrons.length}</span>
        </div>
        {loading ? (
          <div className="flex items-center justify-center py-12 text-ink-muted text-sm">
            <RefreshCw size={16} className="animate-spin mr-2" /> Loading crons…
          </div>
        ) : userCrons.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-ink-muted">
            <Clock size={32} className="mb-3 opacity-40" />
            <p className="text-sm">No custom cron jobs yet.</p>
            <button
              onClick={() => { setEditingId(null); setForm({ schedule: '', command: '', comment: '' }); setShowAdd(true); }}
              className="mt-2 text-xs text-brand-light hover:text-brand transition-colors"
            >
              Add your first cron
            </button>
          </div>
        ) : (
          <div className="space-y-1.5">
            {userCrons.map(entry => (
              <CronRow key={entry.id} entry={entry} onToggle={handleToggle} onEdit={openEdit} onDelete={handleDelete} />
            ))}
          </div>
        )}
      </div>

      {/* Add/Edit modal */}
      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-lg bg-panel-800 border border-panel-border rounded-2xl shadow-2xl overflow-hidden">
            <div className="px-5 py-4 border-b border-panel-border">
              <h3 className="font-semibold text-ink-primary">{editingId ? 'Edit Cron' : 'Add Cron'}</h3>
            </div>
            <div className="px-5 py-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-ink-muted mb-1">Schedule</label>
                <input
                  value={form.schedule}
                  onChange={e => setForm(f => ({ ...f, schedule: e.target.value }))}
                  placeholder="0 2 * * *  or  @daily"
                  className="w-full px-3 py-2 rounded-lg bg-panel-elevated border border-panel-border text-sm text-ink-primary placeholder:text-ink-faint focus:outline-none focus:border-brand/50 font-mono"
                />
                <p className="text-[10px] text-ink-faint mt-1">min hour dom mon dow — e.g. <code className="text-brand-light">0 2 * * *</code> = daily at 2 AM</p>
              </div>
              <div>
                <label className="block text-xs font-medium text-ink-muted mb-1">Command</label>
                <input
                  value={form.command}
                  onChange={e => setForm(f => ({ ...f, command: e.target.value }))}
                  placeholder="/opt/gnukontrolr/setup.sh cmd_backup"
                  className="w-full px-3 py-2 rounded-lg bg-panel-elevated border border-panel-border text-sm text-ink-primary placeholder:text-ink-faint focus:outline-none focus:border-brand/50 font-mono"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-ink-muted mb-1">Comment (optional)</label>
                <input
                  value={form.comment}
                  onChange={e => setForm(f => ({ ...f, comment: e.target.value }))}
                  placeholder="Daily backup cron"
                  className="w-full px-3 py-2 rounded-lg bg-panel-elevated border border-panel-border text-sm text-ink-primary placeholder:text-ink-faint focus:outline-none focus:border-brand/50"
                />
              </div>
            </div>
            <div className="px-5 py-3 border-t border-panel-border flex items-center justify-end gap-2">
              <button
                onClick={() => { setShowAdd(false); setEditingId(null); }}
                className="px-3 py-1.5 text-xs text-ink-muted hover:text-ink-secondary transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                className="px-4 py-1.5 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-light transition-colors"
              >
                {editingId ? 'Update' : 'Add Cron'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function CronRow({ entry, managed, onToggle, onEdit, onDelete }) {
  const [hover, setHover] = useState(false);

  return (
    <div
      className={`flex items-center gap-3 px-4 py-2.5 rounded-xl border transition-colors ${
        entry.enabled
          ? 'bg-panel-elevated border-panel-border'
          : 'bg-panel-800 border-panel-border/50 opacity-60'
      }`}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      {/* Toggle */}
      <button
        onClick={() => onToggle(entry)}
        className={`flex-shrink-0 transition-colors ${entry.enabled ? 'text-ok' : 'text-ink-faint hover:text-ink-muted'}`}
        title={entry.enabled ? 'Disable' : 'Enable'}
      >
        {entry.enabled ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
      </button>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className={`text-xs font-medium ${entry.enabled ? 'text-ink-primary' : 'text-ink-muted'}`}>
          {entry.comment || <span className="italic text-ink-faint">(no label)</span>}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="font-mono text-[11px] text-brand-light">{entry.schedule}</span>
          <span className="text-[10px] text-ink-faint hidden sm:inline">{fmtSchedule(entry.schedule)}</span>
        </div>
        <div className="font-mono text-[11px] text-ink-muted truncate mt-0.5">{entry.command}</div>
      </div>

      {/* Badges */}
      <div className="flex items-center gap-2 flex-shrink-0">
        {managed && (
          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-ok/10 text-ok border border-ok/20 uppercase tracking-wider font-semibold">
            Auto
          </span>
        )}
        {!entry.enabled && (
          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-warn/10 text-warn border border-warn/20 uppercase tracking-wider font-semibold">
            Paused
          </span>
        )}
      </div>

      {/* Actions */}
      {hover && !managed && (
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={() => onEdit(entry)}
            className="p-1.5 rounded-lg text-ink-muted hover:text-ink-secondary hover:bg-panel-border transition-colors"
            title="Edit"
          >
            <Edit3 size={13} />
          </button>
          <button
            onClick={() => onDelete(entry.id)}
            className="p-1.5 rounded-lg text-ink-muted hover:text-bad-light hover:bg-bad/10 transition-colors"
            title="Delete"
          >
            <Trash2 size={13} />
          </button>
        </div>
      )}
    </div>
  );
}
