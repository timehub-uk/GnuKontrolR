import { useState, useEffect, useCallback, useRef } from 'react';
import api from '../utils/api';
import {
  Container, Play, Square, RotateCcw, Trash2, Terminal,
  RefreshCw, Network, ChevronDown, ChevronRight, Loader,
  AlertCircle, Plug, Shield,
} from 'lucide-react';

// ── Port range reference (mirrors backend PORT_RANGES) ───────────────────────
const SERVICE_META = {
  ssh:       { label: 'SSH / SFTP',     color: 'text-blue-400',   bg: 'bg-blue-900/20 border-blue-800' },
  node:      { label: 'Node.js',        color: 'text-green-400',  bg: 'bg-green-900/20 border-green-800' },
  websocket: { label: 'WebSocket',      color: 'text-purple-400', bg: 'bg-purple-900/20 border-purple-800' },
};

// ── Port Assignments panel ────────────────────────────────────────────────────

function PortBadge({ service, port }) {
  const meta = SERVICE_META[service] || { label: service, color: 'text-gray-400', bg: 'bg-panel-700 border-panel-600' };
  return (
    <div className={`flex items-center justify-between rounded-lg border px-3 py-2 ${meta.bg}`}>
      <div className="flex items-center gap-2">
        <Plug size={12} className={meta.color} />
        <span className={`text-xs font-medium ${meta.color}`}>{meta.label}</span>
      </div>
      <span className="text-xs font-mono text-white bg-black/30 px-2 py-0.5 rounded">
        :{port}
      </span>
    </div>
  );
}

function PortAssignmentsPanel({ domain }) {
  const [ports,   setPorts]   = useState(null);   // null = not loaded yet
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState('');
  const [open,    setOpen]    = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await api.get(`/api/docker/containers/${domain}/ports`);
      setPorts(data.ports || {});
    } catch (e) {
      if (e?.response?.status === 404) {
        setPorts({});   // no assignments yet — not an error
      } else {
        setError(e?.response?.data?.detail || 'Failed to load ports');
      }
    } finally {
      setLoading(false);
    }
  }, [domain]);

  useEffect(() => {
    if (open && ports === null) load();
  }, [open, ports, load]);

  const portCount = ports ? Object.keys(ports).length : 0;

  return (
    <div className="border border-panel-600 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-2.5 bg-panel-700/40 hover:bg-panel-700 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Network size={13} className="text-brand-400" />
          <span className="text-sm text-gray-200">Port Assignments</span>
          {ports !== null && portCount > 0 && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-brand-600/25 text-brand-300">
              {portCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {loading && <Loader size={12} className="animate-spin text-gray-500" />}
          {open ? <ChevronDown size={13} className="text-gray-500" /> : <ChevronRight size={13} className="text-gray-500" />}
        </div>
      </button>

      {open && (
        <div className="px-4 py-3 space-y-2 bg-panel-800/30">
          {error && (
            <p className="flex items-center gap-1.5 text-xs text-red-400">
              <AlertCircle size={12} /> {error}
            </p>
          )}

          {!loading && ports !== null && portCount === 0 && (
            <p className="text-xs text-gray-500 text-center py-1">
              No port assignments recorded yet.
            </p>
          )}

          {ports && Object.entries(ports).map(([svc, port]) => (
            <PortBadge key={svc} service={svc} port={port} />
          ))}

          {/* Security note */}
          {ports !== null && portCount > 0 && (
            <div className="flex items-start gap-1.5 pt-1 border-t border-white/5">
              <Shield size={11} className="text-gray-600 mt-0.5 flex-shrink-0" />
              <p className="text-xs text-gray-600">
                All host ports are loopback-bound (127.0.0.1). Container API
                (port 9000) is internal-only and never mapped to the host.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DockerPage() {
  const [containers, setContainers] = useState([]);
  const [stats,      setStats]      = useState({});   // name → {CPUPerc, MemUsage, …}
  const [loading,    setLoading]    = useState(true);
  const [logs,       setLogs]       = useState({ show: false, domain: '', content: '' });
  const [expanded,   setExpanded]   = useState({});   // domain → bool
  const statsTimer = useRef(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/docker/containers');
      setContainers(data);
    } catch { setContainers([]); }
    setLoading(false);
  };

  const loadStats = useCallback(async () => {
    try {
      const { data } = await api.get('/api/docker/stats');
      setStats(data);
    } catch { /* non-fatal */ }
  }, []);

  // Extract total memory from any stats entry (all share the same host total)
  const totalMem = Object.values(stats)[0]?.MemUsage?.split(' / ')[1] ?? null;

  // Return only the "used" portion, stripping the "/ total" part
  const memUsed = name => {
    const raw = stats[name]?.MemUsage;
    if (!raw) return '—';
    return raw.split(' / ')[0];
  };

  useEffect(() => {
    load();
    loadStats();
    statsTimer.current = setInterval(loadStats, 5000);
    return () => clearInterval(statsTimer.current);
  }, [loadStats]);

  const action = async (domain, act) => {
    await api.post(`/api/docker/containers/${domain}/action`, { action: act });
    load();
  };

  const viewLogs = async domain => {
    const { data } = await api.get(`/api/docker/containers/${domain}/logs?tail=200`);
    setLogs({ show: true, domain, content: data.logs });
  };

  const toggleExpand = domain =>
    setExpanded(e => ({ ...e, [domain]: !e[domain] }));

  const stateColor = s => {
    const sl = s?.toLowerCase() || '';
    if (sl.includes('up') || sl === 'running') return 'badge-green';
    if (sl.includes('exit'))                   return 'badge-red';
    return 'badge-yellow';
  };

  // Extract the domain slug from the container name (site_example_com → example.com)
  const domainOf = name =>
    (name || '').replace(/^\//, '').replace(/^site_/, '').replace(/_/g, '.');

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Container size={20} /> Docker Containers
        </h1>
        <button onClick={load} className="btn-ghost" title="Refresh">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="card text-xs text-gray-400 bg-blue-900/10 border-blue-800 flex items-center justify-between gap-4">
        <span>
          Each domain runs in its own isolated Docker container with memory/CPU limits,
          read-only filesystem, and a separate network namespace. Every service is
          assigned its own globally unique host port — no two customers ever share a port.
        </span>
        {totalMem && (
          <span className="shrink-0 font-mono text-gray-300 bg-panel-700 px-2.5 py-1 rounded-lg border border-panel-600 whitespace-nowrap">
            Host RAM: <span className="text-white font-semibold">{totalMem}</span>
          </span>
        )}
      </div>

      {/* Container table */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-panel-700 text-gray-400 text-xs uppercase">
            <tr>
              {['', 'Container', 'Image', 'State', 'CPU', 'Memory', 'Ports', 'Actions'].map(h => (
                <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-panel-700">
            {loading ? (
              <tr><td colSpan={8} className="text-center py-8 text-gray-500">Loading…</td></tr>
            ) : containers.length === 0 ? (
              <tr><td colSpan={8} className="text-center py-8 text-gray-500">No containers found</td></tr>
            ) : containers.map((c, i) => {
              const rawName = c.Names || c.Name || '';
              const domain  = domainOf(rawName);
              const isOpen  = expanded[rawName];
              return [
                // Main row
                <tr key={rawName} className="hover:bg-panel-700/50">
                  <td className="px-3 py-3">
                    <button
                      onClick={() => toggleExpand(rawName)}
                      className="text-gray-500 hover:text-gray-300"
                      title="Port assignments"
                    >
                      {isOpen
                        ? <ChevronDown size={13} />
                        : <ChevronRight size={13} />}
                    </button>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-white">{rawName}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs truncate max-w-xs">{c.Image || '—'}</td>
                  <td className="px-4 py-3">
                    <span className={stateColor(c.State || c.Status)}>
                      {c.State || c.Status || '—'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-400 font-mono text-xs">
                    {stats[rawName]?.CPUPerc ?? c.CPUPerc ?? '—'}
                  </td>
                  <td className="px-4 py-3 text-gray-400 font-mono text-xs">
                    {memUsed(rawName)}
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{c.Ports || '—'}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button title="Start"   onClick={() => action(rawName, 'start')}   className="text-green-500 hover:text-green-300"><Play size={13} /></button>
                      <button title="Stop"    onClick={() => action(rawName, 'stop')}    className="text-yellow-500 hover:text-yellow-300"><Square size={13} /></button>
                      <button title="Restart" onClick={() => action(rawName, 'restart')} className="text-blue-400 hover:text-blue-200"><RotateCcw size={13} /></button>
                      <button title="Logs"    onClick={() => viewLogs(rawName)}          className="text-gray-400 hover:text-white"><Terminal size={13} /></button>
                      <button title="Remove"  onClick={() => action(rawName, 'kill')}    className="text-gray-600 hover:text-red-400"><Trash2 size={13} /></button>
                    </div>
                  </td>
                </tr>,

                // Expandable port assignments row
                isOpen && (
                  <tr key={rawName + '_ports'} className="bg-panel-800/60">
                    <td />
                    <td colSpan={7} className="px-4 py-3">
                      <PortAssignmentsPanel domain={domain} />
                    </td>
                  </tr>
                ),
              ];
            })}
          </tbody>
        </table>
      </div>

      {/* Logs modal */}
      {logs.show && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
          <div className="bg-panel-800 rounded-xl border border-panel-600 w-full max-w-3xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-5 py-3 border-b border-panel-600">
              <span className="text-sm font-medium text-white">Logs — {logs.domain}</span>
              <button onClick={() => setLogs(l => ({ ...l, show: false }))} className="text-gray-400 hover:text-white">✕</button>
            </div>
            <pre className="flex-1 overflow-auto p-4 text-xs text-green-400 font-mono leading-relaxed bg-black/40 rounded-b-xl whitespace-pre-wrap">
              {logs.content || 'No logs available.'}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
