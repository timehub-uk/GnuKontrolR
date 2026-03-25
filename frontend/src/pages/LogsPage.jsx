import { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  ScrollText, RefreshCw, Download, Search, X,
  ChevronDown, Activity, Loader,
} from 'lucide-react';
import api from '../utils/api';

const SYSTEM_SOURCES = [
  { id: 'panel',    label: 'Panel API',   color: 'text-brand-light' },
  { id: 'postgres', label: 'PostgreSQL',  color: 'text-sky-400' },
  { id: 'redis',    label: 'Redis',       color: 'text-red-400' },
  { id: 'mysql',    label: 'MySQL',       color: 'text-orange-400' },
  { id: 'traefik',  label: 'Traefik',     color: 'text-purple-400' },
  { id: 'postfix',  label: 'Postfix',     color: 'text-yellow-400' },
  { id: 'dovecot',  label: 'Dovecot',     color: 'text-pink-400' },
];

const TAIL_OPTIONS = [50, 100, 200, 500, 1000];

function classifyLine(line) {
  const l = line.toLowerCase();
  if (/\berror\b|exception|fatal|critical|fail/.test(l)) return 'text-red-400';
  if (/\bwarn(ing)?\b/.test(l)) return 'text-yellow-300';
  if (/\binfo\b/.test(l)) return 'text-green-300';
  if (/\bdebug\b/.test(l)) return 'text-sky-300';
  return 'text-gray-300';
}

export default function LogsPage() {
  const [searchParams] = useSearchParams();
  const [domains,    setDomains]    = useState([]);
  const [source,     setSource]     = useState(searchParams.get('source') || 'panel');
  const [tail,       setTail]       = useState(200);
  const [search,     setSearch]     = useState('');
  const [lines,      setLines]      = useState([]);
  const [loading,    setLoading]    = useState(false);
  const [autoFollow, setAutoFollow] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [lastFetch,  setLastFetch]  = useState(null);
  const [error,      setError]      = useState('');

  const bottomRef   = useRef(null);
  const intervalRef = useRef(null);
  const searchRef   = useRef(search);
  searchRef.current = search;

  // Load domain list for container log option
  useEffect(() => {
    api.get('/api/domains').then(r => {
      const list = r.data?.domains || r.data || [];
      setDomains(list);
    }).catch(() => {});
  }, []);

  const fetchLogs = useCallback(async (src, tailN, srch) => {
    const s   = src  ?? source;
    const t   = tailN ?? tail;
    const q   = srch !== undefined ? srch : searchRef.current;
    setLoading(true);
    setError('');
    try {
      const params = { tail: t };
      if (q) params.search = q;
      const r = await api.get(`/api/logs/${encodeURIComponent(s)}`, { params });
      setLines(r.data.lines || []);
      setLastFetch(new Date().toLocaleTimeString());
    } catch (e) {
      setError(e?.response?.data?.detail || 'Failed to load logs');
      setLines([]);
    } finally {
      setLoading(false);
    }
  }, [source, tail]);

  // Auto-scroll to bottom when lines change and autoFollow is on
  useEffect(() => {
    if (autoFollow) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [lines, autoFollow]);

  // Auto-refresh every 5 s
  useEffect(() => {
    clearInterval(intervalRef.current);
    if (autoRefresh) {
      intervalRef.current = setInterval(() => fetchLogs(), 5000);
    }
    return () => clearInterval(intervalRef.current);
  }, [autoRefresh, fetchLogs]);

  // Fetch on source/tail change
  useEffect(() => {
    fetchLogs(source, tail, search);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, tail]);

  const handleSourceChange = (id) => {
    setSource(id);
    setLines([]);
    setError('');
  };

  const handleSearch = (e) => {
    e.preventDefault();
    fetchLogs(source, tail, search);
  };

  const handleDownload = async () => {
    try {
      const r = await api.get(`/api/logs/${encodeURIComponent(source)}/download`, {
        params: { tail: 1000 },
        responseType: 'blob',
      });
      const url = URL.createObjectURL(r.data);
      const a   = document.createElement('a');
      a.href     = url;
      a.download = `${source.replace(':', '_')}.log`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* ignore */ }
  };

  // Build full source list: system sources + domain containers
  const domainSources = domains.map(d => {
    const name = d.name || d;
    return { id: `domain:${name}`, label: name, color: 'text-teal-400' };
  });

  const allSources = [...SYSTEM_SOURCES, ...domainSources];
  const activeSource = allSources.find(s => s.id === source);

  return (
    <div className="flex flex-col space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-[20px] font-bold text-ink-primary flex items-center gap-2">
            <ScrollText size={20} className="text-brand" /> System Logs
          </h1>
          <p className="text-[13px] text-ink-muted mt-0.5">
            Real-time logs from all panel services and domain containers
          </p>
        </div>
        <div className="flex items-center gap-2">
          {lastFetch && (
            <span className="text-[11px] text-ink-muted">Updated {lastFetch}</span>
          )}
          <button
            onClick={() => fetchLogs()}
            disabled={loading}
            className="btn-ghost flex items-center gap-1.5 text-xs py-1.5 px-3"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
          <button
            onClick={handleDownload}
            className="btn-ghost flex items-center gap-1.5 text-xs py-1.5 px-3"
          >
            <Download size={13} /> Download
          </button>
        </div>
      </div>

      {/* Controls row */}
      <div className="flex items-center gap-3 flex-wrap flex-shrink-0">
        {/* Source selector */}
        <div className="relative">
          <select
            value={source}
            onChange={e => handleSourceChange(e.target.value)}
            className="input pr-8 appearance-none w-48"
          >
            <optgroup label="System Services">
              {SYSTEM_SOURCES.map(s => (
                <option key={s.id} value={s.id}>{s.label}</option>
              ))}
            </optgroup>
            {domainSources.length > 0 && (
              <optgroup label="Domain Containers">
                {domainSources.map(s => (
                  <option key={s.id} value={s.id}>{s.label}</option>
                ))}
              </optgroup>
            )}
          </select>
          <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-muted pointer-events-none" />
        </div>

        {/* Tail */}
        <div className="relative">
          <select
            value={tail}
            onChange={e => { setTail(Number(e.target.value)); }}
            className="input pr-8 appearance-none w-28"
          >
            {TAIL_OPTIONS.map(n => (
              <option key={n} value={n}>{n} lines</option>
            ))}
          </select>
          <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-muted pointer-events-none" />
        </div>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex items-center gap-1.5 flex-1 max-w-sm">
          <div className="relative flex-1">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-muted" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Filter lines…"
              className="input pl-8 pr-8 w-full"
            />
            {search && (
              <button
                type="button"
                onClick={() => { setSearch(''); fetchLogs(source, tail, ''); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink-primary"
              >
                <X size={12} />
              </button>
            )}
          </div>
          <button type="submit" className="btn-ghost py-1.5 px-3 text-xs">
            Search
          </button>
        </form>

        {/* Auto-refresh toggle */}
        <label className="flex items-center gap-1.5 text-[12px] text-ink-muted cursor-pointer select-none">
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={e => setAutoRefresh(e.target.checked)}
            className="accent-brand w-3.5 h-3.5"
          />
          <Activity size={12} className={autoRefresh ? 'text-brand-light' : ''} />
          Auto-refresh
        </label>

        {/* Auto-follow toggle */}
        <label className="flex items-center gap-1.5 text-[12px] text-ink-muted cursor-pointer select-none">
          <input
            type="checkbox"
            checked={autoFollow}
            onChange={e => setAutoFollow(e.target.checked)}
            className="accent-brand w-3.5 h-3.5"
          />
          Auto-follow
        </label>
      </div>

      {/* Source label badge */}
      {activeSource && (
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className={`text-[11px] font-semibold uppercase tracking-wide ${activeSource.color}`}>
            {activeSource.label}
          </span>
          <span className="text-[11px] text-ink-muted">— {lines.length} lines</span>
          {loading && <Loader size={11} className="animate-spin text-ink-muted" />}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex-shrink-0 text-bad-light bg-bad/10 border border-bad/20 rounded-lg px-3 py-2 text-xs">
          {error}
        </div>
      )}

      {/* Log output */}
      <div
        className="bg-black/70 rounded-xl border border-panel-border overflow-auto p-4 font-mono text-xs"
        style={{ minHeight: '28rem', maxHeight: '70vh' }}
      >
        {!loading && lines.length === 0 && !error && (
          <span className="text-ink-muted">No log lines. Select a source and press Refresh.</span>
        )}
        {lines.map((line, i) => (
          <div
            key={i}
            className={`leading-relaxed whitespace-pre-wrap break-all ${classifyLine(line)}`}
          >
            {line}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
