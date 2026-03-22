import { useState, useEffect } from 'react';
import api from '../utils/api';
import { Globe, Plus, Trash2, RefreshCw } from 'lucide-react';

export default function DnsPage() {
  const [domains, setDomains] = useState([]);
  const [selected, setSelected] = useState('');
  const [records, setRecords]   = useState([]);
  const [form, setForm] = useState({ type: 'A', name: '', content: '', ttl: 300 });

  useEffect(() => {
    api.get('/api/domains/').then(r => {
      setDomains(r.data);
      if (r.data.length) setSelected(r.data[0].name);
    });
  }, []);

  const DNS_TYPES = ['A','AAAA','CNAME','MX','TXT','NS','SRV','CAA'];

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-white flex items-center gap-2"><Globe size={20} />DNS Manager</h1>
      <div className="card text-xs text-gray-400 bg-blue-900/10 border-blue-800">
        DNS is managed by the <strong className="text-blue-300">PowerDNS master container</strong>. Each customer domain's nameservers point to this server.
      </div>

      {/* Domain selector */}
      <div className="flex gap-3">
        <select className="input max-w-xs" value={selected} onChange={e => setSelected(e.target.value)}>
          {domains.map(d => <option key={d.id}>{d.name}</option>)}
        </select>
        <button className="btn-primary flex items-center gap-2"><RefreshCw size={14} /> Load Records</button>
      </div>

      {/* Add record form */}
      <div className="card">
        <h2 className="text-sm font-semibold text-white mb-3">Add DNS Record</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <select className="input" value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))}>
            {DNS_TYPES.map(t => <option key={t}>{t}</option>)}
          </select>
          <input className="input" placeholder="Name (@ for root)" value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          <input className="input md:col-span-2" placeholder="Content / Value" value={form.content}
            onChange={e => setForm(f => ({ ...f, content: e.target.value }))} />
          <input className="input" type="number" placeholder="TTL" value={form.ttl}
            onChange={e => setForm(f => ({ ...f, ttl: parseInt(e.target.value) }))} />
        </div>
        <button className="btn-primary mt-3 flex items-center gap-2"><Plus size={14} /> Add Record</button>
      </div>

      {/* Records table */}
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-panel-700 text-gray-400 text-xs uppercase">
            <tr>{['Type','Name','Content','TTL','Actions'].map(h =>
              <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            <tr><td colSpan={5} className="text-center py-8 text-gray-500">Select a domain to view records</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
