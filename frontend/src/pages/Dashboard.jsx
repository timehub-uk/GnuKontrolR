import { useState, useEffect, useRef } from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from 'recharts';
import { createWS } from '../utils/ws';
import api from '../utils/api';
import {
  Cpu, MemoryStick, HardDrive, Globe, Container, Users,
  Activity, ArrowUp, ArrowDown, Server, Clock,
} from 'lucide-react';

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmt(n, unit = '') { return n != null ? `${n}${unit}` : '—'; }
function uptime(ts) {
  if (!ts) return '—';
  const s = Math.floor(Date.now() / 1000 - ts);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return d > 0 ? `${d}d ${h}h` : h > 0 ? `${h}h ${m}m` : `${m}m`;
}

// ── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ icon: Icon, label, value, sub, pct, glowColor, barColor }) {
  return (
    <div
      className="relative overflow-hidden rounded-xl p-4 border border-panel-border"
      style={{ background: '#111113' }}
    >
      {/* Glow */}
      <div
        className="absolute top-0 right-0 w-16 h-16 rounded-full pointer-events-none"
        style={{ background: glowColor, filter: 'blur(22px)', transform: 'translate(30%,-30%)', opacity: 0.6 }}
      />
      <div className="relative">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-muted">{label}</span>
          <Icon size={13} className="text-ink-muted" />
        </div>
        <div className="text-[26px] font-bold leading-none mb-2" style={{ color: barColor }}>{value}</div>
        {sub && <div className="text-[11px] text-ink-muted mb-2">{sub}</div>}
        {pct != null && (
          <div className="h-[3px] bg-panel-border rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{ width: `${Math.min(pct, 100)}%`, background: `linear-gradient(90deg, ${barColor}, ${barColor}cc)` }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Gauge bar ─────────────────────────────────────────────────────────────────
function GaugeBar({ label, pct, color, sub }) {
  const danger = pct > 80;
  return (
    <div>
      <div className="flex justify-between items-center text-[12px] mb-1.5">
        <span className="text-ink-secondary font-medium">{label}</span>
        <span className={danger ? 'text-bad-light font-semibold' : 'text-ink-muted'}>{fmt(pct, '%')}</span>
      </div>
      <div className="h-[5px] bg-panel-border rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${Math.min(pct ?? 0, 100)}%`,
            background: danger
              ? 'linear-gradient(90deg,#ef4444,#f87171)'
              : `linear-gradient(90deg,${color},${color}bb)`,
          }}
        />
      </div>
      {sub && <div className="text-[10px] text-ink-muted mt-0.5">{sub}</div>}
    </div>
  );
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const [stats,   setStats]   = useState(null);
  const [counts,  setCounts]  = useState({ domains: 0, containers: 0, users: 0 });
  const [history, setHistory] = useState([]);
  const wsRef = useRef(null);

  useEffect(() => {
    // Initial load
    Promise.all([
      api.get('/api/server/stats'),
      api.get('/api/domains/').catch(() => ({ data: [] })),
      api.get('/api/docker/containers').catch(() => ({ data: [] })),
      api.get('/api/users/').catch(() => ({ data: [] })),
    ]).then(([s, d, c, u]) => {
      setStats(s.data);
      setCounts({
        domains:    Array.isArray(d.data) ? d.data.length : 0,
        containers: Array.isArray(c.data) ? c.data.length : 0,
        users:      Array.isArray(u.data) ? u.data.length : 0,
      });
    });

    // Live stats via WebSocket
    wsRef.current = createWS('/api/server/ws/stats', data => {
      setStats(prev => ({ ...prev, ...data }));
      setHistory(h => [
        ...h.slice(-59),
        {
          t:   new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
          cpu: data.cpu ?? data.cpu_percent ?? 0,
          mem: data.mem ?? data.mem_percent ?? 0,
        },
      ]);
    });

    return () => wsRef.current?.close();
  }, []);

  const cpu  = stats?.cpu_percent  ?? 0;
  const mem  = stats?.mem_percent  ?? 0;
  const disk = stats?.disk_percent ?? 0;
  const swap = stats?.swap_percent ?? 0;
  const netSent = stats?.net_sent_mb ?? 0;
  const netRecv = stats?.net_recv_mb ?? 0;
  const netIf   = stats?.net_interfaces ?? {};
  const cpuCores = stats?.cpu_per_core ?? [];

  return (
    <div className="space-y-5 max-w-6xl">
      <div>
        <h1 className="text-[20px] font-bold text-ink-primary">Dashboard</h1>
        <p className="text-[13px] text-ink-muted mt-0.5">
          System overview · uptime {uptime(stats?.boot_timestamp)}
          {stats && ` · load ${stats.load_1m} / ${stats.load_5m} / ${stats.load_15m}`}
        </p>
      </div>

      {/* ── Top stat cards ───────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          icon={Cpu}       label="CPU Usage"
          value={fmt(cpu, '%')} pct={cpu}
          glowColor="#6366f1" barColor="#a5b4fc"
        />
        <StatCard
          icon={MemoryStick} label="Memory"
          value={fmt(mem, '%')}
          sub={`${stats?.mem_used_mb ?? '—'} / ${stats?.mem_total_mb ?? '—'} MB`}
          pct={mem}
          glowColor="#8b5cf6" barColor="#c4b5fd"
        />
        <StatCard
          icon={HardDrive} label="Disk Usage"
          value={fmt(disk, '%')}
          sub={`${stats?.disk_used_gb ?? '—'} / ${stats?.disk_total_gb ?? '—'} GB`}
          pct={disk}
          glowColor="#10b981" barColor="#6ee7b7"
        />
        <StatCard
          icon={Server} label="Containers"
          value={`${counts.containers}`}
          sub={`${counts.domains} domains · ${counts.users} users`}
          glowColor="#f59e0b" barColor="#fcd34d"
        />
      </div>

      {/* ── Charts + resource gauges ─────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">

        {/* Live CPU + Mem chart */}
        <div className="panel p-4">
          <h2 className="text-[12px] font-semibold text-ink-muted uppercase tracking-wider mb-3">
            CPU &amp; Memory — Live (60s)
          </h2>
          <ResponsiveContainer width="100%" height={130}>
            <AreaChart data={history} margin={{ top: 0, right: 0, left: -28, bottom: 0 }}>
              <defs>
                <linearGradient id="gc" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#6366f1" stopOpacity={0.25}/>
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                </linearGradient>
                <linearGradient id="gm" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#8b5cf6" stopOpacity={0.2}/>
                  <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <XAxis dataKey="t" tick={{ fontSize: 9, fill: '#52525b' }} interval="preserveStartEnd" />
              <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: '#52525b' }} />
              <Tooltip
                contentStyle={{ background: '#111113', border: '1px solid #1f1f23', borderRadius: 8, fontSize: 11 }}
                labelStyle={{ color: '#71717a' }}
              />
              <Area type="monotone" dataKey="cpu" stroke="#6366f1" fill="url(#gc)" strokeWidth={1.5} name="CPU %" dot={false}/>
              <Area type="monotone" dataKey="mem" stroke="#8b5cf6" fill="url(#gm)" strokeWidth={1.5} name="Mem %" dot={false}/>
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Resource gauges */}
        <div className="panel p-4 space-y-3.5">
          <h2 className="text-[12px] font-semibold text-ink-muted uppercase tracking-wider">Resource Usage</h2>
          <GaugeBar label="CPU" pct={cpu} color="#6366f1" sub={`Load: ${stats?.load_1m ?? '—'} / ${stats?.load_5m ?? '—'} / ${stats?.load_15m ?? '—'}`} />
          <GaugeBar label="Memory" pct={mem} color="#8b5cf6" sub={`${stats?.mem_used_mb ?? '—'} MB used · ${stats?.mem_available_mb ?? '—'} MB free`} />
          <GaugeBar label="Disk" pct={disk} color="#10b981" sub={`${stats?.disk_free_gb ?? '—'} GB free of ${stats?.disk_total_gb ?? '—'} GB`} />
          <GaugeBar label="Swap" pct={swap} color="#f59e0b" sub={swap > 0 ? `${stats?.swap_used_mb ?? '—'} / ${stats?.swap_total_mb ?? '—'} MB` : 'No swap active'} />
        </div>
      </div>

      {/* ── Per-core CPU + Network ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">

        {/* Per-core */}
        {cpuCores.length > 0 && (
          <div className="panel p-4">
            <h2 className="text-[12px] font-semibold text-ink-muted uppercase tracking-wider mb-3">
              CPU Cores ({cpuCores.length})
            </h2>
            <ResponsiveContainer width="100%" height={100}>
              <BarChart data={cpuCores.map((v, i) => ({ core: `C${i}`, v }))} margin={{ top: 0, right: 0, left: -28, bottom: 0 }}>
                <XAxis dataKey="core" tick={{ fontSize: 9, fill: '#52525b' }} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: '#52525b' }} />
                <Tooltip
                  contentStyle={{ background: '#111113', border: '1px solid #1f1f23', borderRadius: 8, fontSize: 11 }}
                  formatter={v => [`${v}%`, 'Usage']}
                />
                <Bar dataKey="v" radius={[3, 3, 0, 0]}>
                  {cpuCores.map((v, i) => (
                    <Cell key={i} fill={v > 80 ? '#ef4444' : v > 50 ? '#f59e0b' : '#6366f1'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Network */}
        <div className="panel p-4">
          <h2 className="text-[12px] font-semibold text-ink-muted uppercase tracking-wider mb-3">Network</h2>
          <div className="space-y-2.5">
            {/* Totals */}
            <div className="grid grid-cols-2 gap-2">
              <div className="flex items-center gap-2 bg-panel-elevated rounded-lg p-2.5">
                <ArrowUp size={13} className="text-ok-light flex-shrink-0" />
                <div>
                  <div className="text-[15px] font-bold text-ink-primary">{netSent} MB</div>
                  <div className="text-[10px] text-ink-muted">Total sent</div>
                </div>
              </div>
              <div className="flex items-center gap-2 bg-panel-elevated rounded-lg p-2.5">
                <ArrowDown size={13} className="text-brand-light flex-shrink-0" />
                <div>
                  <div className="text-[15px] font-bold text-ink-primary">{netRecv} MB</div>
                  <div className="text-[10px] text-ink-muted">Total received</div>
                </div>
              </div>
            </div>
            {/* Per interface */}
            {Object.entries(netIf).slice(0, 4).map(([iface, n]) => (
              <div key={iface} className="flex items-center justify-between text-[12px]">
                <span className="text-ink-secondary font-mono">{iface}</span>
                <span className="text-ink-muted">↑ {n.sent_mb} MB &nbsp; ↓ {n.recv_mb} MB</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Quick stats ──────────────────────────────────────────────────── */}
      <div className="panel p-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
        {[
          { icon: Globe,     label: 'Domains',    val: counts.domains    },
          { icon: Container, label: 'Containers', val: counts.containers },
          { icon: Users,     label: 'Users',      val: counts.users      },
          { icon: Clock,     label: 'Uptime',     val: uptime(stats?.boot_timestamp) },
        ].map(({ icon: Icon, label, val }) => (
          <div key={label} className="space-y-1">
            <Icon size={16} className="text-ink-muted mx-auto" />
            <div className="text-[20px] font-bold text-ink-primary">{val ?? '—'}</div>
            <div className="text-[11px] text-ink-muted">{label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
