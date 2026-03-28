import { useState, useEffect } from 'react';
import { Settings, Key, User, Lock, CheckCircle, ExternalLink, Contact } from 'lucide-react';
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
      setMsg({ type: 'err', text: err.response?.data?.detail || 'Save failed.' });
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

  const tabs = [
    { id: 'account', label: 'Account',  icon: User },
    { id: 'ai_keys', label: 'AI Keys',  icon: Key  },
  ];

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
          {/* Notice banner */}
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
    </div>
  );
}
