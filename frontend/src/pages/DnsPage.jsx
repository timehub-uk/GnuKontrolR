import { useState, useEffect } from 'react';
import api from '../utils/api';
import { toastSuccess, toastError } from '../utils/toast';
import { Globe, Plus, Trash2, RefreshCw, AlertTriangle, Loader, ShieldCheck } from 'lucide-react';

const DNS_PORTS = [
  { port: 53,  proto: 'UDP', desc: 'DNS queries' },
  { port: 53,  proto: 'TCP', desc: 'DNS zone transfers / large responses' },
];

function StatusPill({ state }) {
  const map = {
    active:         { cls: 'bg-ok/15 text-ok-light border-ok/25',      dot: 'bg-ok',      label: 'Up' },
    inactive:       { cls: 'bg-bad/15 text-bad-light border-bad/25',    dot: 'bg-bad',     label: 'Down' },
    failed:         { cls: 'bg-bad/15 text-bad-light border-bad/25',    dot: 'bg-bad',     label: 'Failed' },
    restarting:     { cls: 'bg-warn/15 text-warn-light border-warn/25', dot: 'bg-warn',    label: 'Restarting' },
    'not installed':{ cls: 'bg-panel-elevated text-ink-muted border-panel-border', dot: 'bg-ink-muted', label: 'Not installed' },
  };
  const s = map[state] ?? { cls: 'bg-panel-elevated text-ink-muted border-panel-border', dot: 'bg-ink-muted', label: state || '…' };
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full border ${s.cls}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}

function PortPill({ port, proto }) {
  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-mono font-semibold px-2 py-0.5 rounded-md bg-brand/10 text-brand-light border border-brand/20">
      :{port} {proto}
    </span>
  );
}

export default function DnsPage() {
  const [domains,   setDomains]   = useState([]);
  const [selected,  setSelected]  = useState('');
  const [records,   setRecords]   = useState([]);
  const [dnsState,  setDnsState]  = useState(null);
  const [loading,   setLoading]   = useState(false);
  const [ensuring,  setEnsuring]  = useState(false);
  const [form, setForm] = useState({ type: 'A', name: '', content: '', ttl: 300 });

  const DNS_TYPES = ['A', 'AAAA', 'CNAME', 'MX', 'TXT', 'NS', 'SRV', 'CAA'];

  useEffect(() => {
    api.get('/api/domains').then(r => {
      const list = r.data?.domains || r.data || [];
      setDomains(list);
      if (list.length) setSelected(list[0].name || list[0]);
    }).catch(() => {});

    api.get('/api/server/services').then(r => {
      setDnsState(r.data?.powerdns ?? 'unknown');
    }).catch(() => setDnsState('unknown'));
  }, []);

  // Flatten PowerDNS rrsets into display rows
  const parseRrsets = (rrsets) => {
    const rows = [];
    for (const rrset of (rrsets || [])) {
      const name = (rrset.name || '').replace(/\.$/, '');
      for (const rec of (rrset.records || [])) {
        if (!rec.disabled) {
          rows.push({ type: rrset.type, name, content: rec.content, ttl: rrset.ttl });
        }
      }
    }
    return rows;
  };

  const loadRecords = async () => {
    if (!selected) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/api/dns/zones/${selected}`);
      const rrsets = data?.rrsets || data?.records || [];
      setRecords(parseRrsets(rrsets));
    } catch (e) {
      toastError(e?.response?.data?.detail || 'Failed to load DNS records');
      setRecords([]);
    } finally {
      setLoading(false);
    }
  };

  const handleEnsureZone = async () => {
    if (!selected) return;
    setEnsuring(true);
    try {
      await api.post(`/api/dns/zones/ensure?zone=${encodeURIComponent(selected)}`);
      toastSuccess(`Zone ${selected} ensured in PowerDNS`);
      await loadRecords();
    } catch (e) {
      toastError(e?.response?.data?.detail || 'Failed to create zone');
    } finally {
      setEnsuring(false);
    }
  };

  const handleAddRecord = async () => {
    if (!selected || !form.name || !form.content) return;
    try {
      await api.post(`/api/dns/zones/${selected}/records`, {
        name: form.name,
        type: form.type,
        content: form.content,
        ttl: form.ttl,
      });
      toastSuccess('DNS record added');
      setForm({ type: 'A', name: '', content: '', ttl: 300 });
      await loadRecords();
    } catch (e) {
      toastError(e?.response?.data?.detail || 'Failed to add record');
    }
  };

  const handleDeleteRecord = async (name, type) => {
    if (!selected) return;
    try {
      await api.delete(`/api/dns/zones/${selected}/records?name=${encodeURIComponent(name)}&type=${encodeURIComponent(type)}`);
      toastSuccess('Record deleted');
      await loadRecords();
    } catch (e) {
      toastError(e?.response?.data?.detail || 'Failed to delete record');
    }
  };

  return (
    <div className="space-y-5">

      {/* Header */}
      <div>
        <h1 className="text-[20px] font-bold text-ink-primary flex items-center gap-2">
          <Globe size={20} className="text-brand" /> DNS Manager
        </h1>
        <p className="text-[13px] text-ink-muted mt-0.5">
          DNS is managed by the PowerDNS master container.
        </p>
      </div>

      {/* Status banner */}
      <div className="panel p-4 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-3">
          <span className="text-[13px] font-semibold text-ink-primary">PowerDNS</span>
          <StatusPill state={dnsState} />
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[11px] text-ink-muted">Serving on:</span>
          {DNS_PORTS.map(p => (
            <PortPill key={`${p.port}-${p.proto}`} port={p.port} proto={p.proto} />
          ))}
        </div>
        {dnsState && dnsState !== 'active' && dnsState !== null && (
          <div className="flex items-center gap-1.5 text-[12px] text-warn-light ml-auto">
            <AlertTriangle size={13} /> PowerDNS is not running — DNS will not resolve.
          </div>
        )}
      </div>

      {/* Domain selector */}
      <div className="flex gap-3 flex-wrap">
        <select
          className="input w-56"
          value={selected}
          onChange={e => { setSelected(e.target.value); setRecords([]); }}
        >
          {domains.length === 0 && <option value="">No domains</option>}
          {domains.map(d => {
            const name = d.name || d;
            return <option key={name} value={name}>{name}</option>;
          })}
        </select>
        <button
          onClick={loadRecords}
          disabled={loading || !selected}
          className="btn-ghost flex items-center gap-1.5 text-sm py-1.5 px-3 disabled:opacity-50"
        >
          {loading ? <Loader size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Load Records
        </button>
        <button
          onClick={handleEnsureZone}
          disabled={ensuring || !selected}
          className="btn-ghost flex items-center gap-1.5 text-sm py-1.5 px-3 disabled:opacity-50 text-brand-light"
        >
          {ensuring ? <Loader size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
          Create Zone
        </button>
      </div>

      {/* Add record form */}
      <div className="panel p-4">
        <h2 className="text-[13px] font-semibold text-ink-primary mb-3">Add DNS Record</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <select className="input" value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))}>
            {DNS_TYPES.map(t => <option key={t}>{t}</option>)}
          </select>
          <input className="input" placeholder="Name (@ for root)" value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          <input className="input md:col-span-2" placeholder="Content / Value" value={form.content}
            onChange={e => setForm(f => ({ ...f, content: e.target.value }))} />
          <input className="input" type="number" placeholder="TTL" value={form.ttl}
            onChange={e => setForm(f => ({ ...f, ttl: parseInt(e.target.value) || 300 }))} />
        </div>
        <button
          onClick={handleAddRecord}
          disabled={!selected || !form.name || !form.content}
          className="btn-primary mt-3 flex items-center gap-1.5 text-sm disabled:opacity-50"
        >
          <Plus size={14} /> Add Record
        </button>
      </div>

      {/* Records table */}
      <div className="panel overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-panel-border">
              {['Type', 'Name', 'Content', 'TTL', 'Actions'].map(h => (
                <th key={h} className="tbl-head">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="text-center py-10 text-ink-muted text-sm">
                  <Loader size={16} className="animate-spin inline mr-2" />Loading records…
                </td>
              </tr>
            ) : records.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-center py-10 text-ink-muted text-sm">
                  Select a domain and click <span className="text-brand-light">Load Records</span> to view DNS records.
                </td>
              </tr>
            ) : records.map((r, i) => (
              <tr key={i} className="border-b border-panel-border/50 hover:bg-panel-elevated transition-colors">
                <td className="tbl-cell"><span className="font-mono text-xs bg-panel-elevated px-1.5 py-0.5 rounded">{r.type}</span></td>
                <td className="tbl-cell font-mono text-xs">{r.name}</td>
                <td className="tbl-cell font-mono text-xs text-ink-secondary">{r.content}</td>
                <td className="tbl-cell text-ink-muted">{r.ttl}</td>
                <td className="tbl-cell">
                  <button
                    onClick={() => handleDeleteRecord(r.name, r.type)}
                    className="text-ink-muted hover:text-bad-light transition-colors p-1"
                    title="Delete record"
                  >
                    <Trash2 size={13} />
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
