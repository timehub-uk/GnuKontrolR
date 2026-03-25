import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../utils/api';
import { Server, Play, Square, RotateCcw, RefreshCw, ScrollText, Settings, AlertTriangle } from 'lucide-react';

const SERVICE_META = {
  traefik:  { label: 'Traefik',    desc: 'Edge router & SSL termination', icon: '🔀', configFile: '/etc/traefik/traefik.yml' },
  mysql:    { label: 'MySQL',      desc: 'Master database server',        icon: '🗄️', configFile: '/etc/mysql/my.cnf' },
  postgres: { label: 'PostgreSQL', desc: 'Panel metadata database',       icon: '🐘', configFile: '/var/lib/postgresql/data/postgresql.conf' },
  redis:    { label: 'Redis',      desc: 'In-memory cache & sessions',    icon: '⚡', configFile: '/usr/local/etc/redis/redis.conf' },
  postfix:  { label: 'Postfix',    desc: 'SMTP mail server',              icon: '📨', configFile: '/etc/postfix/main.cf' },
  dovecot:  { label: 'Dovecot',    desc: 'IMAP/POP3 mail server',        icon: '📥', configFile: '/etc/dovecot/dovecot.conf' },
  powerdns: { label: 'PowerDNS',   desc: 'Authoritative DNS server',      icon: '🌍', configFile: '/etc/powerdns/pdns.conf' },
};

const STATE_BADGE = {
  active:         'bg-ok/15 text-ok-light border border-ok/25',
  inactive:       'bg-bad/15 text-bad-light border border-bad/25',
  failed:         'bg-bad/15 text-bad-light border border-bad/25',
  restarting:     'bg-warn/15 text-warn-light border border-warn/25',
  'not installed':'bg-panel-elevated text-ink-muted border border-panel-border',
  unknown:        'bg-panel-elevated text-ink-muted border border-panel-border',
};

export default function ServicesPage() {
  const [services,    setServices]    = useState({});
  const [loading,     setLoading]     = useState(true);
  const [confirming,  setConfirming]  = useState(null); // { key, action }
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/server/services');
      setServices(data);
    } catch { setServices({}); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const control = async (key, action) => {
    if (action === 'stop' || action === 'restart') {
      setConfirming({ key, action });
      return;
    }
    await api.post(`/api/server/services/${key}/${action}`);
    setTimeout(load, 1200);
  };

  const confirmAction = async () => {
    if (!confirming) return;
    const { key, action } = confirming;
    setConfirming(null);
    await api.post(`/api/server/services/${key}/${action}`);
    setTimeout(load, 1200);
  };

  const stateClass = s => STATE_BADGE[s] ?? STATE_BADGE.unknown;

  return (
    <div className="space-y-5">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[20px] font-bold text-ink-primary flex items-center gap-2">
            <Server size={20} className="text-brand" /> Master Services
          </h1>
          <p className="text-[13px] text-ink-muted mt-0.5">
            Each service runs as its own Docker container on <code className="text-ink-secondary">webpanel_net</code>.
          </p>
        </div>
        <button onClick={load} disabled={loading} className="btn-ghost flex items-center gap-1.5 text-xs py-1.5 px-3">
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {/* Confirm modal */}
      {confirming && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-panel-card border border-panel-border rounded-xl p-6 max-w-sm w-full mx-4 space-y-4">
            <div className="flex items-center gap-2 text-warn-light">
              <AlertTriangle size={18} />
              <h3 className="font-semibold text-ink-primary capitalize">
                {confirming.action} {SERVICE_META[confirming.key]?.label}?
              </h3>
            </div>
            <p className="text-[13px] text-ink-secondary">
              {confirming.action === 'stop'
                ? 'Stopping this service will affect all customer containers that depend on it.'
                : 'The service will restart briefly, causing a short interruption.'}
            </p>
            <div className="flex gap-2 justify-end">
              <button className="btn-ghost text-sm py-1.5 px-4" onClick={() => setConfirming(null)}>Cancel</button>
              <button className="btn-danger text-sm py-1.5 px-4 capitalize" onClick={confirmAction}>
                {confirming.action}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Service grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Object.entries(SERVICE_META).map(([key, meta]) => {
          const state = services[key] || 'unknown';
          return (
            <div key={key} className="panel p-4 flex items-center gap-4">
              <div className="text-2xl">{meta.icon}</div>

              <div className="flex-1 min-w-0">
                <div className="font-semibold text-ink-primary text-[14px]">{meta.label}</div>
                <div className="text-[12px] text-ink-muted">{meta.desc}</div>
                <div className="mt-1.5">
                  <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${stateClass(state)}`}>
                    {loading ? '…' : state}
                  </span>
                </div>
              </div>

              {/* Action buttons */}
              <div className="flex items-center gap-0.5 flex-shrink-0">
                {/* Log */}
                <button
                  onClick={() => navigate(`/logs?source=${key}`)}
                  title="View logs"
                  className="flex items-center justify-center w-7 h-7 rounded-md text-ink-muted hover:text-brand-light hover:bg-brand/10 transition-colors"
                >
                  <ScrollText size={14} />
                </button>

                {/* Config */}
                <button
                  onClick={() => navigate(`/terminal?cmd=cat+${encodeURIComponent(meta.configFile)}`)}
                  title={`Config: ${meta.configFile}`}
                  className="flex items-center justify-center w-7 h-7 rounded-md text-ink-muted hover:text-warn-light hover:bg-warn/10 transition-colors"
                >
                  <Settings size={14} />
                </button>

                <div className="w-px h-5 bg-panel-border mx-1" />

                {/* Start */}
                <button
                  onClick={() => control(key, 'start')}
                  title="Start"
                  className="flex items-center justify-center w-7 h-7 rounded-md text-ink-muted hover:text-ok-light hover:bg-ok/10 transition-colors"
                >
                  <Play size={13} />
                </button>
                {/* Stop */}
                <button
                  onClick={() => control(key, 'stop')}
                  title="Stop"
                  className="flex items-center justify-center w-7 h-7 rounded-md text-ink-muted hover:text-warn-light hover:bg-warn/10 transition-colors"
                >
                  <Square size={13} />
                </button>
                {/* Restart */}
                <button
                  onClick={() => control(key, 'restart')}
                  title="Restart"
                  className="flex items-center justify-center w-7 h-7 rounded-md text-ink-muted hover:text-brand-light hover:bg-brand/10 transition-colors"
                >
                  <RotateCcw size={13} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
