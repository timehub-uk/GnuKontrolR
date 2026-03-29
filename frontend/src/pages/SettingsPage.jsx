import { useState, useEffect } from 'react';
import { Settings, Key, User, Lock, CheckCircle, ExternalLink, Contact, Globe, Server, ScrollText } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api from '../utils/api';

const PROVIDERS = [
  {
    id: 'anthropic',
    name: 'Anthropic',
    description: 'Claude models (claude-3-5-sonnet, claude-3-opus, etc.)',
  },
  {
    id: 'openai',
    name: 'OpenAI',
    description: 'GPT-4o, GPT-4, GPT-3.5-turbo and compatible endpoints.',
  },
  {
    id: 'zen',
    name: 'Zen (OpenCode Zen)',
    description: 'OpenCode Zen provider — no API key required if using OpenCode account.',
  },
  {
    id: 'ollama',
    name: 'Ollama',
    description: 'Local Ollama instance. Use base URL as the key (e.g. http://localhost:11434).',
  },
];

function ProviderRow({ provider, configured, onSaved }) {
  const [key, setKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [msg, setMsg] = useState(null);

  const save = async () => {
    if (!key.trim()) return;
    setSaving(true);
    setMsg(null);
    try {
      await api.post('/api/ai/providers', { provider: provider.id, api_key: key });
      setKey('');
      setMsg({ type: 'ok', text: 'Saved.' });
      onSaved();
    } catch (err) {
      setMsg({ type: 'err', text: err.response?.data?.detail || 'Save failed.' });
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!confirm(`Remove ${provider.name} key?`)) return;
    setDeleting(true);
    setMsg(null);
    try {
      await api.delete(`/api/ai/providers/${provider.id}`);
      setMsg({ type: 'ok', text: 'Removed.' });
      onSaved();
    } catch (err) {
      setMsg({ type: 'err', text: err.response?.data?.detail || 'Delete failed.' });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex flex-col gap-2 py-4 border-b border-panel-subtle last:border-0">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-ink-primary">{provider.name}</span>
            {configured && (
              <span className="inline-flex items-center gap-1 text-xs text-ok bg-ok/10 px-2 py-0.5 rounded-full">
                <CheckCircle size={10} /> Configured
              </span>
            )}
          </div>
          <p className="text-xs text-ink-muted mt-0.5">{provider.description}</p>
        </div>
        {configured && (
          <button
            onClick={remove}
            disabled={deleting}
            className="text-xs text-bad-light hover:text-bad disabled:opacity-50 transition-colors"
          >
            {deleting ? 'Removing…' : 'Remove'}
          </button>
        )}
      </div>
      <div className="flex gap-2">
        <input
          className="input flex-1 text-sm"
          type="password"
          placeholder={configured ? 'Enter new key to replace…' : 'Paste API key…'}
          value={key}
          onChange={e => setKey(e.target.value)}
        />
        <button
          onClick={save}
          disabled={saving || !key.trim()}
          className="btn-primary text-xs px-3 disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
      {msg && (
        <p className={`text-xs ${msg.type === 'ok' ? 'text-ok' : 'text-bad-light'}`}>
          {msg.text}
        </p>
      )}
    </div>
  );
}

function OpenCodeRow({ connected, onRefresh }) {
  const [starting, setStarting] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const [awaitingVerify, setAwaitingVerify] = useState(false);
  const [msg, setMsg] = useState(null);

  const login = async () => {
    setStarting(true);
    setMsg(null);
    try {
      const { data } = await api.post('/api/ai/opencode-auth/login');
      window.open(data.url, '_blank');
      setAwaitingVerify(true);
    } catch (err) {
      setMsg({ type: 'err', text: err.response?.data?.detail || 'Could not start login.' });
    } finally {
      setStarting(false);
    }
  };

  const verify = async () => {
    setVerifying(true);
    setMsg(null);
    try {
      await api.post('/api/ai/opencode-auth/verify');
      setAwaitingVerify(false);
      setMsg({ type: 'ok', text: 'Connected successfully.' });
      onRefresh();
    } catch (err) {
      setMsg({ type: 'err', text: err.response?.data?.detail || 'Verification failed. Try again.' });
    } finally {
      setVerifying(false);
    }
  };

  const disconnect = async () => {
    if (!confirm('Disconnect OpenCode account?')) return;
    setDisconnecting(true);
    setMsg(null);
    try {
      await api.delete('/api/ai/providers/opencode_account');
      setAwaitingVerify(false);
      setMsg({ type: 'ok', text: 'Disconnected.' });
      onRefresh();
    } catch (err) {
      setMsg({ type: 'err', text: err.response?.data?.detail || 'Disconnect failed.' });
    } finally {
      setDisconnecting(false);
    }
  };

  return (
    <div className="flex flex-col gap-2 py-4 border-b border-panel-subtle">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-ink-primary">OpenCode Account</span>
            {connected && (
              <span className="inline-flex items-center gap-1 text-xs text-ok bg-ok/10 px-2 py-0.5 rounded-full">
                <CheckCircle size={10} /> Connected
              </span>
            )}
          </div>
          <p className="text-xs text-ink-muted mt-0.5">
            Sign in with your OpenCode account for access to Zen and other managed models.
          </p>
        </div>
        {connected ? (
          <button
            onClick={disconnect}
            disabled={disconnecting}
            className="text-xs text-bad-light hover:text-bad disabled:opacity-50 transition-colors"
          >
            {disconnecting ? 'Disconnecting…' : 'Disconnect'}
          </button>
        ) : (
          <div className="flex gap-2">
            {awaitingVerify && (
              <button
                onClick={verify}
                disabled={verifying}
                className="btn-primary text-xs px-3 disabled:opacity-50 flex items-center gap-1"
              >
                {verifying ? 'Verifying…' : 'Verify'}
              </button>
            )}
            <button
              onClick={login}
              disabled={starting}
              className="btn-primary text-xs px-3 disabled:opacity-50 flex items-center gap-1"
            >
              <ExternalLink size={12} />
              {starting ? 'Opening…' : 'Connect OpenCode Account'}
            </button>
          </div>
        )}
      </div>
      {msg && (
        <p className={`text-xs ${msg.type === 'ok' ? 'text-ok' : 'text-bad-light'}`}>
          {msg.text}
        </p>
      )}
    </div>
  );
}

function PersonalDetailsCard({ user, onSaved }) {
  const [form, setForm] = useState({
    preferred_name: '',
    full_name:      '',
    phone:          '',
    company:        '',
    address_line1:  '',
    address_line2:  '',
    city:           '',
    state:          '',
    postcode:       '',
    country:        '',
  });
  const [saving, setSaving] = useState(false);
  const [msg,    setMsg]    = useState(null);

  // Populate from user object when it loads
  useEffect(() => {
    if (!user) return;
    setForm({
      preferred_name: user.preferred_name || '',
      full_name:      user.full_name      || '',
      phone:          user.phone          || '',
      company:        user.company        || '',
      address_line1:  user.address_line1  || '',
      address_line2:  user.address_line2  || '',
      city:           user.city           || '',
      state:          user.state          || '',
      postcode:       user.postcode       || '',
      country:        user.country        || '',
    });
  }, [user]);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const save = async () => {
    setSaving(true);
    setMsg(null);
    try {
      await api.patch('/api/users/me', form);
      setMsg({ type: 'ok', text: 'Details saved.' });
      if (onSaved) onSaved();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const text = Array.isArray(detail)
        ? detail.map(e => e.msg || String(e)).join(', ')
        : (detail || 'Save failed.');
      setMsg({ type: 'err', text });
    } finally {
      setSaving(false);
    }
  };

  const field = (label, key, opts = {}) => (
    <div className={opts.full ? 'col-span-2' : ''}>
      <label className="block text-xs text-ink-muted mb-1">{label}</label>
      <input
        className="input w-full text-sm"
        type={opts.type || 'text'}
        placeholder={opts.placeholder || ''}
        value={form[key]}
        onChange={e => set(key, e.target.value)}
      />
    </div>
  );

  return (
    <div className="card space-y-4">
      <h2 className="text-sm font-semibold text-white flex items-center gap-2">
        <Contact size={14} /> Personal &amp; Contact Details
      </h2>

      {/* Preferred name — highlighted at top */}
      <div className="bg-brand/8 border border-brand/20 rounded-xl p-4 space-y-1">
        <label className="block text-xs font-medium text-brand-light">
          What would you like to be called?
        </label>
        <input
          className="input w-full text-sm"
          type="text"
          placeholder="e.g. Alex, Dr Smith, Captain…"
          value={form.preferred_name}
          onChange={e => set('preferred_name', e.target.value)}
        />
        <p className="text-[11px] text-ink-faint">
          Used in panel greetings — leave blank to use your username.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {field('Full Name', 'full_name', { placeholder: 'Jane Smith' })}
        {field('Phone', 'phone', { placeholder: '+1 555 000 0000' })}
        {field('Company', 'company', { placeholder: 'Acme Ltd', full: false })}
        {field('Address Line 1', 'address_line1', { placeholder: '123 Main St', full: false })}
        {field('Address Line 2', 'address_line2', { placeholder: 'Suite 4B', full: false })}
        {field('City', 'city', { placeholder: 'London' })}
        {field('State / Region', 'state', { placeholder: 'England' })}
        {field('Postcode / ZIP', 'postcode', { placeholder: 'EC1A 1BB' })}
        {field('Country', 'country', { placeholder: 'United Kingdom' })}
      </div>

      {msg && (
        <p className={`text-xs ${msg.type === 'ok' ? 'text-ok' : 'text-bad-light'}`}>
          {msg.text}
        </p>
      )}
      <button
        onClick={save}
        disabled={saving}
        className="btn-primary text-sm disabled:opacity-50"
      >
        {saving ? 'Saving…' : 'Save Details'}
      </button>
    </div>
  );
}

function PanelConfigCard() {
  const [domains,      setDomains]      = useState([]);
  const [config,       setConfig]       = useState({ panel_domain: '', server_ip: '', acme_email: '' });
  const [form,         setForm]         = useState({ panel_domain: '', server_ip: '', acme_email: '' });
  const [saving,       setSaving]       = useState(false);
  const [msg,          setMsg]          = useState(null);
  const [noDomains,    setNoDomains]    = useState(false);

  const load = async () => {
    try {
      const [cfgRes, domRes] = await Promise.all([
        api.get('/api/server/panel-config'),
        api.get('/api/domains'),
      ]);
      const cfg  = cfgRes.data;
      const doms = domRes.data || [];
      setConfig(cfg);
      setForm({ panel_domain: cfg.panel_domain || '', server_ip: cfg.server_ip || '', acme_email: cfg.acme_email || '' });
      setDomains(doms);
      setNoDomains(doms.length === 0);
    } catch {
      setMsg({ type: 'err', text: 'Failed to load panel config.' });
    }
  };

  useEffect(() => { load(); }, []);

  const save = async () => {
    if (!form.panel_domain) return;
    setSaving(true);
    setMsg(null);
    try {
      const { data } = await api.patch('/api/server/panel-config', form);
      setMsg({
        type: 'ok',
        text: `Saved. NS updated for ${data.ns_updated} domain(s).${data.errors?.length ? ` Errors: ${data.errors.join(', ')}` : ''}`,
      });
      await load();
    } catch (err) {
      setMsg({ type: 'err', text: err.response?.data?.detail || 'Save failed.' });
    } finally {
      setSaving(false);
    }
  };

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  return (
    <div className="card space-y-5">
      <h2 className="text-sm font-semibold text-white flex items-center gap-2">
        <Globe size={14} /> Panel &amp; DNS Configuration
      </h2>

      {noDomains && (
        <div className="rounded-lg bg-yellow-500/10 border border-yellow-500/30 px-4 py-3 text-sm text-yellow-300">
          No domains have been added yet. Add a domain first, then set it as the master domain here.
        </div>
      )}

      {/* Master domain */}
      <div>
        <label className="block text-xs font-medium text-ink-muted mb-1">
          Master Domain <span className="text-ink-faint">(NS1/NS2/NS3 will be set under this domain)</span>
        </label>
        {domains.length > 0 ? (
          <select
            className="input w-full text-sm"
            value={form.panel_domain}
            onChange={e => set('panel_domain', e.target.value)}
          >
            <option value="">— select master domain —</option>
            {domains.map(d => (
              <option key={d.name} value={d.name}>{d.name}</option>
            ))}
          </select>
        ) : (
          <input
            className="input w-full text-sm"
            type="text"
            placeholder="e.g. yourdomain.com"
            value={form.panel_domain}
            onChange={e => set('panel_domain', e.target.value)}
          />
        )}
        {config.panel_domain && (
          <p className="text-[11px] text-ink-faint mt-1">
            Current: <span className="font-mono text-brand-light">{config.panel_domain}</span>
            &nbsp;→ NS records: ns1.{config.panel_domain}, ns2.{config.panel_domain}, ns3.{config.panel_domain}
          </p>
        )}
      </div>

      {/* Server IP (read-only display + optional override) */}
      <div>
        <label className="block text-xs font-medium text-ink-muted mb-1">
          Server IP <span className="text-ink-faint">(auto-detected hourly — override only if needed)</span>
        </label>
        <input
          className="input w-full text-sm font-mono"
          type="text"
          placeholder={config.server_ip || 'Auto-detected'}
          value={form.server_ip}
          onChange={e => set('server_ip', e.target.value)}
        />
      </div>

      {/* ACME email */}
      <div>
        <label className="block text-xs font-medium text-ink-muted mb-1">Let's Encrypt Email</label>
        <input
          className="input w-full text-sm"
          type="email"
          placeholder={config.acme_email || 'admin@yourdomain.com'}
          value={form.acme_email}
          onChange={e => set('acme_email', e.target.value)}
        />
      </div>

      {msg && (
        <p className={`text-xs ${msg.type === 'ok' ? 'text-ok' : 'text-bad-light'}`}>{msg.text}</p>
      )}

      <button
        onClick={save}
        disabled={saving || !form.panel_domain}
        className="btn-primary text-sm disabled:opacity-50"
      >
        {saving ? 'Saving & syncing DNS…' : 'Save & Sync DNS'}
      </button>
    </div>
  );
}

const LICENSE_BADGE = {
  'MIT':          'bg-green-500/15 text-green-300 border-green-500/30',
  'Apache 2.0':   'bg-blue-500/15 text-blue-300 border-blue-500/30',
  'GPL v2':       'bg-orange-500/15 text-orange-300 border-orange-500/30',
  'GPL v3':       'bg-orange-500/15 text-orange-300 border-orange-500/30',
  'AGPL v3':      'bg-red-500/15 text-red-300 border-red-500/30',
  'BSD 3-Clause': 'bg-purple-500/15 text-purple-300 border-purple-500/30',
  'BSD 2-Clause': 'bg-purple-500/15 text-purple-300 border-purple-500/30',
  'LGPL v2.1':    'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  'PSF':          'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  'EPL 2.0':      'bg-teal-500/15 text-teal-300 border-teal-500/30',
  'ISC':          'bg-green-500/15 text-green-300 border-green-500/30',
};

const SERVICES = [
  {
    category: 'Infrastructure',
    items: [
      { name: 'Docker Engine',      version: '27+',      license: 'Apache 2.0',   url: 'https://github.com/moby/moby/blob/master/LICENSE',                   desc: 'Container runtime' },
      { name: 'Docker Compose',     version: 'v2',       license: 'Apache 2.0',   url: 'https://github.com/docker/compose/blob/main/LICENSE',               desc: 'Multi-container orchestration' },
      { name: 'Traefik',            version: 'v3.3',     license: 'MIT',          url: 'https://github.com/traefik/traefik/blob/master/LICENSE.md',          desc: 'Reverse proxy & TLS termination' },
      { name: 'Nginx',              version: 'alpine',   license: 'BSD 2-Clause', url: 'https://nginx.org/LICENSE',                                          desc: 'Docker API proxy / web server' },
    ],
  },
  {
    category: 'DNS',
    items: [
      { name: 'PowerDNS Authoritative', version: '4.9', license: 'GPL v2',      url: 'https://github.com/PowerDNS/pdns/blob/master/COPYING',               desc: 'Authoritative DNS server' },
      { name: 'dnsmasq',                version: '2.x',  license: 'GPL v2',      url: 'https://thekelleys.org.uk/dnsmasq/doc.html',                         desc: 'Local DNS resolver (localdns)' },
    ],
  },
  {
    category: 'Databases & Cache',
    items: [
      { name: 'MySQL',              version: '8.4',      license: 'GPL v2',       url: 'https://www.mysql.com/about/legal/licensing/osl/',                   desc: 'Relational database (Community Edition)' },
      { name: 'MariaDB',            version: '10.x',     license: 'GPL v2',       url: 'https://mariadb.com/kb/en/mariadb-license/',                         desc: 'Customer site database (in site containers)' },
      { name: 'Redis',              version: '8',        license: 'BSD 3-Clause', url: 'https://github.com/redis/redis/blob/unstable/COPYING',               desc: 'Cache & session store (Redis 7.x and below)' },
      { name: 'SQLite',             version: '3',        license: 'Public Domain', url: 'https://www.sqlite.org/copyright.html',                             desc: 'Panel SQLite database' },
    ],
  },
  {
    category: 'Mail',
    items: [
      { name: 'Postfix',            version: 'latest',   license: 'EPL 2.0',      url: 'https://www.postfix.org/IBM-Public-License-1.0.txt',                 desc: 'Outbound SMTP' },
      { name: 'Dovecot',            version: 'latest',   license: 'MIT',          url: 'https://github.com/dovecot/core/blob/main/COPYING',                  desc: 'IMAP/POP3 server' },
      { name: 'OpenDKIM',           version: '2.x',      license: 'BSD 3-Clause', url: 'https://github.com/trusteddomainproject/OpenDKIM/blob/master/LICENSE', desc: 'DKIM signing milter' },
    ],
  },
  {
    category: 'Monitoring',
    items: [
      { name: 'Prometheus',         version: 'latest',   license: 'Apache 2.0',   url: 'https://github.com/prometheus/prometheus/blob/main/LICENSE',         desc: 'Metrics collection' },
      { name: 'Grafana',            version: 'latest',   license: 'AGPL v3',      url: 'https://github.com/grafana/grafana/blob/main/LICENSE',               desc: 'Metrics dashboards' },
      { name: 'Node Exporter',      version: 'latest',   license: 'Apache 2.0',   url: 'https://github.com/prometheus/node_exporter/blob/master/LICENSE',    desc: 'Host metrics exporter' },
      { name: 'cAdvisor',           version: 'latest',   license: 'Apache 2.0',   url: 'https://github.com/google/cadvisor/blob/master/LICENSE',             desc: 'Container metrics exporter' },
    ],
  },
  {
    category: 'Backend',
    items: [
      { name: 'Python',             version: '3.12',     license: 'PSF',          url: 'https://docs.python.org/3/license.html',                             desc: 'Runtime language' },
      { name: 'FastAPI',            version: '0.x',      license: 'MIT',          url: 'https://github.com/fastapi/fastapi/blob/master/LICENSE',             desc: 'API framework' },
      { name: 'SQLAlchemy',         version: '2.x',      license: 'MIT',          url: 'https://github.com/sqlalchemy/sqlalchemy/blob/main/LICENSE',         desc: 'ORM / async DB access' },
      { name: 'Uvicorn',            version: '0.x',      license: 'BSD 3-Clause', url: 'https://github.com/encode/uvicorn/blob/master/LICENSE.md',           desc: 'ASGI server' },
      { name: 'httpx',              version: '0.x',      license: 'BSD 3-Clause', url: 'https://github.com/encode/httpx/blob/master/LICENSE.md',             desc: 'Async HTTP client' },
      { name: 'python-jose',        version: '3.x',      license: 'MIT',          url: 'https://github.com/mpdavis/python-jose/blob/master/LICENSE',         desc: 'JWT tokens' },
      { name: 'Cryptography',       version: '42+',      license: 'Apache 2.0',   url: 'https://github.com/pyca/cryptography/blob/main/LICENSE',             desc: 'DKIM key generation' },
      { name: 'ClamAV',             version: '1.x',      license: 'GPL v2',       url: 'https://www.clamav.net/about',                                       desc: 'Malware scanning (site containers)' },
    ],
  },
  {
    category: 'Frontend',
    items: [
      { name: 'React',              version: '18',       license: 'MIT',          url: 'https://github.com/facebook/react/blob/main/LICENSE',                desc: 'UI framework' },
      { name: 'Vite',               version: '5',        license: 'MIT',          url: 'https://github.com/vitejs/vite/blob/main/LICENSE',                   desc: 'Build tool' },
      { name: 'Tailwind CSS',       version: '3',        license: 'MIT',          url: 'https://github.com/tailwindlabs/tailwindcss/blob/master/LICENSE',    desc: 'Utility-first CSS' },
      { name: 'Lucide React',       version: '0.x',      license: 'ISC',          url: 'https://github.com/lucide-icons/lucide/blob/main/LICENSE',           desc: 'Icon library' },
      { name: 'xterm.js',           version: '5',        license: 'MIT',          url: 'https://github.com/xtermjs/xterm.js/blob/master/LICENSE',            desc: 'Browser terminal emulator' },
      { name: 'Axios',              version: '1.x',      license: 'MIT',          url: 'https://github.com/axios/axios/blob/v1.x/LICENSE',                   desc: 'HTTP client' },
    ],
  },
];

function LicensesCard() {
  return (
    <div className="space-y-6">
      <div className="card">
        <p className="text-xs text-ink-muted leading-relaxed">
          GnuKontrolR is built on open-source software. The following third-party components are
          used under their respective licenses. Click any license badge or service name to view
          the full license text.
        </p>
      </div>

      {SERVICES.map(group => (
        <div key={group.category} className="card space-y-1 p-0 overflow-hidden">
          <div className="px-4 py-2.5 bg-panel-800 border-b border-panel-subtle">
            <h3 className="text-xs font-semibold text-ink-muted uppercase tracking-wider">
              {group.category}
            </h3>
          </div>
          <div className="divide-y divide-panel-subtle">
            {group.items.map(item => (
              <div key={item.name} className="flex items-center gap-3 px-4 py-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-ink-primary">{item.name}</span>
                    <span className="text-xs text-ink-faint font-mono">{item.version}</span>
                  </div>
                  <p className="text-xs text-ink-muted mt-0.5 truncate">{item.desc}</p>
                </div>
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`shrink-0 inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border transition-opacity hover:opacity-80 ${LICENSE_BADGE[item.license] || 'bg-gray-500/15 text-gray-300 border-gray-500/30'}`}
                >
                  {item.license}
                  <ExternalLink size={9} />
                </a>
              </div>
            ))}
          </div>
        </div>
      ))}

      <p className="text-[11px] text-ink-faint text-center pb-2">
        This list covers direct runtime dependencies. Each package may have its own transitive dependencies under separate licenses.
      </p>
    </div>
  );
}

export default function SettingsPage() {
  const { user, refreshUser } = useAuth();
  const [tab, setTab] = useState('account');
  const [providers, setProviders] = useState([]);

  const loadProviders = async () => {
    try {
      const { data } = await api.get('/api/ai/providers');
      setProviders(data);
    } catch {
      setProviders([]);
    }
  };

  useEffect(() => {
    if (tab === 'ai_keys') loadProviders();
  }, [tab]);

  const isConfigured = id => providers.find(p => p.provider === id && p.configured === true);
  const isSuperadmin = user?.role === 'superadmin';

  const tabs = [
    { id: 'account',      label: 'Account',    icon: User,       show: true         },
    { id: 'ai_keys',      label: 'AI Keys',    icon: Key,        show: true         },
    { id: 'panel_config', label: 'Panel',      icon: Server,     show: isSuperadmin },
    { id: 'licenses',     label: 'Licenses',   icon: ScrollText, show: true         },
  ].filter(t => t.show);

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-xl font-bold text-white flex items-center gap-2">
        <Settings size={20} /> Settings
      </h1>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-panel-700">
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === t.id
                ? 'border-blue-500 text-white'
                : 'border-transparent text-gray-400 hover:text-gray-200'
            }`}
          >
            <t.icon size={14} />
            {t.label}
          </button>
        ))}
      </div>

      {/* Account tab */}
      {tab === 'account' && (
        <>
          {/* Read-only account info */}
          <div className="card space-y-4">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <User size={14} /> Account
            </h2>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div><span className="text-gray-400">Username</span><div className="text-white mt-1 font-mono">{user?.username}</div></div>
              <div><span className="text-gray-400">Email</span><div className="text-white mt-1">{user?.email}</div></div>
              <div><span className="text-gray-400">Role</span><div className="text-white mt-1 capitalize">{user?.role}</div></div>
              <div><span className="text-gray-400">Disk Quota</span><div className="text-white mt-1">{user?.disk_quota_mb} MB</div></div>
            </div>
          </div>

          {/* Personal & Contact Details */}
          <PersonalDetailsCard user={user} onSaved={refreshUser} />

          {/* Change Password */}
          <div className="card space-y-4">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2"><Lock size={14} />Change Password</h2>
            <input className="input" type="password" placeholder="Current password" />
            <input className="input" type="password" placeholder="New password" />
            <input className="input" type="password" placeholder="Confirm new password" />
            <button className="btn-primary">Update Password</button>
          </div>
        </>
      )}

      {/* AI Keys tab */}
      {tab === 'ai_keys' && (
        <div className="card space-y-0 p-0">
          <div className="px-5 py-3 bg-blue-500/10 border-b border-panel-700 rounded-t-lg">
            <p className="text-xs text-blue-300">
              Keys are encrypted and stored securely. They are never exposed after saving.
            </p>
          </div>
          <div className="px-5">
            <OpenCodeRow
              connected={!!isConfigured('opencode_account')}
              onRefresh={loadProviders}
            />
            {PROVIDERS.map(p => (
              <ProviderRow
                key={p.id}
                provider={p}
                configured={!!isConfigured(p.id)}
                onSaved={loadProviders}
              />
            ))}
          </div>
        </div>
      )}

      {/* Panel config tab — superadmin only */}
      {tab === 'panel_config' && isSuperadmin && <PanelConfigCard />}

      {/* Licenses tab */}
      {tab === 'licenses' && <LicensesCard />}
    </div>
  );
}
