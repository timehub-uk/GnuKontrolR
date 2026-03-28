/**
 * EmailSecurityPanel — SBL/DNSBL blacklist management and email policy.
 * Admin endpoints require admin role; domain policy/events visible to owners.
 */
import { useState, useEffect } from 'react';
import {
  Mail, ShieldCheck, ShieldAlert, Search, RefreshCw, Loader,
  CheckCircle, XCircle, Plus, Trash2, AlertTriangle, ToggleLeft, ToggleRight,
} from 'lucide-react';
import api from '../utils/api';

// ── IP Check panel ─────────────────────────────────────────────────────────────

function IPCheckPanel() {
  const [ip,      setIp]      = useState('');
  const [loading, setLoading] = useState(false);
  const [result,  setResult]  = useState(null);
  const [error,   setError]   = useState('');

  const check = async () => {
    if (!ip.trim()) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const { data } = await api.post('/api/email-security/check', { ip: ip.trim() });
      setResult(data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Check failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-[12px] text-gray-400">
        Query all enabled DNSBL lists to check if an IP is blacklisted.
        Results are cached for 1 hour.
      </p>
      <div className="flex gap-2">
        <input
          value={ip}
          onChange={e => setIp(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && check()}
          placeholder="IP address (e.g. 192.168.1.1)"
          className="input flex-1 font-mono text-sm"
        />
        <button
          onClick={check}
          disabled={loading || !ip.trim()}
          className="btn-primary flex items-center gap-1.5 px-4 py-1.5 text-sm"
        >
          {loading ? <Loader size={13} className="animate-spin" /> : <Search size={13} />}
          Check
        </button>
      </div>

      {error && (
        <div className="text-red-400 bg-red-900/15 border border-red-800/30 rounded-xl px-4 py-2.5 text-sm">
          {error}
        </div>
      )}

      {result && (
        <div className={`rounded-xl border p-4 space-y-3 ${
          result.listed_on > 0
            ? 'bg-red-900/15 border-red-800/40'
            : 'bg-green-900/15 border-green-800/40'
        }`}>
          <div className="flex items-center gap-3">
            {result.listed_on > 0
              ? <ShieldAlert size={18} className="text-red-400" />
              : <ShieldCheck size={18} className="text-green-400" />}
            <div>
              <p className={`font-semibold text-sm ${result.listed_on > 0 ? 'text-red-300' : 'text-green-300'}`}>
                {result.listed_on > 0
                  ? `Listed on ${result.listed_on} of ${result.total_checked} DNSBL lists`
                  : `Clean — not found on any of ${result.total_checked} DNSBL lists`}
              </p>
              <p className="text-[11px] text-gray-400">IP: {result.ip}</p>
            </div>
          </div>

          {result.blacklisted?.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-red-400">Blacklisted on:</p>
              {result.blacklisted.map((b, i) => (
                <div key={i} className="flex items-center justify-between text-[11px] bg-red-900/20 rounded-lg px-3 py-1.5">
                  <span className="text-red-200 font-semibold">{b.name}</span>
                  <span className="font-mono text-red-400">{b.return_code}</span>
                </div>
              ))}
            </div>
          )}

          <details className="text-[10px]">
            <summary className="cursor-pointer text-gray-400 hover:text-gray-200">All results ({result.results?.length})</summary>
            <div className="mt-2 space-y-0.5 max-h-48 overflow-y-auto">
              {result.results?.map((r, i) => (
                <div key={i} className="flex items-center gap-2 px-2 py-1 rounded">
                  {r.listed
                    ? <XCircle size={9} className="text-red-400 flex-shrink-0" />
                    : <CheckCircle size={9} className="text-green-400 flex-shrink-0" />}
                  <span className="text-gray-300 flex-1 truncate">{r.name}</span>
                  <span className="font-mono text-gray-500">{r.zone}</span>
                  {r.cached && <span className="text-blue-500 opacity-60">cached</span>}
                </div>
              ))}
            </div>
          </details>
        </div>
      )}
    </div>
  );
}

// ── DNSBL list management ──────────────────────────────────────────────────────

function DnsblListPanel() {
  const [lists,   setLists]   = useState([]);
  const [loading, setLoading] = useState(false);
  const [adding,  setAdding]  = useState(false);
  const [form,    setForm]    = useState({ name: '', zone: '', description: '', weight: 1.0 });
  const [busy,    setBusy]    = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/email-security/dnsbl');
      setLists(data.lists || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggle = async (id, enabled) => {
    setBusy(id);
    try {
      await api.patch(`/api/email-security/dnsbl/${id}`, { enabled: !enabled });
      setLists(prev => prev.map(l => l.id === id ? { ...l, enabled: !enabled } : l));
    } finally {
      setBusy(null);
    }
  };

  const remove = async (id) => {
    if (!confirm('Remove this DNSBL list?')) return;
    setBusy(id);
    try {
      await api.delete(`/api/email-security/dnsbl/${id}`);
      setLists(prev => prev.filter(l => l.id !== id));
    } finally {
      setBusy(null);
    }
  };

  const add = async () => {
    if (!form.name || !form.zone) return;
    try {
      const { data } = await api.post('/api/email-security/dnsbl', form);
      setLists(prev => [...prev, data]);
      setAdding(false);
      setForm({ name: '', zone: '', description: '', weight: 1.0 });
    } catch (e) {
      alert(e?.response?.data?.detail || 'Add failed');
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <p className="text-[12px] text-gray-400">
          {lists.length} DNSBL/RBL services configured.
        </p>
        <div className="flex gap-2">
          <button onClick={load} disabled={loading} className="btn-ghost text-xs flex items-center gap-1 px-2 py-1">
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          </button>
          <button onClick={() => setAdding(a => !a)} className="btn-primary text-xs flex items-center gap-1 px-3 py-1">
            <Plus size={11} /> Add List
          </button>
        </div>
      </div>

      {adding && (
        <div className="bg-panel-800 border border-brand-700/30 rounded-xl p-4 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="Name (e.g. Spamhaus ZEN)" className="input text-sm col-span-1" />
            <input value={form.zone} onChange={e => setForm(f => ({ ...f, zone: e.target.value }))}
              placeholder="Zone (e.g. zen.spamhaus.org)" className="input text-sm font-mono col-span-1" />
            <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              placeholder="Description (optional)" className="input text-sm col-span-2" />
          </div>
          <div className="flex gap-2">
            <button onClick={add} disabled={!form.name || !form.zone}
              className="btn-primary text-xs px-3 py-1.5">Add</button>
            <button onClick={() => setAdding(false)} className="btn-ghost text-xs px-3 py-1.5">Cancel</button>
          </div>
        </div>
      )}

      <div className="space-y-1.5">
        {lists.map(l => (
          <div key={l.id} className={`flex items-center justify-between px-3 py-2 rounded-xl border transition-colors ${
            l.enabled ? 'bg-panel-800 border-panel-600' : 'bg-panel-900/50 border-panel-700/50 opacity-60'
          }`}>
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <button onClick={() => toggle(l.id, l.enabled)} disabled={busy === l.id}>
                {l.enabled
                  ? <ToggleRight size={16} className="text-green-400" />
                  : <ToggleLeft  size={16} className="text-gray-500" />}
              </button>
              <div className="min-w-0">
                <p className="text-[12px] font-semibold text-white truncate">{l.name}</p>
                <p className="text-[10px] text-gray-400 font-mono truncate">{l.zone}</p>
              </div>
            </div>
            <button
              onClick={() => remove(l.id)}
              disabled={busy === l.id}
              className="p-1.5 rounded text-gray-500 hover:text-red-400 hover:bg-red-900/20 transition-colors flex-shrink-0"
            >
              {busy === l.id ? <Loader size={11} className="animate-spin" /> : <Trash2 size={11} />}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Email policy per domain ────────────────────────────────────────────────────

function PolicyPanel({ domains }) {
  const [domain,  setDomain]  = useState(domains[0] || '');
  const [policy,  setPolicy]  = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving,  setSaving]  = useState(false);
  const [dirty,   setDirty]   = useState({});

  useEffect(() => {
    if (!domain) return;
    setLoading(true);
    api.get(`/api/email-security/policy/${domain}`)
      .then(r => { setPolicy(r.data); setDirty({}); })
      .catch(() => setPolicy(null))
      .finally(() => setLoading(false));
  }, [domain]);

  const update = (key, val) => {
    setPolicy(p => ({ ...p, [key]: val }));
    setDirty(d => ({ ...d, [key]: val }));
  };

  const save = async () => {
    if (!Object.keys(dirty).length) return;
    setSaving(true);
    try {
      const { data } = await api.patch(`/api/email-security/policy/${domain}`, dirty);
      setPolicy(data);
      setDirty({});
    } catch (e) {
      alert(e?.response?.data?.detail || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const Toggle = ({ label, field }) => (
    <label className="flex items-center justify-between cursor-pointer select-none py-1.5">
      <span className="text-[13px] text-gray-300">{label}</span>
      <button onClick={() => update(field, !policy[field])}>
        {policy?.[field]
          ? <ToggleRight size={20} className="text-green-400" />
          : <ToggleLeft  size={20} className="text-gray-500" />}
      </button>
    </label>
  );

  return (
    <div className="space-y-3">
      <select value={domain} onChange={e => setDomain(e.target.value)} className="input w-56 text-sm">
        {domains.map(d => <option key={d} value={d}>{d}</option>)}
      </select>

      {loading && <div className="flex justify-center py-4"><Loader size={18} className="animate-spin text-brand-400" /></div>}

      {policy && !loading && (
        <div className="bg-panel-800 border border-panel-600 rounded-xl p-4 space-y-2">
          <Toggle label="DNSBL check (reject blacklisted senders)" field="dnsbl_check" />
          {policy.dnsbl_check && (
            <div className="flex items-center gap-2 pl-2 pb-1">
              <span className="text-[11px] text-gray-400">Action:</span>
              {['reject', 'defer', 'flag'].map(a => (
                <button
                  key={a}
                  onClick={() => update('dnsbl_action', a)}
                  className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
                    policy.dnsbl_action === a
                      ? 'bg-brand-600/25 border-brand-500/40 text-brand-300'
                      : 'bg-panel-700 border-panel-600 text-gray-400'
                  }`}
                >
                  {a}
                </button>
              ))}
            </div>
          )}
          <Toggle label="SPF check" field="spf_check" />
          <Toggle label="DKIM check" field="dkim_check" />
          <Toggle label="DMARC check" field="dmarc_check" />
          <Toggle label="Greylisting (defer first-time senders)" field="greylist" />
          <div className="flex items-center gap-2 py-1">
            <span className="text-[13px] text-gray-300">Outbound rate limit (per hour):</span>
            <input
              type="number"
              min={10} max={10000}
              value={policy.rate_limit_per_hour}
              onChange={e => update('rate_limit_per_hour', parseInt(e.target.value, 10))}
              className="input w-24 text-sm"
            />
          </div>
          {Object.keys(dirty).length > 0 && (
            <button onClick={save} disabled={saving}
              className="btn-primary w-full flex items-center justify-center gap-1.5 py-1.5 text-sm mt-2">
              {saving ? <Loader size={12} className="animate-spin" /> : <CheckCircle size={12} />}
              Save Policy
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── SBL events log ─────────────────────────────────────────────────────────────

function EventsPanel({ domains }) {
  const [domain,  setDomain]  = useState('');
  const [events,  setEvents]  = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/email-security/events', {
        params: { limit: 100, ...(domain ? { domain } : {}) },
      });
      setEvents(data.events || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [domain]);

  const ACTION_COLORS = {
    rejected: 'text-red-400 bg-red-900/15 border-red-800/30',
    deferred: 'text-yellow-400 bg-yellow-900/15 border-yellow-800/30',
    flagged:  'text-orange-400 bg-orange-900/15 border-orange-800/30',
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <select value={domain} onChange={e => setDomain(e.target.value)} className="input w-48 text-sm">
          <option value="">All domains</option>
          {domains.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
        <button onClick={load} disabled={loading} className="btn-ghost text-xs flex items-center gap-1 px-3 py-1.5">
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {events.length === 0 && !loading && (
        <p className="text-sm text-gray-400 py-4 text-center">No SBL events recorded.</p>
      )}

      <div className="space-y-1.5 max-h-80 overflow-y-auto">
        {events.map(e => (
          <div key={e.id} className={`flex items-center justify-between px-3 py-2 rounded-xl border text-[11px] ${ACTION_COLORS[e.action] || 'text-gray-400 bg-panel-800 border-panel-600'}`}>
            <div className="flex items-center gap-3 min-w-0">
              <span className="font-semibold uppercase text-[9px] flex-shrink-0">{e.action}</span>
              <span className="font-mono text-gray-200 flex-shrink-0">{e.ip}</span>
              {e.sender && <span className="text-gray-400 truncate">{e.sender}</span>}
              {e.dnsbl_zone && <span className="text-gray-500 font-mono truncate">{e.dnsbl_zone}</span>}
            </div>
            <span className="text-gray-500 flex-shrink-0 ml-2">
              {e.occurred_at ? new Date(e.occurred_at).toLocaleString() : ''}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

const EMAIL_SEC_TABS = [
  { id: 'check',  label: 'IP Check',   icon: Search },
  { id: 'lists',  label: 'DNSBL Lists', icon: ShieldAlert },
  { id: 'policy', label: 'Policy',     icon: ShieldCheck },
  { id: 'events', label: 'SBL Events', icon: AlertTriangle },
];

export default function EmailSecurityPanel({ domains = [] }) {
  const [tab, setTab] = useState('check');

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-xl bg-blue-900/30 flex items-center justify-center">
          <Mail size={16} className="text-blue-400" />
        </div>
        <div>
          <h2 className="text-[15px] font-bold text-white">Email Security (SBL/DNSBL)</h2>
          <p className="text-[11px] text-gray-400">Blacklist checking, policy enforcement, abuse prevention</p>
        </div>
      </div>

      <div className="flex gap-1 bg-panel-800 border border-panel-600 rounded-xl p-1 w-fit flex-wrap">
        {EMAIL_SEC_TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-colors ${
              tab === id
                ? 'bg-brand-600/30 text-brand-300 font-medium'
                : 'text-gray-400 hover:text-white hover:bg-panel-700'
            }`}
          >
            <Icon size={12} /> {label}
          </button>
        ))}
      </div>

      {tab === 'check'  && <IPCheckPanel />}
      {tab === 'lists'  && <DnsblListPanel />}
      {tab === 'policy' && <PolicyPanel domains={domains} />}
      {tab === 'events' && <EventsPanel domains={domains} />}
    </div>
  );
}
