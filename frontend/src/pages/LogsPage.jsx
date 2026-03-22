import { useState, useEffect, useRef } from 'react';
import api from '../utils/api';
import { ScrollText, RefreshCw } from 'lucide-react';

const LOG_SOURCES = [
  { id: 'nginx_access',  label: 'Nginx Access' },
  { id: 'nginx_error',   label: 'Nginx Error' },
  { id: 'mysql',         label: 'MySQL' },
  { id: 'postfix',       label: 'Mail (Postfix)' },
  { id: 'webpanel',      label: 'Panel' },
];

export default function LogsPage() {
  const [source, setSource] = useState('nginx_access');
  const [lines, setLines]   = useState([]);
  const [domains, setDomains] = useState([]);
  const [domain, setDomain]   = useState('');
  const bottomRef = useRef(null);

  useEffect(() => {
    api.get('/api/domains/').then(r => setDomains(r.data));
  }, []);

  const fetchLogs = async () => {
    if (domain) {
      const { data } = await api.get(`/api/docker/containers/${domain}/logs?tail=300`);
      setLines((data.logs || '').split('\n').filter(Boolean));
    } else {
      setLines(['← Select a domain container or log source to view logs']);
    }
  };

  useEffect(() => { bottomRef.current?.scrollIntoView(); }, [lines]);

  return (
    <div className="space-y-5 h-full flex flex-col">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2"><ScrollText size={20} />Logs</h1>
        <button onClick={fetchLogs} className="btn-ghost flex items-center gap-2"><RefreshCw size={14} /> Refresh</button>
      </div>
      <div className="flex gap-3 flex-wrap">
        <select className="input max-w-xs" value={source} onChange={e => setSource(e.target.value)}>
          {LOG_SOURCES.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
        <select className="input max-w-xs" value={domain} onChange={e => setDomain(e.target.value)}>
          <option value="">— Container logs —</option>
          {domains.map(d => <option key={d.id} value={d.name}>{d.name}</option>)}
        </select>
        <button onClick={fetchLogs} className="btn-primary">Load</button>
      </div>
      <div className="flex-1 bg-black/60 rounded-xl border border-panel-600 overflow-auto p-4 font-mono text-xs min-h-96">
        {lines.length === 0
          ? <span className="text-gray-500">No logs loaded.</span>
          : lines.map((l, i) => (
            <div key={i} className={`leading-relaxed ${l.includes('error') || l.includes('ERROR') ? 'text-red-400' : l.includes('warn') ? 'text-yellow-400' : 'text-green-300'}`}>
              {l}
            </div>
          ))
        }
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
