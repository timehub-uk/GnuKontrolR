/**
 * Fail2banPanel — Admin-only fail2ban jail config and ban management.
 * Talks to /api/fail2ban/* endpoints.
 */
import { useState, useEffect } from 'react';
import {
  Shield, ShieldOff, Plus, Trash2, Loader, RefreshCw,
  CheckCircle, XCircle, Globe, Ban, ToggleLeft, ToggleRight,
} from 'lucide-react';
import api from '../utils/api';

// ── Jails panel ────────────────────────────────────────────────────────────────

function JailsPanel() {
  const [jails,   setJails]   = useState([]);
  const [loading, setLoading] = useState(false);
  const [adding,  setAdding]  = useState(false);
  const [busy,    setBusy]    = useState(null);
  const [appling, setAppling] = useState(false);
  const [form,    setForm]    = useState({
    name: '', enabled: true, maxretry: 5, findtime: 600,
    bantime: 3600, port: '', filter_name: '', logpath: '', comment: '',
  });

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/fail2ban/jails');
      setJails(data.jails || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggleJail = async (j) => {
    setBusy(j.id);
    try {
      const { data } = await api.patch(`/api/fail2ban/jails/${j.id}`, { enabled: !j.enabled });
      setJails(prev => prev.map(x => x.id === j.id ? data : x));
    } finally {
      setBusy(null);
    }
  };

  const deleteJail = async (j) => {
    if (!confirm(`Delete jail "${j.name}"?`)) return;
    setBusy(j.id);
    try {
      await api.delete(`/api/fail2ban/jails/${j.id}`);
      setJails(prev => prev.filter(x => x.id !== j.id));
    } finally {
      setBusy(null);
    }
  };

  const addJail = async () => {
    if (!form.name) return;
    try {
      const { data } = await api.post('/api/fail2ban/jails', form);
      setJails(prev => [...prev, data]);
      setAdding(false);
      setForm({ name: '', enabled: true, maxretry: 5, findtime: 600, bantime: 3600, port: '', filter_name: '', logpath: '', comment: '' });
    } catch (e) {
      alert(e?.response?.data?.detail || 'Create failed');
    }
  };

  const applyAll = async () => {
    setAppling(true);
    try {
      await api.post('/api/fail2ban/apply-all-jails');
      alert('All jail configs written and fail2ban reloaded');
    } catch (e) {
      alert(e?.response?.data?.detail || 'Apply failed');
    } finally {
      setAppling(false);
    }
  };

  const F = ({ label, field, type = 'text', ...props }) => (
    <div className="flex flex-col gap-0.5">
      <label className="text-[10px] text-gray-400">{label}</label>
      <input
        type={type}
        value={form[field]}
        onChange={e => setForm(f => ({ ...f, [field]: type === 'number' ? +e.target.value : e.target.value }))}
        className="input text-sm"
        {...props}
      />
    </div>
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 justify-between">
        <p className="text-[12px] text-gray-400">{jails.length} jails configured</p>
        <div className="flex gap-2">
          <button onClick={load} disabled={loading} className="btn-ghost text-xs flex items-center gap-1 px-2 py-1">
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          </button>
          <button onClick={applyAll} disabled={appling} className="btn-ghost text-xs flex items-center gap-1.5 px-3 py-1.5">
            {appling ? <Loader size={11} className="animate-spin" /> : <CheckCircle size={11} />}
            Apply All
          </button>
          <button onClick={() => setAdding(a => !a)} className="btn-primary text-xs flex items-center gap-1 px-3 py-1.5">
            <Plus size={11} /> Add Jail
          </button>
        </div>
      </div>

      {adding && (
        <div className="bg-panel-800 border border-brand-700/30 rounded-xl p-4 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <F label="Jail name" field="name" placeholder="e.g. nginx-http-auth" />
            <F label="Filter" field="filter_name" placeholder="nginx-http-auth" />
            <F label="Max retries" field="maxretry" type="number" />
            <F label="Find time (s)" field="findtime" type="number" />
            <F label="Ban time (s, -1=permanent)" field="bantime" type="number" />
            <F label="Port" field="port" placeholder="http,https" />
          </div>
          <F label="Log path" field="logpath" placeholder="/var/log/nginx/access.log" />
          <F label="Comment" field="comment" placeholder="Optional note" />
          <div className="flex gap-2">
            <button onClick={addJail} disabled={!form.name} className="btn-primary text-xs px-3 py-1.5">Create</button>
            <button onClick={() => setAdding(false)} className="btn-ghost text-xs px-3 py-1.5">Cancel</button>
          </div>
        </div>
      )}

      <div className="space-y-1.5">
        {jails.map(j => (
          <div key={j.id} className={`flex items-center justify-between px-3 py-2.5 rounded-xl border ${
            j.enabled ? 'bg-panel-800 border-panel-600' : 'bg-panel-900/50 border-panel-700/40 opacity-60'
          }`}>
            <div className="flex items-center gap-2.5 flex-1 min-w-0">
              <button onClick={() => toggleJail(j)} disabled={busy === j.id}>
                {j.enabled
                  ? <ToggleRight size={16} className="text-green-400" />
                  : <ToggleLeft  size={16} className="text-gray-500" />}
              </button>
              <div className="min-w-0">
                <p className="text-[12px] font-mono font-semibold text-white">{j.name}</p>
                <p className="text-[10px] text-gray-400">
                  retry:{j.maxretry} · find:{j.findtime}s · ban:{j.bantime === -1 ? '∞' : `${j.bantime}s`}
                  {j.port && ` · port:${j.port}`}
                </p>
              </div>
            </div>
            <button
              onClick={() => deleteJail(j)}
              disabled={busy === j.id}
              className="p-1.5 rounded text-gray-500 hover:text-red-400 hover:bg-red-900/20 transition-colors"
            >
              {busy === j.id ? <Loader size={11} className="animate-spin" /> : <Trash2 size={11} />}
            </button>
          </div>
        ))}
        {jails.length === 0 && !loading && (
          <p className="text-sm text-gray-400 text-center py-4">No jails configured.</p>
        )}
      </div>
    </div>
  );
}

// ── Bans panel ─────────────────────────────────────────────────────────────────

function BansPanel() {
  const [bans,     setBans]     = useState([]);
  const [loading,  setLoading]  = useState(false);
  const [adding,   setAdding]   = useState(false);
  const [busy,     setBusy]     = useState(null);
  const [form,     setForm]     = useState({ ip: '', jail: 'webpanel-manual', reason: '', bantime: 3600 });

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/fail2ban/bans');
      setBans(data.bans || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const addBan = async () => {
    if (!form.ip) return;
    try {
      const { data } = await api.post('/api/fail2ban/bans', form);
      setBans(prev => [data, ...prev]);
      setAdding(false);
      setForm({ ip: '', jail: 'webpanel-manual', reason: '', bantime: 3600 });
    } catch (e) {
      alert(e?.response?.data?.detail || 'Ban failed');
    }
  };

  const unban = async (id) => {
    setBusy(id);
    try {
      await api.delete(`/api/fail2ban/bans/${id}`);
      setBans(prev => prev.filter(b => b.id !== id));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 justify-between">
        <p className="text-[12px] text-gray-400">{bans.length} active bans</p>
        <div className="flex gap-2">
          <button onClick={load} disabled={loading} className="btn-ghost text-xs px-2 py-1">
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          </button>
          <button onClick={() => setAdding(a => !a)} className="btn-primary text-xs flex items-center gap-1 px-3 py-1.5">
            <Ban size={11} /> Ban IP
          </button>
        </div>
      </div>

      {adding && (
        <div className="bg-panel-800 border border-red-700/30 rounded-xl p-4 space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[10px] text-gray-400">IP Address</label>
              <input value={form.ip} onChange={e => setForm(f => ({ ...f, ip: e.target.value }))}
                placeholder="1.2.3.4" className="input w-full text-sm font-mono mt-0.5" />
            </div>
            <div>
              <label className="text-[10px] text-gray-400">Ban time (s, -1=permanent)</label>
              <input type="number" value={form.bantime} onChange={e => setForm(f => ({ ...f, bantime: +e.target.value }))}
                className="input w-full text-sm mt-0.5" />
            </div>
            <div className="col-span-2">
              <label className="text-[10px] text-gray-400">Reason (optional)</label>
              <input value={form.reason} onChange={e => setForm(f => ({ ...f, reason: e.target.value }))}
                placeholder="Manual ban — abuse" className="input w-full text-sm mt-0.5" />
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={addBan} disabled={!form.ip} className="btn-danger text-xs px-3 py-1.5">Apply Ban</button>
            <button onClick={() => setAdding(false)} className="btn-ghost text-xs px-3 py-1.5">Cancel</button>
          </div>
        </div>
      )}

      <div className="space-y-1.5 max-h-72 overflow-y-auto">
        {bans.map(b => (
          <div key={b.id} className="flex items-center justify-between px-3 py-2 rounded-xl bg-panel-800 border border-panel-600">
            <div>
              <p className="text-[12px] font-mono font-semibold text-red-300">{b.ip}</p>
              <p className="text-[10px] text-gray-400">
                {b.jail} · {b.reason || 'no reason'}
                {b.expires_at && ` · expires ${new Date(b.expires_at).toLocaleString()}`}
              </p>
            </div>
            <button onClick={() => unban(b.id)} disabled={busy === b.id}
              className="text-xs text-gray-400 hover:text-green-400 hover:bg-green-900/20 px-2 py-1 rounded transition-colors">
              {busy === b.id ? <Loader size={11} className="animate-spin" /> : 'Unban'}
            </button>
          </div>
        ))}
        {bans.length === 0 && !loading && (
          <p className="text-sm text-gray-400 text-center py-4">No active bans.</p>
        )}
      </div>
    </div>
  );
}

// ── Geo-block panel ────────────────────────────────────────────────────────────

function GeoBlockPanel() {
  const [rules,    setRules]    = useState([]);
  const [loading,  setLoading]  = useState(false);
  const [applying, setApplying] = useState(false);
  const [busy,     setBusy]     = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/fail2ban/geo-blocks');
      setRules(data.rules || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggle = async (r) => {
    setBusy(r.id);
    try {
      const { data } = await api.post('/api/fail2ban/geo-blocks', {
        country_code: r.country_code,
        country_name: r.country_name,
        blocked: !r.blocked,
      });
      setRules(prev => prev.map(x => x.id === r.id ? data : x));
    } finally {
      setBusy(null);
    }
  };

  const applyAll = async () => {
    setApplying(true);
    try {
      const { data } = await api.post('/api/fail2ban/geo-blocks/apply-all');
      alert(`Applied iptables ipset for ${data.applied?.length || 0} countries`);
      load();
    } catch (e) {
      alert(e?.response?.data?.detail || 'Apply failed');
    } finally {
      setApplying(false);
    }
  };

  const blocked = rules.filter(r => r.blocked);
  const allowed = rules.filter(r => !r.blocked);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-[12px] text-gray-400">
          {blocked.length} countries blocked (iptables ipset + Traefik double protection)
        </p>
        <div className="flex gap-2">
          <button onClick={load} disabled={loading} className="btn-ghost text-xs px-2 py-1">
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          </button>
          <button onClick={applyAll} disabled={applying || blocked.length === 0} className="btn-primary text-xs flex items-center gap-1.5 px-3 py-1.5">
            {applying ? <Loader size={11} className="animate-spin" /> : <Globe size={11} />}
            Apply ipset
          </button>
        </div>
      </div>

      {blocked.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-red-400">Blocked</p>
          {blocked.map(r => (
            <div key={r.id} className="flex items-center justify-between px-3 py-2 rounded-xl bg-red-900/15 border border-red-800/30">
              <div className="flex items-center gap-2">
                <ShieldOff size={12} className="text-red-400 flex-shrink-0" />
                <span className="text-[12px] font-semibold text-red-200">{r.country_name}</span>
                <span className="text-[10px] font-mono text-red-400">{r.country_code}</span>
                {r.ipset_applied && (
                  <span className="text-[9px] bg-red-900/30 border border-red-700/40 px-1.5 py-0.5 rounded text-red-300">ipset</span>
                )}
              </div>
              <button onClick={() => toggle(r)} disabled={busy === r.id}
                className="text-xs text-gray-400 hover:text-green-400 px-2 py-0.5 rounded transition-colors">
                {busy === r.id ? <Loader size={10} className="animate-spin" /> : 'Unblock'}
              </button>
            </div>
          ))}
        </div>
      )}

      {rules.length === 0 && !loading && (
        <p className="text-sm text-gray-400 text-center py-4">
          No geo-block rules. Use the country blocking in Networking → Domain Access Rules to block countries,
          then click "Apply ipset" here to enforce at the server firewall level.
        </p>
      )}
    </div>
  );
}

// ── Main ───────────────────────────────────────────────────────────────────────

const F2B_TABS = [
  { id: 'jails',    label: 'Jails',     icon: Shield },
  { id: 'bans',     label: 'Bans',      icon: Ban },
  { id: 'geoblock', label: 'Geo Block', icon: Globe },
];

export default function Fail2banPanel() {
  const [tab, setTab] = useState('jails');

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-xl bg-orange-900/30 flex items-center justify-center">
          <Shield size={16} className="text-orange-400" />
        </div>
        <div>
          <h2 className="text-[15px] font-bold text-white">Fail2ban</h2>
          <p className="text-[11px] text-gray-400">Jail config, active bans, global geo-blocking via iptables ipset</p>
        </div>
      </div>

      <div className="flex gap-1 bg-panel-800 border border-panel-600 rounded-xl p-1 w-fit">
        {F2B_TABS.map(({ id, label, icon: Icon }) => (
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

      {tab === 'jails'    && <JailsPanel />}
      {tab === 'bans'     && <BansPanel />}
      {tab === 'geoblock' && <GeoBlockPanel />}
    </div>
  );
}
