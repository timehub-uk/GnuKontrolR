import { useState, useEffect } from 'react';
import api from '../utils/api';
import { Server, Play, Square, RotateCcw, RefreshCw } from 'lucide-react';

const SERVICE_META = {
  nginx:       { label: 'Nginx',        desc: 'Web server / reverse proxy', icon: '🌐' },
  traefik:     { label: 'Traefik',      desc: 'Edge router & SSL termination', icon: '🔀' },
  'mysql':     { label: 'MySQL',        desc: 'Master database server', icon: '🗄️' },
  'powerdns':  { label: 'PowerDNS',     desc: 'Authoritative DNS server', icon: '🌍' },
  'postfix':   { label: 'Postfix',      desc: 'SMTP mail server', icon: '📨' },
  'dovecot':   { label: 'Dovecot',      desc: 'IMAP/POP3 mail server', icon: '📥' },
  'redis':     { label: 'Redis',        desc: 'In-memory cache', icon: '⚡' },
  'php8.2-fpm':{ label: 'PHP 8.2 FPM', desc: 'PHP FastCGI process manager', icon: '🐘' },
};

export default function ServicesPage() {
  const [services, setServices] = useState({});
  const [loading, setLoading]   = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/server/services');
      setServices(data);
    } catch { setServices({}); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const control = async (svc, action) => {
    await api.post(`/api/server/services/${svc}/${action}`);
    setTimeout(load, 1000);
  };

  const stateColor = s => {
    if (s === 'active') return 'badge-green';
    if (s === 'inactive' || s === 'failed') return 'badge-red';
    return 'badge-yellow';
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2"><Server size={20} />Master Services</h1>
        <button onClick={load} className="btn-ghost"><RefreshCw size={14} /></button>
      </div>

      <p className="text-sm text-gray-400">
        Each service runs as its own Docker container. Customer domain containers connect to these master services internally via <code className="bg-panel-700 px-1 rounded text-xs">webpanel_net</code>.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Object.entries(SERVICE_META).map(([key, meta]) => {
          const state = services[key] || 'unknown';
          return (
            <div key={key} className="card flex items-center gap-4">
              <div className="text-2xl">{meta.icon}</div>
              <div className="flex-1 min-w-0">
                <div className="font-medium text-white text-sm">{meta.label}</div>
                <div className="text-xs text-gray-500">{meta.desc}</div>
                <div className="mt-1"><span className={stateColor(state)}>{loading ? '…' : state}</span></div>
              </div>
              <div className="flex items-center gap-1.5">
                <button onClick={() => control(key, 'start')}   title="Start"   className="text-green-500 hover:text-green-300 p-1"><Play size={14} /></button>
                <button onClick={() => control(key, 'stop')}    title="Stop"    className="text-yellow-500 hover:text-yellow-300 p-1"><Square size={14} /></button>
                <button onClick={() => control(key, 'restart')} title="Restart" className="text-blue-400 hover:text-blue-200 p-1"><RotateCcw size={14} /></button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
