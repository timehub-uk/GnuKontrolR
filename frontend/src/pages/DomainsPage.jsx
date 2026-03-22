import { useState, useEffect } from 'react';
import api from '../utils/api';
import { Globe, Plus, Trash2, RefreshCw, ShieldCheck } from 'lucide-react';

export default function DomainsPage() {
  const [domains, setDomains] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm]       = useState({ name: '', php_version: '8.2', domain_type: 'main' });
  const [adding, setAdding]   = useState(false);
  const [showForm, setShowForm] = useState(false);

  const load = async () => {
    setLoading(true);
    const { data } = await api.get('/api/domains/');
    setDomains(data);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const addDomain = async e => {
    e.preventDefault();
    setAdding(true);
    try {
      await api.post('/api/domains/', form);
      setShowForm(false);
      setForm({ name: '', php_version: '8.2', domain_type: 'main' });
      await load();
    } catch (err) {
      alert(err.response?.data?.detail || 'Error adding domain');
    } finally { setAdding(false); }
  };

  const deleteDomain = async id => {
    if (!confirm('Delete this domain?')) return;
    await api.delete(`/api/domains/${id}`);
    load();
  };

  const statusColor = s => ({ active: 'badge-green', suspended: 'badge-red', pending: 'badge-yellow' }[s] || 'badge-blue');

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2"><Globe size={20} />Domains</h1>
        <div className="flex gap-2">
          <button onClick={load} className="btn-ghost"><RefreshCw size={14} /></button>
          <button onClick={() => setShowForm(s => !s)} className="btn-primary flex items-center gap-2">
            <Plus size={14} /> Add Domain
          </button>
        </div>
      </div>

      {showForm && (
        <div className="card">
          <h2 className="text-sm font-semibold text-white mb-4">Add New Domain</h2>
          <form onSubmit={addDomain} className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <input className="input" placeholder="example.com" value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required />
            <select className="input" value={form.domain_type}
              onChange={e => setForm(f => ({ ...f, domain_type: e.target.value }))}>
              <option value="main">Main Domain</option>
              <option value="addon">Addon Domain</option>
              <option value="subdomain">Subdomain</option>
              <option value="parked">Parked</option>
              <option value="redirect">Redirect</option>
            </select>
            <select className="input" value={form.php_version}
              onChange={e => setForm(f => ({ ...f, php_version: e.target.value }))}>
              {['8.3','8.2','8.1','8.0','7.4'].map(v => <option key={v}>{v}</option>)}
            </select>
            <div className="md:col-span-3 flex gap-2 justify-end">
              <button type="button" onClick={() => setShowForm(false)} className="btn-ghost">Cancel</button>
              <button type="submit" disabled={adding} className="btn-primary">{adding ? 'Adding…' : 'Add Domain'}</button>
            </div>
          </form>
        </div>
      )}

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-panel-700 text-gray-400 text-xs uppercase">
            <tr>
              {['Domain','Type','Status','PHP','SSL','Created','Actions'].map(h => (
                <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-panel-700">
            {loading ? (
              <tr><td colSpan={7} className="text-center py-8 text-gray-500">Loading…</td></tr>
            ) : domains.length === 0 ? (
              <tr><td colSpan={7} className="text-center py-8 text-gray-500">No domains yet</td></tr>
            ) : domains.map(d => (
              <tr key={d.id} className="hover:bg-panel-700/50 transition-colors">
                <td className="px-4 py-3 font-medium text-white">{d.name}</td>
                <td className="px-4 py-3 text-gray-400 capitalize">{d.domain_type}</td>
                <td className="px-4 py-3"><span className={statusColor(d.status)}>{d.status}</span></td>
                <td className="px-4 py-3 text-gray-400">PHP {d.php_version}</td>
                <td className="px-4 py-3">
                  {d.ssl_enabled ? <ShieldCheck size={14} className="text-green-400" /> : <span className="text-gray-600">—</span>}
                </td>
                <td className="px-4 py-3 text-gray-500 text-xs">{new Date(d.created_at).toLocaleDateString()}</td>
                <td className="px-4 py-3">
                  <button onClick={() => deleteDomain(d.id)} className="text-gray-500 hover:text-red-400 transition-colors">
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
