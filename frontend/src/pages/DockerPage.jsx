import { useState, useEffect } from 'react';
import api from '../utils/api';
import { Container, Play, Square, RotateCcw, Trash2, Terminal, RefreshCw } from 'lucide-react';

export default function DockerPage() {
  const [containers, setContainers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [logs, setLogs]  = useState({ show: false, domain: '', content: '' });

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/docker/containers');
      setContainers(data);
    } catch { setContainers([]); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const action = async (domain, act) => {
    await api.post(`/api/docker/containers/${domain}/action`, { action: act });
    load();
  };

  const viewLogs = async domain => {
    const { data } = await api.get(`/api/docker/containers/${domain}/logs?tail=200`);
    setLogs({ show: true, domain, content: data.logs });
  };

  const stateColor = s => {
    if (s?.toLowerCase().includes('up') || s?.toLowerCase() === 'running') return 'badge-green';
    if (s?.toLowerCase().includes('exit')) return 'badge-red';
    return 'badge-yellow';
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2"><Container size={20} />Docker Containers</h1>
        <button onClick={load} className="btn-ghost"><RefreshCw size={14} /></button>
      </div>

      <div className="card text-xs text-gray-400 bg-blue-900/10 border-blue-800">
        Each domain runs in its own isolated Docker container with memory/CPU limits, read-only filesystem, and separate network namespace.
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-panel-700 text-gray-400 text-xs uppercase">
            <tr>
              {['Container','Image','State','CPU','Memory','Ports','Actions'].map(h => (
                <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-panel-700">
            {loading ? (
              <tr><td colSpan={7} className="text-center py-8 text-gray-500">Loading…</td></tr>
            ) : containers.length === 0 ? (
              <tr><td colSpan={7} className="text-center py-8 text-gray-500">No containers found</td></tr>
            ) : containers.map((c, i) => (
              <tr key={i} className="hover:bg-panel-700/50">
                <td className="px-4 py-3 font-mono text-xs text-white">{c.Names || c.Name || '—'}</td>
                <td className="px-4 py-3 text-gray-400 text-xs truncate max-w-xs">{c.Image || '—'}</td>
                <td className="px-4 py-3"><span className={stateColor(c.State || c.Status)}>{c.State || c.Status || '—'}</span></td>
                <td className="px-4 py-3 text-gray-400">{c.CPUPerc || '—'}</td>
                <td className="px-4 py-3 text-gray-400">{c.MemUsage || '—'}</td>
                <td className="px-4 py-3 text-gray-500 text-xs">{c.Ports || '—'}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <button title="Start"   onClick={() => action(c.Names, 'start')}   className="text-green-500 hover:text-green-300"><Play size={13} /></button>
                    <button title="Stop"    onClick={() => action(c.Names, 'stop')}    className="text-yellow-500 hover:text-yellow-300"><Square size={13} /></button>
                    <button title="Restart" onClick={() => action(c.Names, 'restart')} className="text-blue-400 hover:text-blue-200"><RotateCcw size={13} /></button>
                    <button title="Logs"    onClick={() => viewLogs(c.Names)}          className="text-gray-400 hover:text-white"><Terminal size={13} /></button>
                    <button title="Remove"  onClick={() => action(c.Names, 'kill')}    className="text-gray-600 hover:text-red-400"><Trash2 size={13} /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {logs.show && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
          <div className="bg-panel-800 rounded-xl border border-panel-600 w-full max-w-3xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-5 py-3 border-b border-panel-600">
              <span className="text-sm font-medium text-white">Logs — {logs.domain}</span>
              <button onClick={() => setLogs(l => ({ ...l, show: false }))} className="text-gray-400 hover:text-white">✕</button>
            </div>
            <pre className="flex-1 overflow-auto p-4 text-xs text-green-400 font-mono leading-relaxed bg-black/40 rounded-b-xl">
              {logs.content || 'No logs available.'}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
