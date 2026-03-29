/**
 * SecurityPage
 * Central security command centre for the panel.
 *
 * Sections:
 *   1. Fleet overview  — score ring + severity breakdown across all domains
 *   2. Domain audit    — per-domain live SecurityAdvisor (checks, auto-fix)
 *   3. Firewall        — open-port summary per domain
 *   4. SSL overview    — certificate expiry status across all domains
 *   5. Security log    — recent 401 / 403 / 5xx events from the activity log
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Shield, ShieldCheck, ShieldAlert, ShieldOff,
  Globe, Lock, Unlock, RefreshCw, AlertTriangle,
  CheckCircle, XCircle, Clock, Loader, AlertCircle,
  Flame, Eye, Network,
} from 'lucide-react';
import api from '../utils/api';
import SecurityAdvisor from '../components/SecurityAdvisor';
import SecurityScanner from '../components/SecurityScanner';
import EmailSecurityPanel from '../components/EmailSecurityPanel';
import CveFeed from '../components/CveFeed';
import Fail2banPanel from '../components/Fail2banPanel';

// ── Helpers ───────────────────────────────────────────────────────────────────

function scoreColor(s) {
  if (s >= 90) return 'text-green-400';
  if (s >= 70) return 'text-yellow-400';
  if (s >= 50) return 'text-orange-400';
  return 'text-red-400';
}
function scoreBg(s) {
  if (s >= 90) return 'bg-green-900/20 border-green-800';
  if (s >= 70) return 'bg-yellow-900/20 border-yellow-800';
  if (s >= 50) return 'bg-orange-900/20 border-orange-800';
  return 'bg-red-900/20 border-red-800';
}

function MiniRing({ score, size = 40 }) {
  const r = size * 0.38;
  const c = 2 * Math.PI * r;
  const off = c - (score / 100) * c;
  const stroke = score >= 80 ? '#22c55e' : score >= 60 ? '#eab308' : '#f97316';
  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg className="absolute inset-0 -rotate-90" viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#1f2937" strokeWidth="3" />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={stroke}
          strokeWidth="3" strokeDasharray={c} strokeDashoffset={off}
          strokeLinecap="round" className="transition-all duration-700" />
      </svg>
      <span className={`text-xs font-bold z-10 ${scoreColor(score)}`}>{score}</span>
    </div>
  );
}

// ── 1. Fleet overview ─────────────────────────────────────────────────────────

function FleetOverview({ domains }) {
  const [scores,  setScores]  = useState({});   // domain → {score, checks}
  const [loading, setLoading] = useState(false);
  const [done,    setDone]    = useState(false);

  const scan = useCallback(async () => {
    if (!domains.length) return;
    setLoading(true);
    setDone(false);
    setScores({});
    const results = await Promise.allSettled(
      domains.map(d =>
        api.get(`/api/security/check/${d}`)
          .then(r => ({ domain: d, ...r.data }))
          .catch(() => ({ domain: d, score: 0, checks: [] }))
      )
    );
    const map = {};
    results.forEach(r => { if (r.status === 'fulfilled') map[r.value.domain] = r.value; });
    setScores(map);
    setLoading(false);
    setDone(true);
  }, [domains]);

  useEffect(() => { if (domains.length) scan(); }, [domains, scan]);

  const list    = Object.values(scores);
  const avg     = list.length ? Math.round(list.reduce((a, b) => a + b.score, 0) / list.length) : 0;
  const critical = list.reduce((n, d) => n + (d.checks?.filter(c => c.severity === 'critical').length || 0), 0);
  const high     = list.reduce((n, d) => n + (d.checks?.filter(c => c.severity === 'high').length || 0), 0);
  const atRisk   = list.filter(d => d.score < 70).length;

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-white flex items-center gap-2">
          <Shield size={16} className="text-brand-400" /> Fleet Security Overview
        </h2>
        <button onClick={scan} disabled={loading} className="btn-ghost text-xs flex items-center gap-1.5">
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Scanning…' : 'Scan all'}
        </button>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Avg score',    value: done ? avg : '—',     color: done ? scoreColor(avg) : 'text-gray-500', icon: Shield },
          { label: 'Critical',     value: done ? critical : '—', color: critical > 0 ? 'text-red-400' : 'text-green-400', icon: ShieldOff },
          { label: 'High',         value: done ? high : '—',     color: high > 0 ? 'text-orange-400' : 'text-green-400', icon: ShieldAlert },
          { label: 'At risk (<70)',value: done ? atRisk : '—',   color: atRisk > 0 ? 'text-yellow-400' : 'text-green-400', icon: AlertTriangle },
        ].map(({ label, value, color, icon: Icon }) => (
          <div key={label} className="bg-panel-700/40 rounded-xl p-3 flex items-center gap-3">
            <Icon size={18} className={color} />
            <div>
              <div className={`text-lg font-bold ${color}`}>{value}</div>
              <div className="text-xs text-gray-500">{label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Per-domain mini scores */}
      {done && list.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          {list.map(d => (
            <div key={d.domain} className={`flex items-center gap-2.5 rounded-lg border px-3 py-2 ${scoreBg(d.score)}`}>
              <MiniRing score={d.score} size={36} />
              <div className="min-w-0">
                <p className="text-xs font-medium text-gray-200 truncate">{d.domain}</p>
                <p className="text-xs text-gray-500">
                  {d.checks?.filter(c => c.severity !== 'pass').length || 0} issues
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-sm text-gray-500 py-2">
          <Loader size={14} className="animate-spin" />
          Scanning {domains.length} domain{domains.length !== 1 ? 's' : ''}…
        </div>
      )}
    </div>
  );
}

// ── 2. SSL overview ───────────────────────────────────────────────────────────

function SslOverview({ domains }) {
  const [certs,   setCerts]   = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!domains.length) return;
    setLoading(true);
    Promise.allSettled(
      domains.map(d =>
        api.get(`/api/security/check/${d}`)
          .then(r => {
            const ssl = r.data.checks?.find(c => c.id === 'ssl_expiry' || c.id === 'ssl_valid');
            return { domain: d, check: ssl || null };
          })
          .catch(() => ({ domain: d, check: null }))
      )
    ).then(results => {
      setCerts(results.filter(r => r.status === 'fulfilled').map(r => r.value));
      setLoading(false);
    });
  }, [domains]);

  const icon = (sev) => {
    if (sev === 'pass')     return <CheckCircle size={14} className="text-green-400" />;
    if (sev === 'critical') return <XCircle     size={14} className="text-red-400" />;
    if (sev === 'high')     return <AlertCircle size={14} className="text-orange-400" />;
    return                         <Clock       size={14} className="text-yellow-400" />;
  };

  return (
    <div className="card">
      <h2 className="font-semibold text-white flex items-center gap-2 mb-3">
        <Lock size={16} className="text-brand-400" /> SSL Certificate Status
      </h2>
      {loading ? (
        <p className="text-sm text-gray-500 flex items-center gap-2"><Loader size={13} className="animate-spin" /> Checking…</p>
      ) : certs.length === 0 ? (
        <p className="text-sm text-gray-500">No domains found.</p>
      ) : (
        <div className="divide-y divide-panel-700">
          {certs.map(({ domain, check }) => (
            <div key={domain} className="flex items-center justify-between py-2.5">
              <div className="flex items-center gap-2">
                <Globe size={13} className="text-gray-500" />
                <span className="text-sm text-gray-200">{domain}</span>
              </div>
              <div className="flex items-center gap-2">
                {check ? (
                  <>
                    {icon(check.severity)}
                    <span className={`text-xs ${check.severity === 'pass' ? 'text-green-400' : 'text-orange-400'}`}>
                      {check.message || check.title}
                    </span>
                  </>
                ) : (
                  <span className="text-xs text-gray-600">Not checked</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── 3. Security event feed ────────────────────────────────────────────────────

function SecurityEventFeed() {
  const [events,  setEvents]  = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchErr, setFetchErr] = useState(null);

  useEffect(() => {
    api.get('/api/log/me?limit=200')
      .then(r => {
        const security = (r.data.entries || [])
          .filter(e => [401, 403, 429, 500, 503].includes(e.status))
          .slice(0, 50);
        setEvents(security);
        setFetchErr(null);
      })
      .catch(err => {
        setFetchErr(err?.response?.data?.detail || 'Failed to load security events.');
      })
      .finally(() => setLoading(false));
  }, []);

  const statusStyle = {
    401: 'text-red-400 bg-red-900/20',
    403: 'text-red-400 bg-red-900/20',
    429: 'text-orange-400 bg-orange-900/20',
    500: 'text-yellow-400 bg-yellow-900/20',
    503: 'text-yellow-400 bg-yellow-900/20',
  };
  const statusLabel = {
    401: 'Auth failure',
    403: 'Forbidden',
    429: 'Rate limited',
    500: 'Server error',
    503: 'Unavailable',
  };

  return (
    <div className="card">
      <h2 className="font-semibold text-white flex items-center gap-2 mb-3">
        <Flame size={16} className="text-orange-400" /> Security Events
        {events.length > 0 && (
          <span className="text-xs px-1.5 py-0.5 rounded bg-orange-900/30 text-orange-400">
            {events.length}
          </span>
        )}
      </h2>
      {loading ? (
        <p className="text-sm text-gray-500 flex items-center gap-2"><Loader size={13} className="animate-spin" /> Loading…</p>
      ) : fetchErr ? (
        <p className="text-sm text-red-400">{fetchErr}</p>
      ) : events.length === 0 ? (
        <div className="text-center py-4">
          <ShieldCheck size={18} className="mx-auto mb-1.5 text-green-500" />
          <p className="text-sm text-gray-500">No security events recorded.</p>
        </div>
      ) : (
        <div className="space-y-1.5 max-h-64 overflow-y-auto">
          {events.map((e, i) => (
            <div key={i} className="flex items-center gap-3 py-1.5 text-xs border-b border-panel-700 last:border-0">
              <span className={`px-1.5 py-0.5 rounded font-mono font-medium flex-shrink-0 ${statusStyle[e.status] || 'text-gray-400 bg-panel-700'}`}>
                {statusLabel[e.status] || e.status}
              </span>
              <span className="font-mono text-gray-400 truncate flex-1">{e.method} {e.path}</span>
              <span className="text-gray-600 flex-shrink-0">{new Date(e.timestamp).toLocaleTimeString()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function SecurityPage() {
  const [domains,  setDomains]  = useState([]);
  const [selected, setSelected] = useState('');
  const [tab,      setTab]      = useState('audit');

  useEffect(() => {
    api.get('/api/domains')
      .then(r => {
        const list = (r.data?.domains || r.data || []).map(d => d.name || d);
        setDomains(list);
        if (list.length && !selected) setSelected(list[0]);
      })
      .catch(() => {});
  }, []);

  const tabs = [
    { id: 'audit',   label: 'Domain Audit',    icon: Eye },
    { id: 'fleet',   label: 'Fleet Overview',  icon: Shield },
    { id: 'ssl',     label: 'SSL Status',       icon: Lock },
    { id: 'events',  label: 'Security Events', icon: Flame },
    { id: 'scanner', label: 'AV Scanner',      icon: ShieldAlert },
    { id: 'email',   label: 'Email Security',  icon: Network },
    { id: 'fail2ban',label: 'Fail2ban',        icon: ShieldOff },
    { id: 'cve',     label: 'CVE Feed',        icon: AlertCircle },
  ];

  return (
    <div className="space-y-5">
      {/* Page header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Shield size={20} className="text-brand-400" /> Security
        </h1>

        {/* Domain selector — shown on audit and scanner tabs */}
        {(tab === 'audit' || tab === 'scanner') && (
          <select
            value={selected}
            onChange={e => setSelected(e.target.value)}
            className="input w-56"
          >
            {domains.length === 0 && <option value="">No domains</option>}
            {domains.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        )}
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-panel-800 border border-panel-600 rounded-xl p-1 w-fit">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${
              tab === id
                ? 'bg-brand-600/30 text-brand-300 font-medium'
                : 'text-gray-400 hover:text-white hover:bg-panel-700'
            }`}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'audit' && (
        <SecurityAdvisor domain={selected} />
      )}

      {tab === 'fleet' && (
        <FleetOverview domains={domains} />
      )}

      {tab === 'ssl' && (
        <SslOverview domains={domains} />
      )}

      {tab === 'events' && (
        <SecurityEventFeed />
      )}

      {tab === 'scanner' && (
        <SecurityScanner domain={selected} />
      )}

      {tab === 'email' && (
        <EmailSecurityPanel domains={domains} />
      )}

      {tab === 'fail2ban' && (
        <Fail2banPanel />
      )}

      {tab === 'cve' && (
        <CveFeed />
      )}
    </div>
  );
}
