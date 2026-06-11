import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../utils/api';
import {
  Server, Play, Square, RotateCcw, RefreshCw, ScrollText, Settings,
  AlertTriangle, Plus, ExternalLink, Trash2, X, Package,
} from 'lucide-react';

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

const CATEGORY_ICONS = {
  management:  '🛠️',
  storage:     '💾',
  automation:  '🤖',
  monitoring:  '📊',
  security:    '🔒',
  other:       '🧩',
};

export default function ServicesPage() {
  const [services,        setServices]        = useState({});
  const [secondary,       setSecondary]       = useState({});
  const [loading,         setLoading]         = useState(true);
  const [confirming,      setConfirming]      = useState(null); // { key, action, secondary? }
  const [showBrowse,      setShowBrowse]      = useState(false);
  const [catalogue,       setCatalogue]       = useState({});
  const [enablingKey,     setEnablingKey]     = useState(null);  // service key being enabled
  const [disableConfirm,  setDisableConfirm]  = useState(null);  // { key, name }
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/server/services');
      setServices(data);
    } catch { setServices({}); }
    try {
      const { data } = await api.get('/api/server/secondary');
      setSecondary(data);
    } catch { setSecondary({}); }
    try {
      const { data } = await api.get('/api/server/secondary/catalogue');
      setCatalogue(data);
    } catch { setCatalogue({}); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const control = async (key, action, isSecondary = false) => {
    if (action === 'stop' || action === 'restart' || (action === 'disable')) {
      if (action === 'disable') {
        setDisableConfirm({ key, name: secondary[key]?.name || key });
        return;
      }
      setConfirming({ key, action, secondary: isSecondary });
      return;
    }
    const base = isSecondary ? '/api/server/secondary' : '/api/server/services';
    await api.post(`${base}/${key}/${action}`);
    setTimeout(load, 1500);
  };

  const confirmAction = async () => {
    if (!confirming) return;
    const { key, action, secondary: isSec } = confirming;
    setConfirming(null);
    const base = isSec ? '/api/server/secondary' : '/api/server/services';
    await api.post(`${base}/${key}/${action}`);
    setTimeout(load, 1500);
  };

  const confirmDisable = async () => {
    if (!disableConfirm) return;
    const { key } = disableConfirm;
    setDisableConfirm(null);
    await api.post(`/api/server/secondary/${key}/disable`);
    setTimeout(load, 1500);
  };

  const stateClass = s => STATE_BADGE[s] ?? STATE_BADGE.unknown;

  const openCatalogue = async () => {
    try {
      const { data } = await api.get('/api/server/secondary/catalogue');
      setCatalogue(data);
    } catch {}
    setShowBrowse(true);
  };

  const beginEnable = async (key) => {
    setEnablingKey(key);
    setShowBrowse(false);
    // Fetch saved config if any
    try {
      const { data } = await api.get(`/api/server/secondary/${key}/config`);
      setConfigForm(data.saved_config || {});
      setConfigSchema(data.schema || []);
    } catch {
      const entry = catalogue[key];
      setConfigForm({});
      setConfigSchema(entry?.config_schema || []);
    }
  };

  // ── Config modal state ──────────────────────────────────────────────────
  const [configSchema,  setConfigSchema]  = useState([]);
  const [configForm,    setConfigForm]    = useState({});
  const [configLoading, setConfigLoading] = useState(false);
  const [configError,   setConfigError]   = useState('');

  const updateConfigField = (key, value) => {
    setConfigForm(prev => ({ ...prev, [key]: value }));
  };

  const submitEnable = async () => {
    if (!enablingKey) return;
    setConfigLoading(true);
    setConfigError('');
    try {
      await api.post(`/api/server/secondary/${enablingKey}/enable`, { config: configForm });
      setEnablingKey(null);
      setConfigForm({});
      setConfigSchema([]);
      setTimeout(load, 1500);
    } catch (err) {
      setConfigError(err?.response?.data?.detail || err?.message || 'Failed to enable service');
    }
    setConfigLoading(false);
  };

  // ── Determine the host address for the "Open" button ────────────────────
  const hostAddr = window.location.hostname;

  return (
    <div className="space-y-5">

      {/* =================================================================
          MASTER SERVICES
      ================================================================= */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[20px] font-bold text-ink-primary flex items-center gap-2">
            <Server size={20} className="text-brand" /> Infrastructure Services
          </h1>
          <p className="text-[13px] text-ink-muted mt-0.5">
            Core platform services. Each runs as its own Docker container on{' '}
            <code className="text-ink-secondary">webpanel_net</code>.
          </p>
        </div>
        <button onClick={load} disabled={loading} className="btn-ghost flex items-center gap-1.5 text-xs py-1.5 px-3">
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

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
              <div className="flex items-center gap-0.5 flex-shrink-0">
                <button onClick={() => navigate(`/logs?source=${key}`)}
                  title="View logs"
                  className="flex items-center justify-center w-7 h-7 rounded-md text-ink-muted hover:text-brand-light hover:bg-brand/10 transition-colors">
                  <ScrollText size={14} />
                </button>
                <button onClick={() => navigate(`/terminal?cmd=cat+${encodeURIComponent(meta.configFile)}`)}
                  title={`Config: ${meta.configFile}`}
                  className="flex items-center justify-center w-7 h-7 rounded-md text-ink-muted hover:text-warn-light hover:bg-warn/10 transition-colors">
                  <Settings size={14} />
                </button>
                <div className="w-px h-5 bg-panel-border mx-1" />
                <button onClick={() => control(key, 'start')} title="Start"
                  className="flex items-center justify-center w-7 h-7 rounded-md text-ok-light bg-ok/10 hover:bg-ok/20 transition-colors">
                  <Play size={13} />
                </button>
                <button onClick={() => control(key, 'stop')} title="Stop"
                  className="flex items-center justify-center w-7 h-7 rounded-md text-warn-light bg-warn/10 hover:bg-warn/20 transition-colors">
                  <Square size={13} />
                </button>
                <button onClick={() => control(key, 'restart')} title="Restart"
                  className="flex items-center justify-center w-7 h-7 rounded-md text-brand-light bg-brand/10 hover:bg-brand/20 transition-colors">
                  <RotateCcw size={13} />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* =================================================================
          DIVIDER
      ================================================================= */}
      <div className="relative py-2">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t border-panel-border" />
        </div>
      </div>

      {/* =================================================================
          OPTIONAL SERVICES
      ================================================================= */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-[18px] font-bold text-ink-primary flex items-center gap-2">
            <Package size={18} className="text-brand" /> Optional Services
          </h2>
          <p className="text-[13px] text-ink-muted mt-0.5">
            Add-on services you can enable on demand. Disabled by default to save resources.
          </p>
        </div>
        <button onClick={openCatalogue}
          className="btn-primary flex items-center gap-1.5 text-xs py-1.5 px-3">
          <Plus size={13} /> Browse
        </button>
      </div>

      {/* Optional services grid */}
      {Object.keys(secondary).length === 0 ? (
        <div className="panel p-8 text-center">
          <Package size={32} className="mx-auto text-ink-muted mb-2" />
          <p className="text-ink-secondary text-[14px]">No optional services enabled.</p>
          <p className="text-ink-muted text-[12px] mt-1">
            Click <strong>Browse</strong> to discover and enable add-on services.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Object.values(secondary).filter(s => s.enabled).map(svc => (
            <div key={svc.key} className="panel p-4 flex items-center gap-4">
              <div className="text-2xl">{svc.icon || '🧩'}</div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-ink-primary text-[14px]">{svc.name}</div>
                <div className="text-[12px] text-ink-muted">{svc.description}</div>
                <div className="mt-1.5 flex items-center gap-2">
                  <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${stateClass(svc.state)}`}>
                    {loading ? '…' : svc.state}
                  </span>
                  <span className="text-[10px] text-ink-muted">{svc.container_name}</span>
                </div>
              </div>
              <div className="flex items-center gap-0.5 flex-shrink-0">
                {/* Open web UI button */}
                {svc.web_port && (
                  <a
                    href={`https://${hostAddr}:${svc.web_port}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={`Open Web UI (port ${svc.web_port})`}
                    className="flex items-center justify-center w-7 h-7 rounded-md text-brand-light bg-brand/10 hover:bg-brand/20 transition-colors"
                  >
                    <ExternalLink size={13} />
                  </a>
                )}
                {/* Logs placeholder */}
                <button
                  onClick={() => navigate(`/logs?source=${svc.key}`)}
                  title="View logs"
                  className="flex items-center justify-center w-7 h-7 rounded-md text-ink-muted hover:text-brand-light hover:bg-brand/10 transition-colors"
                >
                  <ScrollText size={14} />
                </button>
                <div className="w-px h-5 bg-panel-border mx-1" />
                <button onClick={() => control(svc.key, 'start', true)} title="Start"
                  disabled={svc.state === 'active'}
                  className="flex items-center justify-center w-7 h-7 rounded-md text-ok-light bg-ok/10 hover:bg-ok/20 disabled:text-ink-muted disabled:bg-transparent transition-colors">
                  <Play size={13} />
                </button>
                <button onClick={() => control(svc.key, 'stop', true)} title="Stop"
                  disabled={svc.state === 'inactive'}
                  className="flex items-center justify-center w-7 h-7 rounded-md text-warn-light bg-warn/10 hover:bg-warn/20 disabled:text-ink-muted disabled:bg-transparent transition-colors">
                  <Square size={13} />
                </button>
                <button onClick={() => control(svc.key, 'restart', true)} title="Restart"
                  className="flex items-center justify-center w-7 h-7 rounded-md text-brand-light bg-brand/10 hover:bg-brand/20 transition-colors">
                  <RotateCcw size={13} />
                </button>
                <div className="w-px h-5 bg-panel-border mx-1" />
                <button onClick={() => control(svc.key, 'disable', true)} title="Disable & remove container"
                  className="flex items-center justify-center w-7 h-7 rounded-md text-bad-light bg-bad/10 hover:bg-bad/20 transition-colors">
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* =================================================================
          CONFIRM MODAL (master service stop/restart)
      ================================================================= */}
      {confirming && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-panel-card border border-panel-border rounded-xl p-6 max-w-sm w-full mx-4 space-y-4">
            <div className="flex items-center gap-2 text-warn-light">
              <AlertTriangle size={18} />
              <h3 className="font-semibold text-ink-primary capitalize">
                {confirming.action}{' '}
                {confirming.secondary
                  ? (secondary[confirming.key]?.name || confirming.key)
                  : (SERVICE_META[confirming.key]?.label || confirming.key)}?
              </h3>
            </div>
            <p className="text-[13px] text-ink-secondary">
              {confirming.action === 'stop'
                ? 'Stopping this service will affect anything that depends on it.'
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

      {/* =================================================================
          DISABLE CONFIRM MODAL (secondary service)
      ================================================================= */}
      {disableConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-panel-card border border-panel-border rounded-xl p-6 max-w-sm w-full mx-4 space-y-4">
            <div className="flex items-center gap-2 text-bad-light">
              <Trash2 size={18} />
              <h3 className="font-semibold text-ink-primary">
                Remove {disableConfirm.name}?
              </h3>
            </div>
            <p className="text-[13px] text-ink-secondary">
              This will stop and remove the container. All data in named volumes will be preserved,
              but the container will need to be re-created from scratch to re-enable it.
            </p>
            <div className="flex gap-2 justify-end">
              <button className="btn-ghost text-sm py-1.5 px-4" onClick={() => setDisableConfirm(null)}>Cancel</button>
              <button className="btn-danger text-sm py-1.5 px-4" onClick={confirmDisable}>Remove</button>
            </div>
          </div>
        </div>
      )}

      {/* =================================================================
          BROWSE CATALOGUE MODAL
      ================================================================= */}
      {showBrowse && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-panel-card border border-panel-border rounded-xl p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-ink-primary flex items-center gap-2">
                <Package size={18} className="text-brand" /> Available Optional Services
              </h2>
              <button onClick={() => setShowBrowse(false)}
                className="flex items-center justify-center w-7 h-7 rounded-md text-ink-muted hover:text-ink-primary hover:bg-panel-elevated transition-colors">
                <X size={16} />
              </button>
            </div>
            <p className="text-[13px] text-ink-secondary">
              Select a service to enable. You will be asked for configuration details (ports, passwords, etc.).
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {Object.values(catalogue).map(entry => {
                const isEnabled = secondary[entry.key]?.enabled;
                const catIcon = CATEGORY_ICONS[entry.category] || '🧩';
                return (
                  <div key={entry.key}
                    className={`border rounded-lg p-3 transition-colors ${
                      isEnabled
                        ? 'border-ok/30 bg-ok/5'
                        : 'border-panel-border hover:border-brand/30 hover:bg-brand/5'
                    }`}>
                    <div className="flex items-start gap-3">
                      <div className="text-2xl">{entry.icon || catIcon}</div>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-ink-primary text-[14px]">{entry.name}</div>
                        <div className="text-[11px] text-ink-muted mt-0.5 line-clamp-2">{entry.description}</div>
                        <div className="flex items-center gap-2 mt-1.5">
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-panel-elevated text-ink-muted">
                            {entry.category}
                          </span>
                          {isEnabled && (
                            <span className="text-[10px] text-ok-light">
                              ✓ Enabled (port {secondary[entry.key]?.web_port || '?'})
                            </span>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={() => isEnabled ? setShowBrowse(false) : beginEnable(entry.key)}
                        disabled={isEnabled}
                        className={`flex-shrink-0 text-xs py-1.5 px-3 rounded-lg font-medium transition-colors ${
                          isEnabled
                            ? 'bg-ok/10 text-ok-light cursor-default'
                            : 'bg-brand/10 text-brand-light hover:bg-brand/20'
                        }`}>
                        {isEnabled ? 'Enabled' : 'Enable'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            {Object.keys(catalogue).length === 0 && (
              <p className="text-center text-ink-muted py-4">Loading catalogue…</p>
            )}

            <div className="flex justify-end pt-2">
              <button className="btn-ghost text-sm py-1.5 px-4" onClick={() => setShowBrowse(false)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* =================================================================
          CONFIG MODAL (settings for enabling a secondary service)
      ================================================================= */}
      {enablingKey && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-panel-card border border-panel-border rounded-xl p-6 max-w-lg w-full mx-4 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-ink-primary flex items-center gap-2">
                {catalogue[enablingKey]?.icon || '🧩'} Configure {catalogue[enablingKey]?.name || enablingKey}
              </h3>
              <button onClick={() => { setEnablingKey(null); setConfigError(''); }}
                className="flex items-center justify-center w-7 h-7 rounded-md text-ink-muted hover:text-ink-primary hover:bg-panel-elevated transition-colors">
                <X size={16} />
              </button>
            </div>

            <p className="text-[13px] text-ink-secondary">
              {catalogue[enablingKey]?.description_full || catalogue[enablingKey]?.description || ''}
            </p>

            {configError && (
              <div className="bg-bad/10 border border-bad/25 rounded-lg p-3 text-[13px] text-bad-light">
                {configError}
              </div>
            )}

            <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
              {configSchema.map(field => (
                <div key={field.key}>
                  <label className="block text-[13px] font-medium text-ink-primary mb-1">
                    {field.label}
                    {field.required && <span className="text-bad-light ml-0.5">*</span>}
                  </label>
                  {field.type === 'password' ? (
                    <input
                      type="password"
                      value={configForm[field.key] || ''}
                      onChange={e => updateConfigField(field.key, e.target.value)}
                      placeholder={field.description || field.label}
                      className="w-full bg-panel-input border border-panel-border rounded-lg px-3 py-2 text-[13px] text-ink-primary placeholder:text-ink-muted focus:outline-none focus:border-brand/50"
                    />
                  ) : field.type === 'number' ? (
                    <input
                      type="number"
                      value={configForm[field.key] ?? field.default ?? ''}
                      onChange={e => updateConfigField(field.key, parseInt(e.target.value) || field.default)}
                      className="w-full bg-panel-input border border-panel-border rounded-lg px-3 py-2 text-[13px] text-ink-primary placeholder:text-ink-muted focus:outline-none focus:border-brand/50"
                    />
                  ) : (
                    <input
                      type="text"
                      value={configForm[field.key] ?? field.default ?? ''}
                      onChange={e => updateConfigField(field.key, e.target.value)}
                      placeholder={field.description || field.label}
                      className="w-full bg-panel-input border border-panel-border rounded-lg px-3 py-2 text-[13px] text-ink-primary placeholder:text-ink-muted focus:outline-none focus:border-brand/50"
                    />
                  )}
                  {field.description && (
                    <p className="text-[11px] text-ink-muted mt-0.5">{field.description}</p>
                  )}
                </div>
              ))}

              {configSchema.length === 0 && (
                <p className="text-[13px] text-ink-secondary">
                  No configuration needed. Click Enable to deploy.
                </p>
              )}

              {/* Summary of what will happen */}
              <div className="bg-panel-elevated rounded-lg p-3 text-[12px] text-ink-secondary space-y-1">
                <p className="font-medium text-ink-primary">Deployment summary</p>
                <p>• Docker image: <code className="text-ink-secondary">{catalogue[enablingKey]?.docker_image}</code></p>
                <p>• Container name: <code className="text-ink-secondary">
                  {catalogue[enablingKey]?.default_container_name || `webpanel_${enablingKey}`}
                </code></p>
                <p>• Network: <code className="text-ink-secondary">webpanel_net</code></p>
                <p>• Restart policy: <code className="text-ink-secondary">unless-stopped</code></p>
              </div>
            </div>

            <div className="flex gap-2 justify-end pt-2">
              <button className="btn-ghost text-sm py-1.5 px-4"
                onClick={() => { setEnablingKey(null); setConfigError(''); }}>
                Cancel
              </button>
              <button className="btn-primary text-sm py-1.5 px-4 flex items-center gap-1.5"
                disabled={configLoading}
                onClick={submitEnable}>
                {configLoading ? (
                  <RefreshCw size={13} className="animate-spin" />
                ) : (
                  <Play size={13} />
                )}
                {configLoading ? 'Deploying…' : 'Enable & Deploy'}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
