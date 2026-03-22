import { useState, useEffect, useRef } from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { createWS } from '../utils/ws';
import api from '../utils/api';
import { Cpu, MemoryStick, HardDrive, Globe, Container, Users } from 'lucide-react';

function StatCard({ icon: Icon, label, value, sub, color }) {
  return (
    <div className="card flex items-center gap-4">
      <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${color}`}>
        <Icon size={22} className="text-white" />
      </div>
      <div>
        <div className="text-2xl font-bold text-white">{value}</div>
        <div className="text-xs text-gray-400">{label}</div>
        {sub && <div className="text-xs text-gray-500 mt-0.5">{sub}</div>}
      </div>
    </div>
  );
}

function GaugeBar({ label, pct, color }) {
  return (
    <div>
      <div className="flex justify-between text-xs text-gray-400 mb-1">
        <span>{label}</span><span>{pct}%</span>
      </div>
      <div className="h-2 bg-panel-600 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats]   = useState(null);
  const [counts, setCounts] = useState({ domains: 0, users: 0, containers: 0 });
  const [history, setHistory] = useState([]);
  const wsRef = useRef(null);

  useEffect(() => {
    // Load initial data via AJAX
    Promise.all([
      api.get('/api/server/stats'),
      api.get('/api/domains/'),
      api.get('/api/docker/containers').catch(() => ({ data: [] })),
    ]).then(([s, d, c]) => {
      setStats(s.data);
      setCounts(prev => ({ ...prev, domains: d.data.length, containers: c.data.length }));
    });

    // Real-time stats via WebSocket
    wsRef.current = createWS('/api/server/ws/stats', data => {
      setStats(prev => ({ ...prev, ...data }));
      setHistory(h => [...h.slice(-29), { t: new Date().toLocaleTimeString(), cpu: data.cpu, mem: data.mem }]);
    });

    return () => wsRef.current?.close();
  }, []);

  const cpu  = stats?.cpu_percent  ?? 0;
  const mem  = stats?.mem_percent  ?? 0;
  const disk = stats?.disk_percent ?? 0;

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-white">Dashboard</h1>

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard icon={Globe}      label="Domains"    value={counts.domains}    color="bg-blue-600"   />
        <StatCard icon={Container}  label="Containers" value={counts.containers} color="bg-purple-600" />
        <StatCard icon={Users}      label="Users"      value="—"                 color="bg-green-600"  />
        <StatCard icon={HardDrive}  label="Disk Used"
          value={`${stats?.disk_used_gb ?? 0} GB`}
          sub={`of ${stats?.disk_total_gb ?? 0} GB`}
          color="bg-orange-600" />
      </div>

      {/* Gauges */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card space-y-4">
          <h2 className="text-sm font-semibold text-white">Resource Usage</h2>
          <GaugeBar label="CPU"    pct={cpu}  color={cpu  > 80 ? 'bg-red-500'    : 'bg-blue-500'}   />
          <GaugeBar label="Memory" pct={mem}  color={mem  > 80 ? 'bg-red-500'    : 'bg-purple-500'} />
          <GaugeBar label="Disk"   pct={disk} color={disk > 90 ? 'bg-red-500'    : 'bg-orange-500'} />
        </div>

        {/* Live chart */}
        <div className="card">
          <h2 className="text-sm font-semibold text-white mb-3">Live CPU &amp; Memory (30s)</h2>
          <ResponsiveContainer width="100%" height={140}>
            <AreaChart data={history} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
              <XAxis dataKey="t" tick={{ fontSize: 9, fill: '#6b7280' }} interval="preserveStartEnd" />
              <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: '#6b7280' }} />
              <Tooltip contentStyle={{ background: '#1f2937', border: '1px solid #374151', fontSize: 11 }} />
              <Area type="monotone" dataKey="cpu" stroke="#3b82f6" fill="#3b82f620" strokeWidth={1.5} name="CPU %" />
              <Area type="monotone" dataKey="mem" stroke="#a855f7" fill="#a855f720" strokeWidth={1.5} name="Mem %" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Quick stats */}
      {stats && (
        <div className="card grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
          {[
            { label: 'CPU', val: `${cpu}%` },
            { label: 'RAM', val: `${stats.mem_used_mb} MB` },
            { label: 'Net ↑', val: `${stats.net_sent_mb} MB` },
            { label: 'Net ↓', val: `${stats.net_recv_mb} MB` },
          ].map(x => (
            <div key={x.label}>
              <div className="text-lg font-bold text-white">{x.val}</div>
              <div className="text-xs text-gray-400">{x.label}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
