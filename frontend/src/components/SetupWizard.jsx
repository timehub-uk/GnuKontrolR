import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Shield, ShieldCheck, Globe, BarChart3, HardDrive,
  RefreshCw, Server, Check, ChevronRight, ChevronLeft,
  Sparkles, ExternalLink, Clock, Activity, Settings,
  Eye, Loader, XCircle, CheckCircle,
} from 'lucide-react';
import api from '../utils/api';
import { toast } from 'sonner';

const DIAGNOSTIC_ENDPOINTS = [
  { label: 'Auth / Session',    method: 'GET',  path: '/api/auth/me' },
  { label: 'User Profile',      method: 'GET',  path: '/api/users/me' },
  { label: 'Domains',           method: 'GET',  path: '/api/domains' },
  { label: 'Server Services',   method: 'GET',  path: '/api/server/services' },
  { label: 'Server Stats',      method: 'GET',  path: '/api/server/stats' },
  { label: 'Panel Config',      method: 'GET',  path: '/api/server/panel-config' },
  { label: 'Fail2ban Jails',    method: 'GET',  path: '/api/fail2ban/jails' },
  { label: 'Geo Countries',     method: 'GET',  path: '/api/geo/countries' },
  { label: 'Services Catalogue',method: 'GET',  path: '/api/services/catalogue' },
  { label: 'Notifications',     method: 'GET',  path: '/api/notifications' },
  { label: 'CVE Feed',          method: 'GET',  path: '/api/cve/recent?limit=1' },
  { label: 'DNS Sync Status',   method: 'GET',  path: '/api/dns-sync/status' },
  { label: 'Activity Log',      method: 'GET',  path: '/api/activity-log' },
  { label: 'Setup Status',      method: 'GET',  path: '/api/setup/status' },
];

const STEPS = [
  {
    id: 'secrets',
    icon: Shield,
    title: 'Change Default Secrets',
    description: 'Update the admin password and generate a new JWT signing key.',
    field: 'secrets_changed',
    interactive: true,
  },
  {
    id: 'fail2ban',
    icon: ShieldCheck,
    title: 'Enable Fail2ban Rules',
    description: 'Protect SSH, web panel, and mail services from brute-force attacks.',
    field: 'fail2ban_done',
    interactive: true,
  },
  {
    id: 'geo',
    icon: Globe,
    title: 'Configure Geo-Blocking',
    description: 'Restrict access by country to reduce attack surface.',
    field: 'geo_block_done',
    interactive: true,
  },
  {
    id: 'grafana',
    icon: BarChart3,
    title: 'Review Grafana Dashboards',
    description: 'Check system metrics, container resource usage, and DNS query patterns.',
    field: 'grafana_done',
    interactive: false,
    action: { label: 'Open Grafana', path: null, external: 'http://localhost:3001' },
  },
  {
    id: 'backup_cron',
    icon: HardDrive,
    title: 'Schedule Automated Backups',
    description: 'Daily backups — includes all site files, databases, DNS zones, and panel config.',
    field: 'backup_cron_set',
    hasToggle: true,
    interactive: true,
  },
  {
    id: 'cve_cron',
    icon: Activity,
    title: 'CVE Monitoring & Auto-Updates',
    description: 'Weekly CVE feed check and panel update check. Stay informed on threats.',
    field: 'cve_cron_set',
    hasToggle: true,
    interactive: true,
  },
  {
    id: 'services',
    icon: Server,
    title: 'Disable Unused Services',
    description: 'Review running services and disable anything you don\'t need.',
    field: 'services_pruned',
    interactive: true,
  },
];

function SecretsStep({ onDone, stepState, markStep }) {
  const [adminPassword, setAdminPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [jwtSecret, setJwtSecret] = useState('');
  const [saving, setSaving] = useState(false);
  const [animating, setAnimating] = useState(false);
  const [countdown, setCountdown] = useState(128);
  const [manualMode, setManualMode] = useState(false);

  const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-';

  const randomChar = () => chars[Math.floor(Math.random() * chars.length)];

  const randomString = (len) => {
    let s = '';
    for (let i = 0; i < len; i++) s += randomChar();
    return s;
  };

  const generateKey = () => {
    const len = 48;
    let s = '';
    for (let i = 0; i < len; i++) s += randomChar();
    setJwtSecret(s);
  };

  const startAnimation = () => {
    setAnimating(true);
    setCountdown(128);
    setJwtSecret(randomString(48));
  };

  useEffect(() => {
    if (!animating) return;
    const t = setTimeout(() => {
      if (countdown <= 0) {
        setAnimating(false);
        generateKey();
      } else {
        setCountdown(c => c - 0.5);
      }
    }, 500);
    return () => clearTimeout(t);
  }, [animating, countdown]);

  useEffect(() => {
    if (!animating) return;
    const r = setInterval(() => {
      setJwtSecret(randomString(48));
    }, 60);
    return () => clearInterval(r);
  }, [animating]);

  useEffect(() => { if (!jwtSecret) startAnimation(); }, []);

  const save = async () => {
    if (adminPassword && adminPassword !== confirmPassword) {
      toast.error('Passwords do not match');
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post('/api/setup/rotate-secrets', {
        new_secret_key: jwtSecret,
        new_password: adminPassword || undefined,
      });
      toast.success('Secrets updated. Panel will restart to apply the new JWT key.');
      await markStep('secrets_changed', true);
      onDone();
    } catch (err) {
      toast.error('Failed to update secrets: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-xs font-medium text-ink-muted mb-1">New Admin Password</label>
        <input
          className="input w-full text-sm"
          type="password"
          placeholder="Leave blank to keep current"
          value={adminPassword}
          onChange={e => setAdminPassword(e.target.value)}
        />
      </div>
      {adminPassword && (
        <div>
          <label className="block text-xs font-medium text-ink-muted mb-1">Confirm Password</label>
          <input
            className="input w-full text-sm"
            type="password"
            placeholder="Repeat new password"
            value={confirmPassword}
            onChange={e => setConfirmPassword(e.target.value)}
          />
        </div>
      )}
      <div>
        <div className="flex items-center justify-between mb-1">
          <label className="block text-xs font-medium text-ink-muted">JWT Secret Key</label>
          <div className="flex items-center gap-2">
            {animating && (
              <span className="text-xs text-brand-light font-mono tabular-nums">
                {Math.floor(countdown / 60)}:{(Math.ceil(countdown) % 60).toString().padStart(2, '0')}
              </span>
            )}
            <button
              onClick={() => { if (animating) { setAnimating(false); generateKey(); } else { startAnimation(); } }}
              className="text-xs text-brand-light hover:text-brand transition-colors"
            >
              {animating ? 'Stop' : 'Re-seed'}
            </button>
            <button
              onClick={() => setManualMode(m => !m)}
              className="text-xs text-ink-muted hover:text-ink-secondary transition-colors"
            >
              {manualMode ? 'Auto' : 'Manual'}
            </button>
          </div>
        </div>
        <div className="relative">
          <input
            className="input w-full text-sm font-mono"
            type="text"
            value={jwtSecret}
            onChange={e => { setManualMode(true); setAnimating(false); setJwtSecret(e.target.value); }}
            readOnly={animating}
          />
          {animating && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="flex items-center gap-1.5">
                <RefreshCw size={12} className="animate-spin text-brand-light" />
                <span className="text-xs text-brand-light font-mono">seeding entropy pool…</span>
              </div>
            </div>
          )}
        </div>
        <p className="text-[11px] text-ink-faint mt-1">
          A restart is required after changing. Existing sessions will be invalidated.
        </p>
      </div>
      <button
        onClick={save}
        disabled={saving || (!!adminPassword && adminPassword !== confirmPassword)}
        className="btn-primary text-sm disabled:opacity-50"
      >
        {saving ? 'Saving…' : 'Apply Secrets'}
      </button>
      {stepState?.secrets_changed && (
        <div className="flex items-center gap-2 text-ok text-sm">
          <Check size={14} /> Secrets updated
        </div>
      )}
    </div>
  );
}

function Fail2banStep({ onDone, markStep }) {
  const [jails, setJails] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(null);

  const load = async () => {
    try {
      const { data } = await api.get('/api/fail2ban/jails');
      setJails(data.jails || []);
      if ((data.jails || []).every(j => j.enabled)) {
        await markStep('fail2ban_done', true);
      }
    } catch {
      setJails([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggle = async (jail, enable) => {
    setToggling(jail.id);
    try {
      await api.patch(`/api/fail2ban/jails/${jail.id}`, { enabled: enable });
      setJails(prev => prev.map(j => j.id === jail.id ? { ...j, enabled: enable } : j));
      if (enable && jails.every(j => j.id === jail.id ? enable : j.enabled)) {
        await markStep('fail2ban_done', true);
      }
    } catch {
      toast.error(`Failed to ${enable ? 'enable' : 'disable'} ${jail.name}`);
    } finally {
      setToggling(null);
    }
  };

  if (loading) return <div className="flex items-center gap-2 text-sm text-ink-muted"><Loader size={14} className="animate-spin" /> Loading jails…</div>;

  return (
    <div className="space-y-2">
      {jails.length === 0 && (
        <p className="text-sm text-ink-muted">No fail2ban jails found. Install fail2ban first.</p>
      )}
      {jails.map(jail => (
        <div key={jail.id} className="flex items-center justify-between py-2 px-3 rounded-lg bg-panel-elevated">
          <div>
            <span className="text-sm font-medium text-ink-primary">{jail.name}</span>
            <span className="text-xs text-ink-faint ml-2">{jail.port ? `port ${jail.port}` : ''}</span>
          </div>
          <button
            onClick={() => toggle(jail, !jail.enabled)}
            disabled={toggling === jail.id}
            className={`relative w-10 h-5 rounded-full transition-colors ${
              jail.enabled ? 'bg-ok' : 'bg-panel-border'
            }`}
          >
            <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
              jail.enabled ? 'translate-x-5' : ''
            }`} />
          </button>
        </div>
      ))}
      {jails.length > 0 && jails.every(j => j.enabled) && (
        <div className="flex items-center gap-2 text-ok text-sm pt-2">
          <Check size={14} /> All jails enabled
        </div>
      )}
    </div>
  );
}

function GeoStep({ onDone, markStep }) {
  const [countries, setCountries] = useState([]);
  const [blocked, setBlocked] = useState({});
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(null);
  const [filter, setFilter] = useState('');

  const load = async () => {
    try {
      const [geoRes, blockRes] = await Promise.all([
        api.get('/api/geo/countries'),
        api.get('/api/fail2ban/geo-blocks'),
      ]);
      const all = geoRes.data?.countries || geoRes.data || [];
      const blocks = {};
      (blockRes.data?.blocks || blockRes.data || []).forEach(b => { blocks[b.country_code] = b.blocked; });
      setCountries(all);
      setBlocked(blocks);
    } catch {
      setCountries([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggle = async (cc, name, block) => {
    setToggling(cc);
    try {
      await api.post('/api/fail2ban/geo-blocks', { country_code: cc, country_name: name, blocked: block });
      setBlocked(prev => ({ ...prev, [cc]: block }));
      await api.post('/api/fail2ban/geo-blocks/apply-all');
      await markStep('geo_block_done', true);
    } catch {
      toast.error(`Failed to ${block ? 'block' : 'unblock'} ${name}`);
    } finally {
      setToggling(null);
    }
  };

  if (loading) return <div className="flex items-center gap-2 text-sm text-ink-muted"><Loader size={14} className="animate-spin" /> Loading countries…</div>;

  const filtered = filter
    ? countries.filter(c => c.name?.toLowerCase().includes(filter.toLowerCase()) || c.code?.toLowerCase().includes(filter.toLowerCase()))
    : countries;

  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-muted">Tap a country to block or unblock it. Blocked countries are denied at the firewall level.</p>
      <input
        className="input w-full text-sm"
        type="text"
        placeholder="Search countries…"
        value={filter}
        onChange={e => setFilter(e.target.value)}
      />
      <div className="max-h-48 overflow-y-auto space-y-1 pr-1">
        {filtered.map(c => (
          <div key={c.code} className="flex items-center justify-between py-1.5 px-3 rounded-lg hover:bg-panel-elevated transition-colors">
            <span className="text-sm text-ink-primary">{c.name} <span className="text-ink-faint">{c.code}</span></span>
            <button
              onClick={() => toggle(c.code, c.name, !blocked[c.code])}
              disabled={toggling === c.code}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                blocked[c.code]
                  ? 'bg-bad/15 text-bad-light border-bad/30'
                  : 'bg-panel-elevated text-ink-muted border-panel-border hover:text-ink-primary'
              }`}
            >
              {blocked[c.code] ? 'Blocked' : 'Allow'}
            </button>
          </div>
        ))}
      </div>
      {Object.keys(blocked).length > 0 && (
        <div className="flex items-center gap-2 text-ok text-sm">
          <Check size={14} /> {Object.keys(blocked).length} countr{Object.keys(blocked).length === 1 ? 'y' : 'ies'} blocked
        </div>
      )}
    </div>
  );
}

function ServicesStep({ onDone, markStep }) {
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(null);

  const load = async () => {
    try {
      const { data } = await api.get('/api/server/services');
      const list = Object.entries(data || {}).map(([name, info]) => ({
        name,
        running: info?.running ?? info?.status === 'running',
        status: info?.status || 'unknown',
      }));
      setServices(list);
    } catch {
      setServices([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggle = async (svc, start) => {
    setToggling(svc);
    try {
      await api.post(`/api/server/services/${svc}/${start ? 'start' : 'stop'}`);
      setServices(prev => prev.map(s => s.name === svc ? { ...s, running: start, status: start ? 'running' : 'stopped' } : s));
      if (!start) await markStep('services_pruned', true);
    } catch {
      toast.error(`Failed to ${start ? 'start' : 'stop'} ${svc}`);
    } finally {
      setToggling(null);
    }
  };

  if (loading) return <div className="flex items-center gap-2 text-sm text-ink-muted"><Loader size={14} className="animate-spin" /> Loading services…</div>;

  return (
    <div className="space-y-2">
      <p className="text-xs text-ink-muted">Stop services you don't need to reduce resource usage and attack surface.</p>
      {services.map(svc => (
        <div key={svc.name} className="flex items-center justify-between py-2 px-3 rounded-lg bg-panel-elevated">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${svc.running ? 'bg-ok' : 'bg-ink-faint'}`} />
            <span className="text-sm font-medium text-ink-primary capitalize">{svc.name}</span>
            <span className="text-xs text-ink-faint">{svc.status}</span>
          </div>
          <button
            onClick={() => toggle(svc.name, !svc.running)}
            disabled={toggling === svc.name}
            className={`relative w-10 h-5 rounded-full transition-colors ${
              svc.running ? 'bg-ok' : 'bg-panel-border'
            }`}
          >
            <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
              svc.running ? 'translate-x-5' : ''
            }`} />
          </button>
        </div>
      ))}
      {services.filter(s => !s.running).length > 0 && (
        <div className="flex items-center gap-2 text-ok text-sm pt-2">
          <Check size={14} /> {services.filter(s => !s.running).length} service{services.filter(s => !s.running).length === 1 ? '' : 's'} disabled
        </div>
      )}
    </div>
  );
}

export default function SetupWizard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);
  const [completed, setCompleted] = useState(false);
  const [stepState, setStepState] = useState({});
  const [creatingCrons, setCreatingCrons] = useState(false);
  const [diagnosticResults, setDiagnosticResults] = useState(null);
  const [runningDiag, setRunningDiag] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get('/api/setup/status');
        if (!data.completed) {
          setStep(data.step_index || 0);
          setStepState(data.steps || {});
          setVisible(true);
        }
      } catch {
        // non-fatal
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const markStep = async (field, value = true) => {
    try {
      await api.post('/api/setup/step', { field, value, step_index: step });
      setStepState(prev => ({ ...prev, [field]: value }));
    } catch { /* non-fatal */ }
  };

  const totalSteps = STEPS.length;

  const isStepDone = (idx) => {
    const s = STEPS[idx];
    if (s.hasToggle) return stepState[s.field] === true;
    return stepState[s.field] === true;
  };

  const nextStep = () => {
    if (step < totalSteps - 1) setStep(s => s + 1);
  };

  const prevStep = () => {
    if (step > 0) setStep(s => s - 1);
  };

  const skipStep = async () => {
    await markStep(STEPS[step].field, false);
    nextStep();
  };

  const handleAction = (s) => {
    if (s.action?.path) {
      navigate(s.action.path);
    } else if (s.action?.external) {
      window.open(s.action.external, '_blank', 'noopener');
    }
  };

  const runDiagnostics = async () => {
    setRunningDiag(true);
    setDiagnosticResults(DIAGNOSTIC_ENDPOINTS.map(e => ({ ...e, status: 'pending', statusCode: null })));
    const results = [];
    for (const ep of DIAGNOSTIC_ENDPOINTS) {
      try {
        const res = await api({ method: ep.method, url: ep.path, timeout: 8000 });
        results.push({ ...ep, status: 'ok', statusCode: res.status });
      } catch (err) {
        const code = err?.response?.status || 0;
        results.push({ ...ep, status: 'fail', statusCode: code, error: err.message });
      }
      setDiagnosticResults([...results]);
    }
    setRunningDiag(false);
    return results;
  };

  const handleFinish = async () => {
    // Run diagnostics first
    if (!diagnosticResults) {
      await runDiagnostics();
      return;
    }
    setCreatingCrons(true);
    try {
      await api.post('/api/setup/crons', {
        backup: stepState.backup_cron_set || false,
        cve: stepState.cve_cron_set || false,
        update: stepState.cve_cron_set || false,
      });
      await api.post('/api/setup/complete');
      toast.success('Setup complete!');
      setCompleted(true);
      setTimeout(() => setVisible(false), 500);
    } catch (err) {
      toast.error('Failed to finalize setup: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setCreatingCrons(false);
    }
  };

  const allDiagOk = diagnosticResults && diagnosticResults.every(r => r.status === 'ok');

  const current = STEPS[step];
  const progress = ((step + 1) / totalSteps) * 100;

  if (!visible || completed) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl bg-panel-800 border border-panel-border rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-panel-border">
          <div className="flex items-center gap-3 mb-1">
            <div className="w-9 h-9 rounded-xl bg-brand/15 flex items-center justify-center">
              <Sparkles size={18} className="text-brand-light" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-ink-primary">Welcome to GnuKontrolR</h2>
              <p className="text-xs text-ink-muted">Let's get your panel set up securely in a few steps</p>
            </div>
          </div>
          <div className="mt-4 w-full h-1 bg-panel-border rounded-full overflow-hidden">
            <div
              className="h-full bg-brand rounded-full transition-all duration-400 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex justify-between mt-1.5 text-[10px] text-ink-faint">
            <span>Step {step + 1} of {totalSteps}</span>
            <span>{Math.round(progress)}%</span>
          </div>
        </div>

        {/* Body */}
        <div className="px-6 py-6 min-h-[260px]">
          {diagnosticResults ? (
            /* ── Diagnostic report ── */
            <div className="space-y-3">
              <div className="flex items-center gap-2 mb-1">
                <CheckCircle size={16} className={allDiagOk ? 'text-ok' : 'text-yellow-400'} />
                <h3 className="text-base font-semibold text-ink-primary">API Diagnostics</h3>
                <span className="text-xs text-ink-faint">
                  {diagnosticResults.filter(r => r.status === 'ok').length}/{diagnosticResults.length} passed
                </span>
              </div>
              <div className="max-h-64 overflow-y-auto space-y-1 pr-1">
                {diagnosticResults.map((ep, idx) => (
                  <div key={idx} className="flex items-center justify-between py-1.5 px-3 rounded-lg bg-panel-elevated">
                    <div className="flex items-center gap-2">
                      {ep.status === 'pending' ? (
                        <Loader size={12} className="animate-spin text-ink-muted" />
                      ) : ep.status === 'ok' ? (
                        <CheckCircle size={12} className="text-ok" />
                      ) : (
                        <XCircle size={12} className="text-bad-light" />
                      )}
                      <span className="text-sm text-ink-primary">{ep.label}</span>
                      <span className="text-[10px] text-ink-faint font-mono">{ep.method} {ep.path}</span>
                    </div>
                    <span className={`text-xs font-mono ${
                      ep.status === 'pending' ? 'text-ink-faint' :
                      ep.status === 'ok' ? 'text-ok' : 'text-bad-light'
                    }`}>
                      {ep.status === 'pending' ? '…' :
                       ep.status === 'ok' ? `[OK] ${ep.statusCode}` :
                       `[FAIL] ${ep.statusCode || ''}`}
                    </span>
                  </div>
                ))}
              </div>
              {!allDiagOk && !runningDiag && (
                <p className="text-xs text-yellow-400">
                  Some endpoints returned errors. The panel may still function — you can proceed or investigate later.
                </p>
              )}
            </div>
          ) : (
            /* ── Normal step content ── */
            <>
            <div className="flex items-start gap-4 mb-4">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
                isStepDone(step) ? 'bg-ok/15' : 'bg-panel-elevated'
              }`}>
                <current.icon
                  size={20}
                  className={isStepDone(step) ? 'text-ok' : 'text-brand-light'}
                />
              </div>
              <div className="flex-1">
                <h3 className="text-base font-semibold text-ink-primary mb-1">{current.title}</h3>
                <p className="text-sm text-ink-muted leading-relaxed">{current.description}</p>
              </div>
              {isStepDone(step) && (
                <div className="w-6 h-6 rounded-full bg-ok/15 flex items-center justify-center flex-shrink-0">
                  <Check size={14} className="text-ok" />
                </div>
              )}
            </div>

            <div className="mt-4 pl-14">
              {current.id === 'secrets' && (
                <SecretsStep onDone={nextStep} stepState={stepState} markStep={markStep} />
              )}

              {current.id === 'fail2ban' && (
                <Fail2banStep onDone={nextStep} markStep={markStep} />
              )}

              {current.id === 'geo' && (
                <GeoStep onDone={nextStep} markStep={markStep} />
              )}

              {current.id === 'grafana' && !isStepDone(step) && (
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => handleAction(current)}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-light transition-colors"
                  >
                    Open Grafana <ExternalLink size={14} />
                  </button>
                  <button
                    onClick={async () => { await markStep(current.field, true); nextStep(); }}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-panel-elevated text-ink-primary text-sm font-medium hover:bg-panel-border transition-colors"
                  >
                    <Eye size={14} /> Mark as Reviewed
                  </button>
                </div>
              )}

              {current.id === 'backup_cron' && (
                <div className="flex items-center gap-3">
                  <button
                    onClick={async () => {
                      await markStep(current.field, true);
                      setStepState(prev => ({ ...prev, [current.field]: true }));
                    }}
                    disabled={stepState[current.field]}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                      stepState[current.field]
                        ? 'bg-ok/15 text-ok cursor-default'
                        : 'bg-brand text-white hover:bg-brand-light'
                    }`}
                  >
                    {stepState[current.field] ? (
                      <span className="flex items-center gap-2"><Check size={14} /> Backup Cron Enabled</span>
                    ) : (
                      <span className="flex items-center gap-2"><Clock size={14} /> Enable Daily Backups (2 AM)</span>
                    )}
                  </button>
                  <span className="text-xs text-ink-faint">
                    Creates a system crontab entry for daily backups
                  </span>
                </div>
              )}

              {current.id === 'cve_cron' && (
                <div className="flex items-center gap-3">
                  <button
                    onClick={async () => {
                      await markStep(current.field, true);
                      setStepState(prev => ({ ...prev, [current.field]: true }));
                    }}
                    disabled={stepState[current.field]}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                      stepState[current.field]
                        ? 'bg-ok/15 text-ok cursor-default'
                        : 'bg-brand text-white hover:bg-brand-light'
                    }`}
                  >
                    {stepState[current.field] ? (
                      <span className="flex items-center gap-2"><Check size={14} /> CVE Monitoring Enabled</span>
                    ) : (
                      <span className="flex items-center gap-2"><Activity size={14} /> Enable CVE Monitoring</span>
                    )}
                  </button>
                  <span className="text-xs text-ink-faint">
                    Weekly CVE + update checks
                  </span>
                </div>
              )}

              {current.id === 'services' && (
                <ServicesStep onDone={nextStep} markStep={markStep} />
              )}

              {isStepDone(step) && !current.interactive && current.id !== 'grafana' && (
                <div className="flex items-center gap-2 text-ok text-sm">
                  <Check size={14} />
                  <span>Completed</span>
                </div>
              )}
            </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-panel-border flex items-center justify-between">
          <div className="flex gap-2">
            {diagnosticResults ? (
              <div className="flex items-center gap-2 text-xs text-ink-faint">
                <span>{runningDiag ? 'Running…' : 'Done'}</span>
                <span className={`font-mono ${allDiagOk ? 'text-ok' : 'text-yellow-400'}`}>
                  {diagnosticResults.filter(r => r.status === 'ok').length}/{diagnosticResults.length}
                </span>
              </div>
            ) : (
              STEPS.map((_, idx) => (
                <div
                  key={idx}
                  className={`w-2 h-2 rounded-full transition-colors ${
                    idx === step
                      ? 'bg-brand'
                      : isStepDone(idx)
                      ? 'bg-ok'
                      : 'bg-panel-border'
                  }`}
                />
              ))
            )}
          </div>

          <div className="flex items-center gap-2">
            {diagnosticResults ? (
              <button
                onClick={handleFinish}
                disabled={creatingCrons}
                className="inline-flex items-center gap-2 px-5 py-2 rounded-lg bg-ok text-white text-sm font-medium hover:bg-ok/90 transition-colors disabled:opacity-50"
              >
                {creatingCrons ? (
                  <><RefreshCw size={14} className="animate-spin" /> Finalizing…</>
                ) : (
                  <><Sparkles size={14} /> Finalize Setup</>
                )}
              </button>
            ) : step < totalSteps - 1 ? (
              <>
                {current.interactive ? (
                  <button
                    onClick={skipStep}
                    className="px-3 py-1.5 text-xs text-ink-muted hover:text-ink-secondary transition-colors"
                  >
                    Skip
                  </button>
                ) : (
                  <button
                    onClick={nextStep}
                    className="inline-flex items-center gap-1 px-4 py-1.5 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-light transition-colors"
                  >
                    Next <ChevronRight size={14} />
                  </button>
                )}
              </>
            ) : (
              <button
                onClick={handleFinish}
                disabled={runningDiag || creatingCrons}
                className="inline-flex items-center gap-2 px-5 py-2 rounded-lg bg-ok text-white text-sm font-medium hover:bg-ok/90 transition-colors disabled:opacity-50"
              >
                {runningDiag ? (
                  <><Loader size={14} className="animate-spin" /> Running diagnostics…</>
                ) : creatingCrons ? (
                  <><RefreshCw size={14} className="animate-spin" /> Finalizing…</>
                ) : (
                  <><Sparkles size={14} /> Run Diagnostics &amp; Complete</>
                )}
              </button>
            )}

            {!diagnosticResults && step > 0 && (
              <button
                onClick={prevStep}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs text-ink-muted hover:text-ink-secondary transition-colors"
              >
                <ChevronLeft size={14} /> Back
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
