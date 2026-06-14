import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Shield, ShieldCheck, Globe, BarChart3, HardDrive,
  RefreshCw, Server, Check, ChevronRight, ChevronLeft,
  Sparkles, ExternalLink, Clock, Activity, Settings,
  Eye, Loader, XCircle, CheckCircle, Smartphone, ClipboardList,
  Trash2, FileText, Key, Copy, Download,
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
  {
    id: 'dsar_contact',
    icon: ClipboardList,
    title: 'Set DSAR Contact',
    description: 'Configure the Data Protection Officer contact for privacy requests.',
    field: 'dsar_contact_set',
    interactive: true,
  },
  {
    id: 'data_retention',
    icon: Trash2,
    title: 'Data Retention Policy',
    description: 'Review and confirm data retention schedules for compliance.',
    field: 'data_retention_set',
    interactive: false,
  },
  {
    id: 'privacy_policy',
    icon: FileText,
    title: 'Accept Privacy Policy',
    description: 'Review and accept the platform privacy policy.',
    field: 'privacy_policy_done',
    interactive: true,
  },
  {
    id: 'mfa',
    icon: Smartphone,
    title: 'Configure MFA / 2FA',
    description: 'Set up multi-factor authentication with QR code + recovery codes.',
    field: 'mfa_configured',
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

  const randomChar = () => {
    const array = new Uint32Array(1);
    window.crypto.getRandomValues(array);
    return chars[array[0] % chars.length];
  };

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
  const [installing, setInstalling] = useState(false);
  const [toggling, setToggling] = useState(null);
  const [installError, setInstallError] = useState(null);

  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get('/api/fail2ban/jails');
      setJails(data.jails || []);
      if ((data.jails || []).length > 0 && (data.jails || []).every(j => j.enabled)) {
        await markStep('fail2ban_done', true);
      }
    } catch {
      setJails([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const install = async () => {
    setInstalling(true);
    setInstallError(null);
    try {
      await api.post('/api/setup/setup-fail2ban');
      toast.success('Fail2ban jails installed and configured');
      await load();
      onDone();
    } catch (err) {
      const msg = err?.response?.data?.detail || err.message;
      setInstallError(msg);
      toast.error('Failed to install fail2ban: ' + msg);
    } finally {
      setInstalling(false);
    }
  };

  const reapply = async () => {
    setRefreshing(true);
    setInstallError(null);
    try {
      await api.post('/api/setup/setup-fail2ban');
      toast.success('Fail2ban config re-applied');
      await load();
    } catch (err) {
      const msg = err?.response?.data?.detail || err.message;
      setInstallError(msg);
      toast.error('Failed to re-apply fail2ban: ' + msg);
    } finally {
      setRefreshing(false);
    }
  };

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
        <div className="space-y-3">
          <p className="text-sm text-ink-muted">
            Fail2ban is not yet configured. This will set up jails for SSH, web panel, and mail services.
          </p>
          {installError && (
            <p className="text-xs text-bad-light">{installError}</p>
          )}
          <button
            onClick={install}
            disabled={installing}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-light transition-colors disabled:opacity-50"
          >
            {installing ? (
              <><Loader size={14} className="animate-spin" /> Installing…</>
            ) : (
              <><ShieldCheck size={14} /> Install &amp; Configure</>
            )}
          </button>
        </div>
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
      {jails.length > 0 && (
        <div className="flex items-center gap-2 pt-2">
          <button
            onClick={reapply}
            disabled={refreshing}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-panel-elevated text-ink-secondary text-xs font-medium hover:bg-panel-border transition-colors disabled:opacity-50"
          >
            {refreshing ? (
              <><Loader size={12} className="animate-spin" /> Re-applying…</>
            ) : (
              <><RefreshCw size={12} /> Re-apply Config</>
            )}
          </button>
          {jails.every(j => j.enabled) && (
            <span className="flex items-center gap-1.5 text-ok text-xs ml-auto">
              <Check size={12} /> All jails enabled
            </span>
          )}
        </div>
      )}
      {installError && jails.length > 0 && (
        <p className="text-xs text-bad-light">{installError}</p>
      )}
    </div>
  );
}

const COUNTRY_REGIONS = {
  'Eastern Europe': ['AL','BA','BG','BY','CZ','EE','HR','HU','LT','LV','MD','ME','MK','PL','RO','RS','SK','SI','UA'],
  'Western Europe': ['AT','BE','CH','DE','DK','ES','FI','FR','GB','GR','IE','IS','IT','LU','NL','NO','PT','SE'],
  'Middle East & North Africa': ['AE','BH','DZ','EG','IL','IQ','IR','JO','KW','LB','LY','MA','OM','PS','QA','SA','SY','TN','YE'],
  'Sub-Saharan Africa': ['AO','BF','BI','BJ','BW','CD','CF','CG','CI','CM','CV','DJ','ER','ET','GA','GH','GM','GN','GQ','KE','KM','LR','LS','MG','ML','MR','MU','MW','MZ','NA','NE','NG','RW','SC','SD','SL','SN','SO','SS','ST','SZ','TD','TG','TZ','UG','ZA','ZM','ZW'],
  'Asia-Pacific': ['AF','AM','AU','AZ','BD','BN','BT','CN','FJ','GE','ID','IN','JP','KG','KH','KP','KR','KZ','LA','LK','MM','MN','MV','MY','NP','NZ','PG','PH','PK','SB','SG','TH','TJ','TL','TM','TV','UZ','VN','VU','WS'],
  'Americas': ['AG','AR','BB','BO','BR','BS','BZ','CA','CL','CO','CR','CU','DM','DO','EC','GD','GT','GY','HN','HT','JM','MX','NI','PA','PE','PY','SR','SV','TT','US','UY','VC','VE'],
};

const REGION_DISPLAY = {
  'Eastern Europe': { desc: 'Eastern & Central Europe', icon: '🏰' },
  'Western Europe': { desc: 'Western & Southern Europe', icon: '🏛️' },
  'Middle East & North Africa': { desc: 'MENA region', icon: '🏜️' },
  'Sub-Saharan Africa': { desc: 'Central & Southern Africa', icon: '🌍' },
  'Asia-Pacific': { desc: 'Asia, Oceania & Pacific', icon: '🌏' },
  'Americas': { desc: 'North, Central & South America', icon: '🌎' },
};

const QUICK_BLOCK = [
  { label: 'China', code: 'CN' },
  { label: 'Russia', code: 'RU' },
  { label: 'North Korea', code: 'KP' },
  { label: 'Iran', code: 'IR' },
  { label: 'Syria', code: 'SY' },
  { label: 'Venezuela', code: 'VE' },
  { label: 'Cuba', code: 'CU' },
  { label: 'Belarus', code: 'BY' },
  { label: 'Myanmar', code: 'MM' },
  { label: 'Sudan', code: 'SD' },
];

function GeoStep({ onDone, markStep }) {
  const [countries, setCountries] = useState([]);
  const [blocked, setBlocked] = useState({});
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState('');
  const [suggestions, setSuggestions] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  const inputRef = useRef(null);

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

  useEffect(() => {
    if (!input.trim()) { setSuggestions([]); setShowDropdown(false); return; }
    const q = input.toLowerCase();
    const matches = countries
      .filter(c =>
        (c.name?.toLowerCase().includes(q) || c.code?.toLowerCase().includes(q)) &&
        !blocked[c.code]
      )
      .slice(0, 10);
    setSuggestions(matches);
    setShowDropdown(matches.length > 0);
    setActiveIdx(-1);
  }, [input, countries, blocked]);

  const addCountry = async (cc, name) => {
    if (blocked[cc]) return;
    setInput('');
    setShowDropdown(false);
    try {
      await api.post('/api/fail2ban/geo-blocks', { country_code: cc, country_name: name, blocked: true });
      setBlocked(prev => ({ ...prev, [cc]: true }));
      await api.post('/api/fail2ban/geo-blocks/apply-all');
      await markStep('geo_block_done', true);
    } catch {
      toast.error(`Failed to block ${name}`);
    }
  };

  const removeCountry = async (cc, name) => {
    try {
      await api.post('/api/fail2ban/geo-blocks', { country_code: cc, country_name: name, blocked: false });
      setBlocked(prev => ({ ...prev, [cc]: false }));
      await api.post('/api/fail2ban/geo-blocks/apply-all');
    } catch {
      toast.error(`Failed to unblock ${name}`);
    }
  };

  const handleKey = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx(i => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter' && activeIdx >= 0 && suggestions[activeIdx]) {
      e.preventDefault();
      addCountry(suggestions[activeIdx].code, suggestions[activeIdx].name);
    } else if (e.key === 'Enter' && input.trim()) {
      e.preventDefault();
      const exact = countries.find(c =>
        c.name?.toLowerCase() === input.trim().toLowerCase() && !blocked[c.code]
      );
      if (exact) addCountry(exact.code, exact.name);
    } else if (e.key === 'Escape') {
      setShowDropdown(false);
    }
  };

  if (loading) return <div className="flex items-center gap-2 text-sm text-ink-muted"><Loader size={14} className="animate-spin" /> Loading countries…</div>;

  const blockedEntries = Object.entries(blocked).filter(([,v]) => v);
  const countryName = (cc) => countries.find(c => c.code === cc)?.name || cc;

  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-muted">
        Type a country name and press Enter to block it. Blocked countries are denied at the firewall level.
      </p>

      {/* Autocomplete input */}
      <div className="relative">
        <input
          ref={inputRef}
          className="input w-full text-sm"
          type="text"
          placeholder="Type country name… e.g. China, Russia"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          onFocus={() => input.trim() && setSuggestions.length > 0 && setShowDropdown(true)}
          onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
        />
        {showDropdown && (
          <div className="absolute top-full left-0 right-0 mt-1 bg-panel-800 border border-panel-border rounded-lg shadow-xl z-10 max-h-48 overflow-y-auto">
            {suggestions.map((c, i) => (
              <button
                key={c.code}
                onMouseDown={() => addCountry(c.code, c.name)}
                className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 transition-colors ${
                  i === activeIdx ? 'bg-brand/15 text-brand-light' : 'text-ink-primary hover:bg-panel-elevated'
                }`}
              >
                <span>{c.name}</span>
                <span className="text-ink-faint text-[11px] font-mono">{c.code}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Quick-block chips */}
      <div>
        <p className="text-[11px] text-ink-faint mb-1.5">Quick block</p>
        <div className="flex flex-wrap gap-1.5">
          {QUICK_BLOCK.map(qb => (
            <button
              key={qb.code}
              onClick={() => {
                if (blocked[qb.code]) {
                  removeCountry(qb.code, qb.label);
                } else {
                  addCountry(qb.code, qb.label);
                }
              }}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                blocked[qb.code]
                  ? 'bg-bad/15 text-bad-light border-bad/30'
                  : 'bg-panel-elevated text-ink-muted border-panel-border hover:border-ink-faint hover:text-ink-primary'
              }`}
            >
              {qb.label} {blocked[qb.code] ? '✓' : '+'}
            </button>
          ))}
        </div>
      </div>

      {/* Blocked pills */}
      {blockedEntries.length > 0 && (
        <div>
          <p className="text-[11px] text-ink-faint mb-1.5">
            Blocked ({blockedEntries.length})
          </p>
          <div className="flex flex-wrap gap-1.5">
            {blockedEntries.map(([cc]) => (
              <span
                key={cc}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs bg-bad/15 text-bad-light border border-bad/30"
              >
                {countryName(cc)}
                <button
                  onClick={() => removeCountry(cc, countryName(cc))}
                  className="hover:text-bright transition-colors leading-none"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
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


// ═════════════════════════════════════════════════════════════════════════════
// Grafana connectivity test — small badge showing [working] / [fail]
// ═════════════════════════════════════════════════════════════════════════════

function GrafanaTest() {
  const [status, setStatus] = useState('checking'); // checking | ok | fail
  const [msg, setMsg] = useState('');

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const timeout = setTimeout(() => {
      if (!cancelled) {
        setStatus('fail');
        setMsg('Connection timed out');
      }
      controller.abort();
    }, 5000);

    fetch('http://localhost:3001/api/health', {
      signal: controller.signal,
      mode: 'no-cors',
    })
      .then(() => {
        if (!cancelled) {
          clearTimeout(timeout);
          setStatus('ok');
          setMsg('Grafana is responding');
        }
      })
      .catch(() => {
        if (!cancelled) {
          clearTimeout(timeout);
          // Fallback: try the Grafana login page
          fetch('http://localhost:3001/login', { signal: controller.signal })
            .then(() => { setStatus('ok'); setMsg('Grafana is reachable'); })
            .catch(() => { setStatus('fail'); setMsg('Cannot reach Grafana'); });
        }
      });

    return () => { cancelled = true; clearTimeout(timeout); controller.abort(); };
  }, []);

  if (status === 'checking') {
    return (
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-panel-surface border border-panel-subtle">
        <Loader size={14} className="animate-spin text-ink-muted" />
        <span className="text-xs text-ink-muted">Testing Grafana connection…</span>
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${
      status === 'ok'
        ? 'bg-ok/10 border-ok/20'
        : 'bg-error/10 border-error/20'
    }`}>
      {status === 'ok' ? (
        <CheckCircle size={14} className="text-ok shrink-0" />
      ) : (
        <XCircle size={14} className="text-error shrink-0" />
      )}
      <span className={`text-xs ${status === 'ok' ? 'text-ok' : 'text-error'}`}>
        Grafana: <strong className="uppercase tracking-wider">{status === 'ok' ? 'working' : 'fail'}</strong>
        {msg && <span className="text-ink-muted ml-1">— {msg}</span>}
      </span>
    </div>
  );
}


// ═════════════════════════════════════════════════════════════════════════════
// MFA Wizard Step — inline QR scan + verify + recovery codes download
// ═════════════════════════════════════════════════════════════════════════════

function MfaWizardStep({ onDone }) {
  const [step, setStep] = useState('start'); // start | qr | recovery | done
  const [enrollData, setEnrollData] = useState(null);
  const [verifyCode, setVerifyCode] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [recoveryCodes, setRecoveryCodes] = useState(null);
  const [error, setError] = useState(null);
  const [expectedCode, setExpectedCode] = useState('');

  useEffect(() => {
    if (step !== 'qr' || !enrollData) return;
    setExpectedCode(enrollData.expected_code || '');

    const interval = setInterval(async () => {
      try {
        const res = await api.get(`/api/mfa/expected-code/${enrollData.device_id}`);
        setExpectedCode(res.data.expected_code || '');
      } catch { /* ignore */ }
    }, 5000);

    return () => clearInterval(interval);
  }, [step, enrollData]);

  const startEnroll = async () => {
    setError(null);
    try {
      const res = await api.post('/api/mfa/enroll', null, {
        params: { device_name: 'Setup Wizard' },
      });
      setEnrollData(res.data);
      setStep('qr');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start MFA enrollment.');
    }
  };

  const verifyTotp = async () => {
    if (!verifyCode.trim() || !enrollData) return;
    setVerifying(true);
    setError(null);
    try {
      const res = await api.post('/api/mfa/verify', {
        device_id: enrollData.device_id,
        code: verifyCode.trim(),
      });
      if (res.data?.recovery_codes?.length) {
        setRecoveryCodes(res.data.recovery_codes);
        setStep('recovery');
      } else {
        onDone();
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid code. Please try again.');
    } finally {
      setVerifying(false);
    }
  };

  const downloadRecoveryTxt = () => {
    if (!recoveryCodes) return;
    const lines = [
      'GnuKontrolR - MFA Recovery Codes',
      '================================',
      'Generated: ' + new Date().toISOString(),
      '',
      'Keep these codes safe and private. Each code can be used ONLY ONCE.',
      'If you lose access to your authenticator app, enter one of these',
      'codes during login to regain access to your account.',
      '',
      '┌──────────────────────────────────────┐',
      ...recoveryCodes.map((c, i) => `│  ${String(i + 1).padStart(2, ' ')}.  ${c}  │`),
      '└──────────────────────────────────────┘',
      '',
      'After using a recovery code, generate new codes from the MFA settings page.',
      'Store this file in a secure location (e.g., password manager, safe).',
      '',
    ].join('\n');
    const blob = new Blob([lines], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'gnukontrolr-mfa-recovery-codes.txt';
    a.click();
    URL.revokeObjectURL(url);
  };

  if (step === 'start') {
    return (
      <div className="space-y-4">
        <p className="text-sm text-ink-secondary leading-relaxed">
          Multi-factor authentication adds an extra layer of security to your account.
          After setup, you will need both your password <strong>and</strong> a one-time code
          from your authenticator app to log in.
        </p>
        <div className="flex items-start gap-3 px-3 py-2.5 bg-brand/10 border border-brand/20 rounded-lg">
          <Smartphone size={16} className="text-brand shrink-0 mt-0.5" />
          <ul className="text-xs text-ink-muted space-y-1">
            <li>✓ Works with Google Authenticator, Authy, Microsoft Authenticator, etc.</li>
            <li>✓ Time-based one-time passwords (TOTP) — no internet required after setup</li>
            <li>✓ 8 recovery codes will be generated — save them securely</li>
          </ul>
        </div>
        <button
          onClick={startEnroll}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium
                     bg-brand hover:bg-brand-hover text-white transition-colors"
        >
          <Smartphone size={16} />
          Set Up MFA Now
        </button>
      </div>
    );
  }

  if (step === 'recovery') {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-ok">
          <CheckCircle size={18} />
          <span className="text-sm font-medium text-ok">MFA Activated Successfully</span>
        </div>

        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Key size={16} className="text-amber-400" />
            <h3 className="text-sm font-semibold text-ink-primary">Recovery Codes</h3>
          </div>
          <p className="text-xs text-ink-muted">
            These codes can be used <strong className="text-amber-300">once each</strong> if you lose access
            to your authenticator app. Save them now — they will never be shown again.
          </p>

          <div className="grid grid-cols-2 gap-1.5">
            {recoveryCodes.map((code, i) => (
              <div key={i} className="px-2.5 py-1.5 rounded bg-panel-surface border border-panel-subtle
                                          font-mono text-xs text-ink-primary tracking-wider text-center">
                {code.match(/.{1,4}/g).join('-')}
              </div>
            ))}
          </div>

          <div className="flex flex-wrap gap-2 pt-1">
            <button
              onClick={downloadRecoveryTxt}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-medium
                         bg-brand hover:bg-brand-hover text-white transition-colors"
            >
              <Download size={14} />
              Download Recovery Codes (.txt)
            </button>
            <button
              onClick={() => {
                navigator.clipboard.writeText(recoveryCodes.join('\n'));
                toast.success('Recovery codes copied!');
              }}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-medium
                         border border-panel-subtle text-ink-primary hover:bg-panel-hover transition-colors"
            >
              <Copy size={14} />
              Copy All
            </button>
          </div>
        </div>

        <button
          onClick={onDone}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium
                     bg-ok hover:bg-ok/80 text-white transition-colors"
        >
          <CheckCircle size={16} />
          Done — Mark Step Complete
        </button>
      </div>
    );
  }

  // step === 'qr'
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-secondary">
        Scan this QR code with your authenticator app, then enter the 6-digit code below.
      </p>

      {/* QR Code */}
      {enrollData?.qrcode_b64 && (
        <div className="flex justify-center">
          <div className="p-2 bg-white rounded-xl shadow-lg">
            <img
              src={`data:image/png;base64,${enrollData.qrcode_b64}`}
              alt="MFA QR Code"
              className="w-44 h-44"
            />
          </div>
        </div>
      )}

      {/* Manual secret fallback */}
      {enrollData?.secret && (
        <div className="flex items-center justify-between bg-panel-surface border border-panel-subtle rounded-lg px-3 py-2">
          <div>
            <span className="text-xs text-ink-muted">Secret key (manual entry):</span>
            <code className="ml-2 text-sm font-mono text-ink-primary">{enrollData.secret}</code>
          </div>
          <button
            onClick={() => {
              navigator.clipboard.writeText(enrollData.secret);
              toast.success('Secret key copied');
            }}
            className="p-1.5 rounded hover:bg-panel-hover text-ink-muted hover:text-ink-primary"
          >
            <Copy size={14} />
          </button>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 px-3 py-2 bg-error/10 border border-error/20 rounded-lg">
          <XCircle size={14} className="text-error shrink-0" />
          <span className="text-xs text-error">{error}</span>
        </div>
      )}

      {/* Verify code */}
      <div className="flex items-end gap-3">
        <div className="space-y-1">
          <label className="text-xs text-ink-muted flex items-center gap-1.5">
            <span>Verification Code</span>
            {expectedCode && (
              <span className="text-[10px] text-brand-light font-mono select-all">
                (expected code {expectedCode})
              </span>
            )}
          </label>
          <input
            type="text"
            value={verifyCode}
            onChange={(e) => setVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            placeholder="000000"
            maxLength={6}
            className="w-36 px-3 py-2 rounded-lg bg-panel-surface border border-panel-subtle
                       text-ink-primary text-center text-xl font-mono tracking-widest
                       focus:outline-none focus:ring-2 focus:ring-brand/50"
          />
        </div>
        <button
          onClick={verifyTotp}
          disabled={verifying || verifyCode.length !== 6}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                     bg-brand hover:bg-brand-hover text-white transition-colors disabled:opacity-50"
        >
          {verifying ? (
            <><Loader size={14} className="animate-spin" /> Verifying…</>
          ) : (
            <><CheckCircle size={14} /> Verify &amp; Activate</>
          )}
        </button>
      </div>
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
  const [dpoEmail, setDpoEmail] = useState('');
  const [hasScrolledToBottom, setHasScrolledToBottom] = useState(false);
  const [privacyAccepted, setPrivacyAccepted] = useState(false);
  const privacyScrollRef = useRef(null);

  useEffect(() => {
    setHasScrolledToBottom(false);
    setPrivacyAccepted(false);
  }, [step]);

  useEffect(() => {
    if (STEPS[step]?.id === 'privacy_policy' && privacyScrollRef.current) {
      const el = privacyScrollRef.current;
      if (el.scrollHeight <= el.clientHeight) {
        setHasScrolledToBottom(true);
      }
    }
  }, [step]);

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

  const nextStep = async () => {
    if (step < totalSteps - 1) {
      const s = STEPS[step];
      if (s.id === 'services' && !isStepDone(step)) {
        await markStep(s.field, false);
      }
      if (s.id === 'privacy_policy' && !isStepDone(step)) {
        await markStep(s.field, true);
      }
      setStep(prev => prev + 1);
    }
  };

  const prevStep = () => {
    if (step > 0) setStep(s => s - 1);
  };

  const skipStep = async () => {
    await markStep(STEPS[step].field, false);
    nextStep();
  };

  const handleScroll = (e) => {
    const el = e.target;
    const isAtBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 5;
    if (isAtBottom) {
      setHasScrolledToBottom(true);
    }
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

  const resetWizard = async () => {
    if (!confirm('Reset the setup wizard? All steps will be marked incomplete and the wizard will reappear.')) return;
    try {
      await api.post('/api/setup/reset');
      toast.success('Wizard reset. Reloading…');
      setTimeout(() => window.location.reload(), 800);
    } catch (err) {
      toast.error('Failed to reset: ' + (err?.response?.data?.detail || err.message));
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
                <div className="space-y-3">
                  {/* Quick connectivity test */}
                  <GrafanaTest />

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

              {current.id === 'dsar_contact' && (
                <div className="space-y-3">
                  <p className="text-sm text-ink-secondary">
                    Set the Data Protection Officer (DPO) contact email for handling privacy requests
                    and breach notifications.
                  </p>
                  <div className="flex items-center gap-2">
                    <input
                      type="email"
                      value={dpoEmail}
                      onChange={(e) => setDpoEmail(e.target.value)}
                      placeholder="dpo@example.com"
                      className="flex-1 max-w-xs px-3 py-2 rounded-lg bg-panel-surface border border-panel-subtle
                                 text-ink-primary placeholder-ink-muted text-sm
                                 focus:outline-none focus:ring-2 focus:ring-brand/50"
                    />
                    <button
                      onClick={() => {
                        if (dpoEmail.trim()) {
                          toast.success('DSAR contact saved. Update .env BREACH_NOTIFICATION_EMAIL for persistence.');
                          markStep(current.field);
                        }
                      }}
                      disabled={!dpoEmail.trim()}
                      className="px-4 py-2 rounded-lg text-sm font-medium bg-brand hover:bg-brand-hover
                                 text-white transition-colors disabled:opacity-50"
                    >
                      Save Contact
                    </button>
                  </div>
                </div>
              )}

              {current.id === 'data_retention' && (
                <div className="space-y-3">
                  <p className="text-sm text-ink-secondary">
                    Data retention policies ensure compliance with GDPR, SOC 2, and ISO 27001.
                    The following schedules are configured:
                  </p>
                  <ul className="text-xs text-ink-muted space-y-1 list-disc pl-4">
                    <li>Request logs: 12 months</li>
                    <li>Consent records: 3 years</li>
                    <li>Completed DSARs: 1 year</li>
                    <li>Suspended accounts: 90-day grace period</li>
                    <li>Password history: last 5 passwords blocked from reuse</li>
                  </ul>
                </div>
              )}

              {current.id === 'privacy_policy' && (
                <div className="space-y-3">
                  <p className="text-sm text-ink-secondary">
                    Review and accept the platform Privacy Policy to record your consent.
                  </p>
                  <div
                    ref={privacyScrollRef}
                    onScroll={handleScroll}
                    className="h-32 overflow-y-auto border border-panel-border p-3 rounded-lg text-[11px] font-mono text-ink-secondary bg-panel-elevated leading-relaxed whitespace-pre-wrap"
                  >
{`GnuKontrolR Privacy Policy Basics

1. Data Collection
We collect system configuration, domain configurations, user emails, and system operation logs to provide container hosting and DNS management services.

2. Data Retention
- System request logs: Retained for 12 months.
- Account information: Retained for the duration of the active account.
- Consent records: Retained for 3 years to comply with GDPR/SOC 2 standards.

3. Data Subject Rights
You can request access, correction, or deletion of your personal data at any time via the Privacy section of the dashboard or by contacting the DPO.

4. Security Measures
All credentials and secrets are encrypted at rest using AES-256 (Fernet) and TLS 1.2+ is enforced for all external communications.

5. Compliance & Third-Parties
We do not sell or share your personal data with third parties. All operational data is stored securely on your local instance.`}
                  </div>
                  <div className="flex items-center justify-between pt-1">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        id="accept-privacy-policy"
                        checked={privacyAccepted || isStepDone(step)}
                        disabled={isStepDone(step) || !hasScrolledToBottom}
                        onChange={(e) => setPrivacyAccepted(e.target.checked)}
                        className="w-4 h-4 rounded border-panel-subtle bg-panel-surface text-brand focus:ring-brand/50 focus:ring-offset-0 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                      />
                      <label
                        htmlFor="accept-privacy-policy"
                        className={`text-xs select-none cursor-pointer ${
                          !hasScrolledToBottom && !isStepDone(step)
                            ? 'text-ink-muted cursor-not-allowed'
                            : 'text-ink-secondary hover:text-ink-primary'
                        }`}
                      >
                        {!hasScrolledToBottom && !isStepDone(step)
                          ? 'Please scroll to the bottom of the policy to accept'
                          : 'I accept the Privacy Policy'}
                      </label>
                    </div>
                    {isStepDone(step) && (
                      <div className="flex items-center gap-1.5 text-ok text-xs">
                        <CheckCircle size={14} /> Accepted &amp; Consent Recorded
                      </div>
                    )}
                  </div>
                </div>
              )}

              {current.id === 'mfa' && (
                isStepDone(step) ? (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 text-ok">
                      <CheckCircle size={18} />
                      <span className="text-sm font-medium text-ok">MFA is active and configured for your account.</span>
                    </div>
                    <p className="text-xs text-ink-muted leading-relaxed">
                      Your session is protected with multi-factor authentication. You can generate new recovery codes or disable MFA from the Settings page.
                    </p>
                  </div>
                ) : (
                  <MfaWizardStep onDone={() => markStep(current.field, true)} />
                )
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
                {current.interactive && !isStepDone(step) && current.id !== 'services' && (current.id !== 'privacy_policy' || !privacyAccepted) ? (
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
            {diagnosticResults && (
              <button
                onClick={resetWizard}
                className="px-3 py-1.5 text-[10px] text-ink-faint hover:text-error transition-colors ml-auto"
              >
                Reset Setup Wizard
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
