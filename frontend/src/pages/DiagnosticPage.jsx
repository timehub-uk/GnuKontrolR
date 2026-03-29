import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../utils/api';
import {
  Activity, RefreshCw, Server, Database, Wifi, Cpu,
  MemoryStick, HardDrive, Container, CheckCircle2,
  XCircle, AlertTriangle, Clock, Globe,
} from 'lucide-react';

// ── helpers ───────────────────────────────────────────────────────────────────

function level(pct) {
  if (pct >= 90) return 'critical';
  if (pct >= 75) return 'warning';
  return 'ok';
}

const LEVEL_BADGE = {
  ok:       'bg-ok/15 text-ok-light border border-ok/25',
  warning:  'bg-warn/15 text-warn-light border border-warn/25',
  critical: 'bg-bad/15 text-bad-light border border-bad/25',
  unknown:  'bg-panel-elevated text-ink-muted border border-panel-border',
};
const LEVEL_BAR = {
  ok:       'bg-ok',
  warning:  'bg-warn',
  critical: 'bg-bad',
  unknown:  'bg-ink-muted',
};

const STATE_BADGE = {
  active:          'bg-ok/15 text-ok-light border border-ok/25',
  inactive:        'bg-bad/15 text-bad-light border border-bad/25',
  failed:          'bg-bad/15 text-bad-light border border-bad/25',
  restarting:      'bg-warn/15 text-warn-light border border-warn/25',
  'not installed': 'bg-panel-elevated text-ink-muted border border-panel-border',
  unknown:         'bg-panel-elevated text-ink-muted border border-panel-border',
};
const STATE_ICON = {
  active:          <CheckCircle2 size={14} className="text-ok" />,
  inactive:        <XCircle size={14} className="text-bad" />,
  failed:          <XCircle size={14} className="text-bad" />,
  restarting:      <AlertTriangle size={14} className="text-warn" />,
  'not installed': <XCircle size={14} className="text-ink-muted" />,
  unknown:         <AlertTriangle size={14} className="text-ink-muted" />,
};

const SERVICE_META = {
  traefik:  { label: 'Traefik',    icon: '🔀', desc: 'Reverse proxy & SSL' },
  mysql:    { label: 'MySQL',      icon: '🗄️', desc: 'Master database' },
  postgres: { label: 'PostgreSQL', icon: '🐘', desc: 'Panel metadata DB' },
  redis:    { label: 'Redis',      icon: '⚡', desc: 'Cache & sessions' },
  postfix:  { label: 'Postfix',    icon: '📨', desc: 'Outbound SMTP' },
  dovecot:  { label: 'Dovecot',    icon: '📥', desc: 'IMAP / POP3' },
  powerdns: { label: 'PowerDNS',   icon: '🌍', desc: 'Authoritative DNS' },
};

function fmtUptime(secs) {
  if (!secs || secs < 0) return '—';
  const d = Math.floor(secs / 86400);
  const h = Math.floor((secs % 86400) / 3600);
  const m = Math.floor((secs % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function fmtAgo(ts) {
  if (!ts) return '';
  const secs = Math.floor(Date.now() / 1000) - ts;
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  return `${Math.floor(secs / 3600)}h ago`;
}

// ── sub-components ────────────────────────────────────────────────────────────

function ResourceBar({ label, pct, used, total, unit }) {
  const lvl = level(pct);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className="text-ink-secondary">{label}</span>
        <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${LEVEL_BADGE[lvl]}`}>
          {pct.toFixed(1)}%
        </span>
      </div>
      <div className="h-2 rounded-full bg-panel-elevated overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${LEVEL_BAR[lvl]}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
      {used != null && (
        <p className="text-xs text-ink-muted text-right">
          {used} / {total} {unit}
        </p>
      )}
    </div>
  );
}

function StatusDot({ state }) {
  const cls = {
    active:   'bg-ok animate-pulse',
    inactive: 'bg-bad',
    failed:   'bg-bad',
    restarting:'bg-warn animate-pulse',
    unknown:  'bg-ink-muted',
    'not installed': 'bg-ink-muted',
  }[state] ?? 'bg-ink-muted';
  return <span className={`inline-block w-2 h-2 rounded-full ${cls}`} />;
}

// ── main page ─────────────────────────────────────────────────────────────────

export default function DiagnosticPage() {
  const [data,       setData]      = useState(null);
  const [liveStats,  setLiveStats] = useState(null);
  const [loading,    setLoading]   = useState(true);
  const [error,      setError]     = useState('');
  const [auto,       setAuto]      = useState(true);
  const [wsStatus,   setWsStatus]  = useState('connecting'); // connecting | live | error
  const wsRef = useRef(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data: d } = await api.get('/api/server/diagnostic');
      setData(d);
    } catch (e) {
      setError(e?.response?.data?.detail ?? 'Failed to load diagnostic data');
    } finally {
      setLoading(false);
    }
  }, []);

  // Live WebSocket for CPU/Memory/Disk stats
  useEffect(() => {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host  = window.location.hostname;
    const port  = import.meta.env.VITE_API_PORT || '8000';
    // Append auth token — ws/stats requires JWT since it was secured
    const token = localStorage.getItem('access_token');
    const url   = `${proto}://${host}:${port}/api/server/ws/stats${token ? `?token=${encodeURIComponent(token)}` : ''}`;

    let ws;
    let reconnectTimeout;

    function connect() {
      ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen  = () => setWsStatus('live');
      ws.onclose = () => {
        setWsStatus('error');
        reconnectTimeout = setTimeout(connect, 5000);
      };
      ws.onerror = () => setWsStatus('error');
      ws.onmessage = (e) => {
        try { setLiveStats(JSON.parse(e.data)); } catch { /* ignore */ }
      };
    }

    connect();
    return () => {
      clearTimeout(reconnectTimeout);
      ws?.close();
    };
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!auto) return;
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [auto, load]);

  // ── overall health summary ────────────────────────────────────────────────
  const summary = (() => {
    if (!data) return { level: 'unknown', label: 'Loading…', count: {} };
    const svcValues = Object.values(data.services || {});
    const tcpValues = Object.values(data.tcp_checks || {});
    const down   = svcValues.filter(s => s === 'inactive' || s === 'failed').length;
    const restart= svcValues.filter(s => s === 'restarting').length;
    const tcpFail= tcpValues.filter(t => !t.ok).length;
    const h      = data.health || {};
    const critical = down > 0 || h.cpu === 'critical' || h.mem === 'critical' || h.disk === 'critical' || tcpFail > 0;
    const warning  = restart > 0 || h.cpu === 'warning' || h.mem === 'warning' || h.disk === 'warning';
    const lvl = critical ? 'critical' : warning ? 'warning' : 'ok';
    return { level: lvl, down, restart, tcpFail, h };
  })();

  const SUMMARY_STYLE = {
    ok:       'bg-ok/10 border-ok/30 text-ok-light',
    warning:  'bg-warn/10 border-warn/30 text-warn-light',
    critical: 'bg-bad/10 border-bad/30 text-bad-light',
    unknown:  'bg-panel-card border-panel-border text-ink-muted',
  };

  // Prefer live WebSocket stats for resource bars; fall back to snapshot
  const s = liveStats
    ? {
        cpu_percent:   liveStats.cpu,
        mem_percent:   liveStats.mem,
        mem_used_mb:   liveStats.mem_used_mb,
        mem_total_mb:  data?.stats?.mem_total_mb,
        disk_percent:  liveStats.disk,
        disk_used_gb:  data?.stats?.disk_used_gb,
        disk_total_gb: data?.stats?.disk_total_gb,
        net_sent_mb:   liveStats.net_sent,
        net_recv_mb:   liveStats.net_recv,
        boot_timestamp: data?.stats?.boot_timestamp,
      }
    : data?.stats;
  const cc = data?.customer_containers;

  return (
    <div className="space-y-6">
      {/* header */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-ink-primary flex items-center gap-2">
          <Activity size={20} /> System Diagnostic
        </h1>
        <div className="flex items-center gap-3">
          <span className={`flex items-center gap-1.5 text-xs font-medium ${wsStatus === 'live' ? 'text-ok-light' : 'text-ink-muted'}`}>
            <span className={`w-2 h-2 rounded-full ${wsStatus === 'live' ? 'bg-ok animate-pulse' : 'bg-ink-muted'}`} />
            {wsStatus === 'live' ? 'Live' : wsStatus === 'connecting' ? 'Connecting…' : 'Offline'}
          </span>
          {data && (
            <span className="text-xs text-ink-muted">
              Updated {fmtAgo(data.timestamp)}
            </span>
          )}
          <button
            onClick={() => setAuto(v => !v)}
            className={`text-xs px-2 py-1 rounded border transition-colors ${
              auto
                ? 'bg-brand/15 border-brand/30 text-brand-light'
                : 'bg-panel-elevated border-panel-border text-ink-muted'
            }`}
          >
            Auto {auto ? 'ON' : 'OFF'}
          </button>
          <button
            onClick={load}
            disabled={loading}
            className="btn-primary flex items-center gap-1.5 text-sm px-3 py-1.5"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="card border-bad/30 bg-bad/10 text-bad-light text-sm p-4">
          {error}
        </div>
      )}

      {/* overall status banner */}
      {data && (
        <div className={`rounded-xl border px-5 py-4 flex items-center gap-3 ${SUMMARY_STYLE[summary.level]}`}>
          {summary.level === 'ok'
            ? <CheckCircle2 size={22} />
            : summary.level === 'warning'
            ? <AlertTriangle size={22} />
            : <XCircle size={22} />}
          <div>
            <p className="font-semibold">
              {summary.level === 'ok'    && 'All systems operational'}
              {summary.level === 'warning' && 'Systems degraded — action may be needed'}
              {summary.level === 'critical' && 'Critical issues detected'}
            </p>
            <p className="text-xs opacity-75 mt-0.5">
              {summary.down > 0 && `${summary.down} service(s) down · `}
              {summary.restart > 0 && `${summary.restart} restarting · `}
              {summary.tcpFail > 0 && `${summary.tcpFail} TCP check(s) failed · `}
              {cc && `${cc.up}/${cc.total} customer containers up`}
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* ── Resources ── */}
        <div className="card space-y-4">
          <h2 className="text-sm font-semibold text-ink-secondary uppercase tracking-wide flex items-center gap-2">
            <Cpu size={14} /> System Resources
          </h2>
          {s ? (
            <div className="space-y-4">
              <ResourceBar
                label="CPU"
                pct={s.cpu_percent}
              />
              <ResourceBar
                label="Memory"
                pct={s.mem_percent}
                used={s.mem_used_mb}
                total={s.mem_total_mb}
                unit="MB"
              />
              <ResourceBar
                label="Disk"
                pct={s.disk_percent}
                used={s.disk_used_gb}
                total={s.disk_total_gb}
                unit="GB"
              />
              <div className="grid grid-cols-2 gap-3 pt-1">
                <div className="bg-panel-elevated rounded-lg p-3 text-center">
                  <p className="text-xs text-ink-muted mb-1 flex items-center justify-center gap-1">
                    <Clock size={11} /> Uptime
                  </p>
                  <p className="text-sm font-mono text-ink-primary">
                    {fmtUptime(Math.floor(Date.now() / 1000) - s.boot_timestamp)}
                  </p>
                </div>
                <div className="bg-panel-elevated rounded-lg p-3 text-center">
                  <p className="text-xs text-ink-muted mb-1 flex items-center justify-center gap-1">
                    <Wifi size={11} /> Network
                  </p>
                  <p className="text-xs font-mono text-ink-primary">
                    ↑{s.net_sent_mb} MB ↓{s.net_recv_mb} MB
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-ink-muted text-sm">Loading…</p>
          )}
        </div>

        {/* ── Customer Containers ── */}
        <div className="card space-y-4">
          <h2 className="text-sm font-semibold text-ink-secondary uppercase tracking-wide flex items-center gap-2">
            <Container size={14} /> Customer Containers
          </h2>
          {cc ? (
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-panel-elevated rounded-lg p-4 text-center">
                <p className="text-2xl font-bold text-ink-primary">{cc.total}</p>
                <p className="text-xs text-ink-muted mt-1">Total</p>
              </div>
              <div className="bg-ok/10 border border-ok/25 rounded-lg p-4 text-center">
                <p className="text-2xl font-bold text-ok-light">{cc.up}</p>
                <p className="text-xs text-ok-light/70 mt-1">Running</p>
              </div>
              <div className={`rounded-lg p-4 text-center border ${cc.down > 0 ? 'bg-bad/10 border-bad/25' : 'bg-panel-elevated border-panel-border'}`}>
                <p className={`text-2xl font-bold ${cc.down > 0 ? 'text-bad-light' : 'text-ink-muted'}`}>{cc.down}</p>
                <p className={`text-xs mt-1 ${cc.down > 0 ? 'text-bad-light/70' : 'text-ink-muted'}`}>Stopped</p>
              </div>
            </div>
          ) : (
            <p className="text-ink-muted text-sm">Loading…</p>
          )}

          {/* TCP Health Checks */}
          <div className="space-y-2 pt-2">
            <h3 className="text-xs font-semibold text-ink-muted uppercase tracking-wide flex items-center gap-1.5">
              <Globe size={11} /> TCP Connectivity
            </h3>
            {data?.tcp_checks ? (
              <div className="divide-y divide-panel-border">
                {Object.entries(data.tcp_checks).map(([key, { ok, latency_ms }]) => (
                  <div key={key} className="flex items-center justify-between py-2 text-sm">
                    <div className="flex items-center gap-2">
                      {ok
                        ? <CheckCircle2 size={13} className="text-ok" />
                        : <XCircle size={13} className="text-bad" />}
                      <span className="text-ink-secondary capitalize">{SERVICE_META[key]?.label ?? key}</span>
                    </div>
                    <span className={`text-xs font-mono ${ok ? 'text-ok-light' : 'text-bad-light'}`}>
                      {ok ? `${latency_ms}ms` : 'FAIL'}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-ink-muted text-sm">Loading…</p>
            )}
          </div>
        </div>

        {/* ── Master Services ── */}
        <div className="card lg:col-span-2 space-y-3">
          <h2 className="text-sm font-semibold text-ink-secondary uppercase tracking-wide flex items-center gap-2">
            <Server size={14} /> Master Services
          </h2>
          {data?.services ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
              {Object.entries(SERVICE_META).map(([key, meta]) => {
                const state  = data.services[key] ?? 'unknown';
                const uptime = data.service_uptimes?.[key];
                const tcp    = data.tcp_checks?.[key];
                return (
                  <div
                    key={key}
                    className={`rounded-xl border p-4 space-y-2 ${
                      state === 'active'
                        ? 'bg-panel-card border-panel-border'
                        : state === 'restarting'
                        ? 'bg-warn/5 border-warn/20'
                        : 'bg-bad/5 border-bad/20'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-base">{meta.icon}</span>
                        <span className="text-sm font-medium text-ink-primary">{meta.label}</span>
                      </div>
                      <StatusDot state={state} />
                    </div>
                    <p className="text-xs text-ink-muted">{meta.desc}</p>
                    <div className="flex items-center justify-between">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATE_BADGE[state] ?? STATE_BADGE.unknown}`}>
                        {state}
                      </span>
                      {uptime != null && uptime > 0 && (
                        <span className="text-xs text-ink-muted font-mono">{fmtUptime(uptime)}</span>
                      )}
                    </div>
                    {tcp && (
                      <div className="flex items-center gap-1 text-xs text-ink-muted">
                        {tcp.ok
                          ? <><CheckCircle2 size={11} className="text-ok" /> <span className="text-ok-light/80">{tcp.latency_ms}ms</span></>
                          : <><XCircle size={11} className="text-bad" /> <span className="text-bad-light/80">TCP fail</span></>
                        }
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-ink-muted text-sm">Loading…</p>
          )}
        </div>

      </div>
    </div>
  );
}
