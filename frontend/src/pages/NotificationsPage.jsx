import { useState, useEffect, useCallback } from 'react';
import { Bell, CheckCheck, Trash2, X, RefreshCw, Globe, Users, Package, Info } from 'lucide-react';
import api from '../utils/api';
import { toast } from '../utils/toast';

// ── Icon by notification type ─────────────────────────────────────────────────
const TYPE_META = {
  domain_created:   { icon: Globe,    label: 'Domain',  color: 'text-brand',    bg: 'bg-brand/15'    },
  user_registered:  { icon: Users,    label: 'User',    color: 'text-ok',       bg: 'bg-ok/15'       },
  app_installed:    { icon: Package,  label: 'App',     color: 'text-warn',     bg: 'bg-warn/15'     },
};
function typeMeta(type) {
  return TYPE_META[type] ?? { icon: Info, label: 'Event', color: 'text-ink-muted', bg: 'bg-panel-elevated' };
}

// ── Detail card modal ─────────────────────────────────────────────────────────
function DetailCard({ notif, onClose, onRead }) {
  const { icon: Icon, color, bg } = typeMeta(notif.type);
  const ts = notif.created_at
    ? new Date(notif.created_at + 'Z').toLocaleString()
    : '—';

  useEffect(() => {
    if (!notif.is_read) onRead(notif.id);
  }, [notif.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-panel-card border border-panel-subtle rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
        {/* Header */}
        <div className="flex items-start gap-3 p-5 border-b border-panel-subtle">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${bg}`}>
            <Icon size={18} className={color} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-semibold text-ink-primary leading-snug">{notif.title}</div>
            <div className="text-[11px] text-ink-muted mt-0.5">{ts}</div>
          </div>
          <button
            onClick={onClose}
            className="text-ink-faint hover:text-ink-primary transition-colors flex-shrink-0 p-0.5"
          >
            <X size={16} />
          </button>
        </div>

        {/* Message */}
        <div className="px-5 pt-4 pb-3">
          <p className="text-[13px] text-ink-secondary leading-relaxed">{notif.message}</p>
        </div>

        {/* Details table */}
        {Object.keys(notif.details || {}).length > 0 && (
          <div className="px-5 pb-5">
            <div className="rounded-xl border border-panel-subtle overflow-hidden mt-2">
              <table className="w-full text-[12px]">
                <tbody>
                  {Object.entries(notif.details).map(([k, v], i) => (
                    <tr key={k} className={i % 2 === 0 ? 'bg-panel-elevated/40' : ''}>
                      <td className="px-3 py-2 text-ink-muted font-medium whitespace-nowrap w-1/3">{k}</td>
                      <td className="px-3 py-2 text-ink-primary break-all">{String(v)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="px-5 pb-4 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-panel-elevated hover:bg-panel-subtle text-ink-secondary text-[12px] rounded-lg transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function NotificationsPage() {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading]             = useState(true);
  const [selected, setSelected]           = useState(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get('/api/notifications');
      setNotifications(data);
    } catch {
      toast.error('Failed to load notifications');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const markRead = useCallback(async (id) => {
    await api.post(`/api/notifications/${id}/read`).catch(() => {});
    setNotifications(prev =>
      prev.map(n => n.id === id ? { ...n, is_read: true } : n)
    );
  }, []);

  const markAllRead = async () => {
    await api.post('/api/notifications/read-all').catch(() => {});
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
    toast.success('All marked as read');
  };

  const deleteOne = async (id, e) => {
    e.stopPropagation();
    await api.delete(`/api/notifications/${id}`).catch(() => {});
    setNotifications(prev => prev.filter(n => n.id !== id));
    if (selected?.id === id) setSelected(null);
  };

  const clearAll = async () => {
    if (!window.confirm('Delete all notifications?')) return;
    await api.delete('/api/notifications').catch(() => {});
    setNotifications([]);
    toast.success('All notifications cleared');
  };

  const unread = notifications.filter(n => !n.is_read).length;

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-brand/15 flex items-center justify-center">
            <Bell size={18} className="text-brand" />
          </div>
          <div>
            <h1 className="text-[17px] font-bold text-ink-primary">Notifications</h1>
            <p className="text-[11px] text-ink-muted">
              {unread > 0 ? `${unread} unread` : 'All caught up'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="p-2 rounded-lg text-ink-muted hover:text-ink-primary hover:bg-panel-elevated transition-colors"
            title="Refresh"
          >
            <RefreshCw size={14} />
          </button>
          {unread > 0 && (
            <button
              onClick={markAllRead}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-panel-elevated hover:bg-panel-subtle text-ink-secondary text-[12px] transition-colors"
            >
              <CheckCheck size={13} />
              Mark all read
            </button>
          )}
          {notifications.length > 0 && (
            <button
              onClick={clearAll}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-bad/10 hover:bg-bad/20 text-bad-light text-[12px] transition-colors"
            >
              <Trash2 size={13} />
              Clear all
            </button>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="bg-panel-card border border-panel-subtle rounded-2xl overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-6 h-6 border-2 border-brand border-t-transparent rounded-full animate-spin" />
          </div>
        ) : notifications.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <Bell size={32} className="text-ink-faint" />
            <p className="text-[13px] text-ink-muted">No notifications yet</p>
          </div>
        ) : (
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-panel-subtle">
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-ink-faint w-8" />
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">Event</th>
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-ink-faint hidden sm:table-cell">Message</th>
                <th className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-ink-faint hidden md:table-cell">Time</th>
                <th className="px-4 py-2.5 w-8" />
              </tr>
            </thead>
            <tbody>
              {notifications.map((n, idx) => {
                const { icon: Icon, color, bg, label } = typeMeta(n.type);
                const ts = n.created_at
                  ? new Date(n.created_at + 'Z').toLocaleString()
                  : '—';
                const isEven = idx % 2 === 0;
                return (
                  <tr
                    key={n.id}
                    onClick={() => setSelected(n)}
                    className={`
                      cursor-pointer border-b border-panel-subtle last:border-0 transition-colors
                      hover:bg-brand/5
                      ${isEven ? 'bg-panel-elevated/20' : 'bg-transparent'}
                      ${!n.is_read ? 'border-l-2 border-l-brand' : ''}
                    `}
                  >
                    {/* Unread dot */}
                    <td className="px-3 py-3">
                      {!n.is_read && (
                        <span className="w-2 h-2 rounded-full bg-brand inline-block animate-pulse" />
                      )}
                    </td>

                    {/* Type badge + title */}
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${bg}`}>
                          <Icon size={13} className={color} />
                        </div>
                        <div>
                          <div className={`font-medium leading-snug ${!n.is_read ? 'text-ink-primary' : 'text-ink-secondary'}`}>
                            {n.title}
                          </div>
                          <div className="text-[10px] text-ink-faint capitalize">{label}</div>
                        </div>
                      </div>
                    </td>

                    {/* Message preview */}
                    <td className="px-4 py-3 hidden sm:table-cell">
                      <span className="text-ink-muted text-[12px] line-clamp-1">{n.message}</span>
                    </td>

                    {/* Timestamp */}
                    <td className="px-4 py-3 hidden md:table-cell">
                      <span className="text-ink-faint text-[11px] whitespace-nowrap">{ts}</span>
                    </td>

                    {/* Delete */}
                    <td className="px-3 py-3">
                      <button
                        onClick={e => deleteOne(n.id, e)}
                        className="p-1 rounded text-ink-faint hover:text-bad-light hover:bg-bad/10 transition-colors opacity-0 group-hover:opacity-100"
                        title="Delete"
                      >
                        <X size={12} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Detail modal */}
      {selected && (
        <DetailCard
          notif={selected}
          onClose={() => setSelected(null)}
          onRead={markRead}
        />
      )}
    </div>
  );
}
