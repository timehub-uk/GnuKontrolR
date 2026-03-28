/**
 * SecurityScanner — Admin-only antivirus, malware heuristics, and file sanitizer.
 * Talks to /api/scanner/* endpoints.
 */
import { useState, useEffect } from 'react';
import {
  ShieldAlert, ShieldCheck, ScanLine, Trash2, Loader, AlertTriangle,
  CheckCircle, XCircle, FileWarning, Archive, RefreshCw, Bug, Wrench,
} from 'lucide-react';
import api from '../utils/api';

const AREAS = ['public', 'uploads', 'private', 'all'];

const SEVERITY_COLORS = {
  critical: 'text-red-400 bg-red-900/20 border-red-800/40',
  high:     'text-orange-400 bg-orange-900/20 border-orange-800/40',
  medium:   'text-yellow-400 bg-yellow-900/20 border-yellow-800/40',
  low:      'text-blue-400 bg-blue-900/20 border-blue-800/40',
};

const DETECTION_LABELS = {
  clamav:    { label: 'ClamAV', cls: 'text-purple-300 bg-purple-900/20 border-purple-700/30' },
  heuristic: { label: 'Heuristic', cls: 'text-yellow-300 bg-yellow-900/20 border-yellow-700/30' },
  manual:    { label: 'Manual', cls: 'text-gray-300 bg-gray-800/20 border-gray-700/30' },
};

// ── Scan Jobs panel ────────────────────────────────────────────────────────────

function ScanPanel({ domain }) {
  const [area,    setArea]    = useState('all');
  const [running, setRunning] = useState(false);
  const [jobs,    setJobs]    = useState([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState('');

  const loadJobs = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/scanner/jobs', { params: domain ? { domain } : {} });
      setJobs(data.jobs || []);
    } catch {
      setError('Could not load scan history');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadJobs(); }, [domain]);

  const startScan = async () => {
    if (!domain) return;
    setRunning(true);
    setError('');
    try {
      await api.post('/api/scanner/scan', { domain, area });
      await loadJobs();
    } catch (e) {
      setError(e?.response?.data?.detail || 'Scan failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <select
          value={area}
          onChange={e => setArea(e.target.value)}
          className="input w-36 text-sm"
        >
          {AREAS.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <button
          onClick={startScan}
          disabled={running || !domain}
          className="btn-primary flex items-center gap-1.5 px-4 py-1.5 text-sm"
        >
          {running ? <Loader size={13} className="animate-spin" /> : <ScanLine size={13} />}
          {running ? 'Scanning…' : 'Run ClamAV Scan'}
        </button>
        <button
          onClick={loadJobs}
          disabled={loading}
          className="btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-sm"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 text-red-400 bg-red-900/15 border border-red-800/30 rounded-xl px-4 py-2.5 text-sm">
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {jobs.length === 0 && !loading && (
        <p className="text-sm text-gray-400 py-4 text-center">No scan jobs yet.</p>
      )}

      <div className="space-y-2">
        {jobs.map(j => (
          <div key={j.id} className="bg-panel-800 border border-panel-600 rounded-xl p-3 space-y-1.5">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                {j.status === 'running' && <Loader size={13} className="animate-spin text-brand-400" />}
                {j.status === 'done'    && (j.infected > 0
                  ? <ShieldAlert size={13} className="text-red-400" />
                  : <ShieldCheck size={13} className="text-green-400" />)}
                {j.status === 'failed'  && <XCircle size={13} className="text-red-500" />}
                <span className="text-sm font-semibold text-white">{j.domain} / {j.area}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded border font-mono ${
                  j.status === 'done'   ? 'text-green-300 bg-green-900/20 border-green-800/30' :
                  j.status === 'failed' ? 'text-red-300 bg-red-900/20 border-red-800/30' :
                  'text-blue-300 bg-blue-900/20 border-blue-800/30'
                }`}>{j.status}</span>
              </div>
              <span className="text-[11px] text-gray-400">
                {j.started_at ? new Date(j.started_at).toLocaleString() : ''}
              </span>
            </div>
            <div className="flex items-center gap-4 text-[11px] text-gray-400">
              <span className="text-green-400">✓ {j.clean} clean</span>
              {j.infected > 0 && <span className="text-red-400 font-semibold">⚠ {j.infected} infected</span>}
              {j.errors > 0   && <span className="text-orange-400">! {j.errors} errors</span>}
            </div>
            {j.summary?.length > 0 && j.infected > 0 && (
              <ul className="text-[11px] font-mono text-red-300 pl-2 space-y-0.5 max-h-20 overflow-y-auto">
                {j.summary.filter(s => s.threat).map((s, i) => (
                  <li key={i}>⚠ {s.file} — {s.threat}</li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Malware Alerts panel ───────────────────────────────────────────────────────

function AlertsPanel({ domain }) {
  const [alerts,   setAlerts]   = useState([]);
  const [loading,  setLoading]  = useState(false);
  const [resolved, setResolved] = useState(false);
  const [busyId,   setBusyId]   = useState(null);

  const loadAlerts = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/scanner/alerts', {
        params: { ...(domain ? { domain } : {}), resolved },
      });
      setAlerts(data.alerts || []);
    } catch {
      setAlerts([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadAlerts(); }, [domain, resolved]);

  const quarantine = async (id) => {
    setBusyId(id);
    try {
      await api.post(`/api/scanner/alerts/${id}/quarantine`);
      await loadAlerts();
    } catch (e) {
      alert(e?.response?.data?.detail || 'Quarantine failed');
    } finally {
      setBusyId(null);
    }
  };

  const resolve = async (id) => {
    setBusyId(id);
    try {
      await api.post(`/api/scanner/alerts/${id}/resolve`);
      await loadAlerts();
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <label className="flex items-center gap-1.5 text-sm text-gray-400 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={resolved}
            onChange={e => setResolved(e.target.checked)}
            className="accent-brand"
          />
          Show resolved
        </label>
        <button onClick={loadAlerts} disabled={loading} className="btn-ghost flex items-center gap-1.5 px-3 py-1 text-xs">
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {alerts.length === 0 && !loading && (
        <p className="text-sm text-gray-400 py-4 text-center">
          {resolved ? 'No resolved alerts.' : 'No active malware alerts.'}
        </p>
      )}

      <div className="space-y-2">
        {alerts.map(a => {
          const sevCls  = SEVERITY_COLORS[a.severity] || SEVERITY_COLORS.low;
          const detInfo = DETECTION_LABELS[a.detection] || { label: a.detection, cls: '' };
          return (
            <div key={a.id} className={`border rounded-xl p-3 space-y-2 ${sevCls}`}>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <FileWarning size={13} />
                  <span className="text-xs font-mono font-semibold">{a.domain}/{a.area}/{a.filepath}</span>
                  <span className={`text-[9px] px-1.5 py-0.5 rounded border ${detInfo.cls}`}>{detInfo.label}</span>
                  <span className={`text-[9px] px-1.5 py-0.5 rounded border font-semibold uppercase ${sevCls}`}>{a.severity}</span>
                </div>
                {!a.resolved && (
                  <div className="flex gap-1.5">
                    {!a.quarantined && (
                      <button
                        onClick={() => quarantine(a.id)}
                        disabled={busyId === a.id}
                        className="flex items-center gap-1 px-2 py-1 rounded-lg bg-orange-900/30 border border-orange-700/40 text-orange-300 text-[10px] hover:bg-orange-900/50 transition-colors disabled:opacity-50"
                      >
                        {busyId === a.id ? <Loader size={9} className="animate-spin" /> : <Archive size={9} />}
                        Quarantine
                      </button>
                    )}
                    <button
                      onClick={() => resolve(a.id)}
                      disabled={busyId === a.id}
                      className="flex items-center gap-1 px-2 py-1 rounded-lg bg-green-900/30 border border-green-700/40 text-green-300 text-[10px] hover:bg-green-900/50 transition-colors disabled:opacity-50"
                    >
                      {busyId === a.id ? <Loader size={9} className="animate-spin" /> : <CheckCircle size={9} />}
                      Resolve
                    </button>
                  </div>
                )}
                {a.quarantined && (
                  <span className="text-[9px] text-orange-300 bg-orange-900/20 border border-orange-700/30 px-1.5 py-0.5 rounded">
                    Quarantined
                  </span>
                )}
              </div>
              {a.threat_name && (
                <p className="text-[10px] font-mono opacity-80">Threat: {a.threat_name}</p>
              )}
              <p className="text-[9px] opacity-60">
                Detected: {a.detected_at ? new Date(a.detected_at).toLocaleString() : '—'}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Heuristic Scan panel ───────────────────────────────────────────────────────

function HeuristicPanel({ domain }) {
  const [area,    setArea]    = useState('public');
  const [path,    setPath]    = useState('');
  const [running, setRunning] = useState(false);
  const [result,  setResult]  = useState(null);
  const [error,   setError]   = useState('');

  const run = async () => {
    if (!domain) return;
    setRunning(true);
    setError('');
    setResult(null);
    try {
      const { data } = await api.post('/api/scanner/heuristic', {
        domain, area, path,
      });
      setResult(data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Heuristic scan failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-[12px] text-gray-400">
        Scans PHP/JS files for dangerous patterns (eval, base64_decode, shell_exec, webshell markers)
        without requiring ClamAV signatures.
      </p>
      <div className="flex items-center gap-2 flex-wrap">
        <select value={area} onChange={e => setArea(e.target.value)} className="input w-32 text-sm">
          {['public', 'uploads', 'private'].map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <input
          value={path}
          onChange={e => setPath(e.target.value)}
          placeholder="Subdirectory (optional)"
          className="input w-48 text-sm font-mono"
        />
        <button
          onClick={run}
          disabled={running || !domain}
          className="btn-primary flex items-center gap-1.5 px-4 py-1.5 text-sm"
        >
          {running ? <Loader size={13} className="animate-spin" /> : <Bug size={13} />}
          {running ? 'Scanning…' : 'Run Heuristic Scan'}
        </button>
      </div>

      {error && (
        <div className="text-red-400 bg-red-900/15 border border-red-800/30 rounded-xl px-4 py-2.5 text-sm">
          {error}
        </div>
      )}

      {result && (
        <div className="bg-panel-800 border border-panel-600 rounded-xl p-4 space-y-2">
          <div className="flex items-center gap-4 text-sm">
            <span className="text-gray-300">Files scanned: <strong className="text-white">{result.files_scanned}</strong></span>
            <span className={result.alerts_created > 0 ? 'text-red-400 font-semibold' : 'text-green-400'}>
              Alerts: {result.alerts_created}
            </span>
          </div>
          {result.findings?.length > 0 && (
            <ul className="space-y-1.5 max-h-48 overflow-y-auto">
              {result.findings.map((f, i) => (
                <li key={i} className="text-[11px] bg-yellow-900/10 border border-yellow-800/30 rounded-lg p-2">
                  <span className="font-mono text-yellow-300">{f.file}</span>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {f.patterns.map((p, j) => (
                      <span key={j} className="bg-yellow-900/20 border border-yellow-700/30 text-yellow-400 text-[9px] px-1.5 py-0.5 rounded font-mono">
                        {p.pattern} L{p.line}
                      </span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
          {result.alerts_created === 0 && (
            <p className="text-green-400 text-sm flex items-center gap-1.5">
              <CheckCircle size={13} /> No suspicious patterns found
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Sanitizer panel ────────────────────────────────────────────────────────────

const SANITIZE_ACTIONS = [
  { id: 'strip_eval',          label: 'Strip eval()' },
  { id: 'strip_base64_decode', label: 'Strip base64_decode()' },
  { id: 'strip_system',        label: 'Strip system()' },
  { id: 'strip_exec',          label: 'Strip exec()' },
  { id: 'strip_passthru',      label: 'Strip passthru()' },
  { id: 'strip_shell_exec',    label: 'Strip shell_exec()' },
  { id: 'strip_proc_open',     label: 'Strip proc_open()' },
  { id: 'strip_js_unescape',   label: 'Strip JS unescape write' },
];

function SanitizerPanel({ domain }) {
  const [area,    setArea]    = useState('public');
  const [path,    setPath]    = useState('');
  const [actions, setActions] = useState(['strip_eval', 'strip_base64_decode', 'strip_system']);
  const [running, setRunning] = useState(false);
  const [result,  setResult]  = useState(null);
  const [error,   setError]   = useState('');

  const toggle = (id) => setActions(prev =>
    prev.includes(id) ? prev.filter(a => a !== id) : [...prev, id]
  );

  const run = async () => {
    if (!domain || !path) return;
    setRunning(true);
    setError('');
    setResult(null);
    try {
      const { data } = await api.post('/api/scanner/sanitize', { domain, area, path, actions });
      setResult(data);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Sanitization failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-[12px] text-gray-400">
        Strip dangerous code patterns from a specific file. The original is backed up automatically.
        <strong className="text-orange-300"> Use with caution — this modifies live files.</strong>
      </p>
      <div className="flex items-center gap-2 flex-wrap">
        <select value={area} onChange={e => setArea(e.target.value)} className="input w-32 text-sm">
          {['public', 'uploads', 'private'].map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <input
          value={path}
          onChange={e => setPath(e.target.value)}
          placeholder="e.g. wp-includes/bad.php"
          className="input flex-1 min-w-48 text-sm font-mono"
        />
      </div>

      <div className="flex flex-wrap gap-2">
        {SANITIZE_ACTIONS.map(a => (
          <button
            key={a.id}
            onClick={() => toggle(a.id)}
            className={`text-[11px] px-2.5 py-1 rounded-lg border transition-colors ${
              actions.includes(a.id)
                ? 'bg-brand-600/25 border-brand-500/40 text-brand-300'
                : 'bg-panel-700 border-panel-600 text-gray-400 hover:text-gray-200'
            }`}
          >
            {a.label}
          </button>
        ))}
      </div>

      <button
        onClick={run}
        disabled={running || !domain || !path || actions.length === 0}
        className="btn-danger flex items-center gap-1.5 px-4 py-1.5 text-sm"
      >
        {running ? <Loader size={13} className="animate-spin" /> : <Wrench size={13} />}
        {running ? 'Sanitizing…' : 'Sanitize File'}
      </button>

      {error && (
        <div className="text-red-400 bg-red-900/15 border border-red-800/30 rounded-xl px-4 py-2.5 text-sm">
          {error}
        </div>
      )}

      {result && (
        <div className={`rounded-xl p-4 border text-sm space-y-1.5 ${
          result.changed
            ? 'bg-orange-900/10 border-orange-800/30'
            : 'bg-green-900/10 border-green-800/30'
        }`}>
          <p className={result.changed ? 'text-orange-300 font-semibold' : 'text-green-400'}>
            {result.detail || (result.changed ? `Modified — ${result.lines_changed} replacements made` : 'File clean')}
          </p>
          {result.actions?.map((a, i) => (
            <p key={i} className="text-[11px] text-gray-300 font-mono">
              {a.action}: {a.replacements} replacement{a.replacements !== 1 ? 's' : ''}
            </p>
          ))}
          {result.backup && (
            <p className="text-[10px] text-gray-400">Backup: <span className="font-mono">{result.backup}</span></p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main SecurityScanner component ────────────────────────────────────────────

const SCANNER_TABS = [
  { id: 'scan',       label: 'AV Scan',    icon: ScanLine },
  { id: 'alerts',     label: 'Alerts',     icon: ShieldAlert },
  { id: 'heuristic',  label: 'Heuristic',  icon: Bug },
  { id: 'sanitize',   label: 'Sanitizer',  icon: Wrench },
];

export default function SecurityScanner({ domain }) {
  const [tab, setTab] = useState('scan');

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <div className="w-8 h-8 rounded-xl bg-red-900/30 flex items-center justify-center">
          <ShieldAlert size={16} className="text-red-400" />
        </div>
        <div>
          <h2 className="text-[15px] font-bold text-white">Security Scanner</h2>
          <p className="text-[11px] text-gray-400">Admin-only — antivirus, malware detection, file sanitizer</p>
        </div>
      </div>

      {/* Sub-tabs */}
      <div className="flex gap-1 bg-panel-800 border border-panel-600 rounded-xl p-1 w-fit flex-wrap">
        {SCANNER_TABS.map(({ id, label, icon: Icon }) => (
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

      {tab === 'scan'      && <ScanPanel      domain={domain} />}
      {tab === 'alerts'    && <AlertsPanel    domain={domain} />}
      {tab === 'heuristic' && <HeuristicPanel domain={domain} />}
      {tab === 'sanitize'  && <SanitizerPanel domain={domain} />}
    </div>
  );
}
