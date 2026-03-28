import { useState, useEffect, useMemo } from 'react';
import { createColumnHelper } from '@tanstack/react-table';
import { toast } from 'sonner';
import api from '../utils/api';
import { fmtDate } from '../utils/dates';
import DataTable from '../components/DataTable';
import { Globe, Plus, Trash2, RefreshCw, RefreshCcw, RotateCcw, Crown } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

// ── Status badge ──────────────────────────────────────────────────────────────
const STATUS_BADGE = {
  active:    'bg-ok/15 text-ok-light border border-ok/25',
  suspended: 'bg-bad/15 text-bad-light border border-bad/25',
  pending:   'bg-warn/15 text-warn-light border border-warn/25',
};

// ── Service pill definitions ──────────────────────────────────────────────────
const SERVICE_META = {
  ssl:  { label: 'SSL',  title: 'HTTPS / TLS certificate' },
  ssh:  { label: 'SSH',  title: 'SSH / SFTP access' },
  web:  { label: 'Web',  title: 'Web server (container running)' },
  dns:  { label: 'DNS',  title: 'DNS zone provisioned' },
  smtp: { label: 'SMTP', title: 'Outbound mail relay (port 25/587)' },
  imap: { label: 'IMAP', title: 'IMAP mail access (port 143/993)' },
  pop3: { label: 'POP3', title: 'POP3 mail access (port 110/995)' },
};

// ── ServicePills ──────────────────────────────────────────────────────────────
function ServicePills({ services = {} }) {
  if (!services || Object.keys(services).length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1">
      {Object.entries(SERVICE_META).map(([key, meta]) => {
        const status = services[key];
        if (!status) return null;

        const isOk = status === 'ok';
        return (
          <span
            key={key}
            title={`${meta.title} — ${isOk ? 'active' : 'issue detected'}`}
            className={`
              inline-flex items-center gap-1 text-[10px] font-semibold px-1.5 py-0.5
              rounded-full border select-none whitespace-nowrap
              ${isOk
                ? 'bg-ok/10 border-ok/20 text-ok-light'
                : 'bg-warn/10 border-warn/20 text-warn-light'}
            `}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                isOk ? 'bg-ok' : 'bg-warn animate-pulse'
              }`}
            />
            {meta.label}
          </span>
        );
      })}
    </div>
  );
}

// ── Reset DNS dialog ──────────────────────────────────────────────────────────
function ResetDnsDialog({ domain, onConfirm, onCancel, resetting }) {
  const [unlocked, setUnlocked] = useState(false);

  return (
    <div className="card border-warn/30 bg-warn/5 space-y-4">
      <div>
        <p className="text-sm font-semibold text-ink-primary mb-1">
          Reset DNS for <span className="text-warn-light font-mono">{domain?.name}</span>?
        </p>
        <p className="text-xs text-ink-muted">
          This wipes the entire PowerDNS zone and rebuilds it from scratch with
          NS, glue, A, MX, service CNAMEs (imap/smtp/pop/sftp), SPF, DKIM,
          DMARC, MTA-STS, TLS-RPT and CAA records. Existing custom records will
          be lost. This cannot be undone.
        </p>
      </div>

      {/* Unlock slider */}
      <div className="flex items-center gap-3">
        <label className="relative inline-flex items-center cursor-pointer">
          <input
            type="checkbox"
            checked={unlocked}
            onChange={e => setUnlocked(e.target.checked)}
            className="sr-only peer"
          />
          <div className={`
            w-11 h-6 rounded-full peer transition-colors
            after:content-[''] after:absolute after:top-[2px] after:left-[2px]
            after:bg-white after:rounded-full after:h-5 after:w-5
            after:transition-all peer-checked:after:translate-x-full
            ${unlocked ? 'bg-warn' : 'bg-panel-border'}
          `} />
        </label>
        <span className="text-xs text-ink-muted">
          {unlocked ? 'Unlocked — ready to reset' : 'Slide to unlock reset'}
        </span>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => onConfirm(domain.id)}
          disabled={!unlocked || resetting}
          className="btn-primary bg-warn hover:bg-warn/80 border-warn/50 text-xs px-3 py-1.5 disabled:opacity-40"
        >
          {resetting ? 'Resetting…' : 'Reset DNS'}
        </button>
        <button onClick={onCancel} className="btn-ghost text-xs px-3 py-1.5">Cancel</button>
      </div>
    </div>
  );
}

// ── Column helper ─────────────────────────────────────────────────────────────
const col = createColumnHelper();

// ── Page ──────────────────────────────────────────────────────────────────────
export default function DomainsPage() {
  const { user }                        = useAuth();
  const isSuperAdmin                    = user?.role === 'superadmin';
  const [domains,      setDomains]      = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [form,         setForm]         = useState({ name: '', php_version: '8.2', domain_type: 'main' });
  const [adding,       setAdding]       = useState(false);
  const [showForm,     setShowForm]     = useState(false);
  const [deleting,     setDeleting]     = useState(null);
  const [syncing,      setSyncing]      = useState(null);
  const [resetTarget,  setResetTarget]  = useState(null);   // domain object
  const [resetting,    setResetting]    = useState(false);
  const [settingMaster, setSettingMaster] = useState(null); // domain id

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/domains/');
      setDomains(data);
    } catch {
      toast.error('Failed to load domains');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const addDomain = async e => {
    e.preventDefault();
    setAdding(true);
    try {
      await api.post('/api/domains/', form);
      toast.success(`Domain ${form.name} added`);
      setShowForm(false);
      setForm({ name: '', php_version: '8.2', domain_type: 'main' });
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Error adding domain');
    } finally {
      setAdding(false);
    }
  };

  const syncDns = async name => {
    setSyncing(name);
    try {
      await api.post(`/api/dns/zones/${encodeURIComponent(name)}/ensure`);
      toast.success(`DNS zone synced for ${name}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'DNS sync failed');
    } finally {
      setSyncing(null);
    }
  };

  const confirmDelete = async id => {
    try {
      await api.delete(`/api/domains/${id}`);
      toast.success('Domain deleted');
      setDeleting(null);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Delete failed');
    }
  };

  const setMasterDomain = async id => {
    setSettingMaster(id);
    try {
      const { data } = await api.post(`/api/domains/${id}/set-master`);
      toast.success(`Master domain set to ${data.panel_domain}`);
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to set master domain');
    } finally {
      setSettingMaster(null);
    }
  };

  const confirmResetDns = async id => {
    setResetting(true);
    try {
      await api.post(`/api/domains/${id}/reset-dns`);
      toast.success(`DNS reset for ${resetTarget?.name}`);
      setResetTarget(null);
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'DNS reset failed');
    } finally {
      setResetting(false);
    }
  };

  const columns = useMemo(() => [
    col.accessor('name', {
      header: 'Domain',
      cell: i => (
        <div className="flex items-center gap-2">
          <span className="font-medium text-ink-primary">{i.getValue()}</span>
          {i.row.original.is_master && (
            <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/25">
              <Crown size={9} /> master
            </span>
          )}
        </div>
      ),
    }),
    col.accessor('domain_type', {
      header: 'Type',
      cell: i => (
        <span className="text-ink-secondary capitalize text-xs">{i.getValue()}</span>
      ),
    }),
    col.accessor('status', {
      header: 'Status',
      cell: i => (
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_BADGE[i.getValue()] ?? 'bg-panel-elevated text-ink-muted'}`}>
          {i.getValue()}
        </span>
      ),
    }),
    col.accessor('php_version', {
      header: 'PHP',
      cell: i => (
        <span className="text-ink-muted text-xs">PHP {i.getValue()}</span>
      ),
    }),
    col.accessor('services', {
      header: 'Services',
      enableSorting: false,
      cell: i => <ServicePills services={i.getValue()} />,
    }),
    col.accessor('created_at', {
      header: 'Created',
      cell: i => (
        <span className="text-ink-muted text-xs">{fmtDate(i.getValue())}</span>
      ),
    }),
    col.display({
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex items-center gap-1">
          {isSuperAdmin && (
            <button
              onClick={() => setMasterDomain(row.original.id)}
              disabled={settingMaster === row.original.id || row.original.is_master}
              className={`p-1 rounded transition-colors
                ${row.original.is_master
                  ? 'text-amber-400 cursor-default'
                  : 'text-ink-muted hover:text-amber-400'}
                ${settingMaster === row.original.id ? 'animate-pulse' : ''}`}
              title={row.original.is_master ? 'Current master domain' : 'Set as master domain'}
            >
              <Crown size={13} />
            </button>
          )}
          <button
            onClick={() => syncDns(row.original.name)}
            disabled={syncing === row.original.name}
            className="text-ink-muted hover:text-brand transition-colors p-1 rounded"
            title="Sync DNS zone"
          >
            <RefreshCcw size={13} className={syncing === row.original.name ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={() => { setResetTarget(row.original); setDeleting(null); }}
            className="text-ink-muted hover:text-warn-light transition-colors p-1 rounded"
            title="Reset DNS to default"
          >
            <RotateCcw size={13} />
          </button>
          <button
            onClick={() => { setDeleting(row.original.id); setResetTarget(null); }}
            className="text-ink-muted hover:text-bad transition-colors p-1 rounded"
            title="Delete domain"
          >
            <Trash2 size={13} />
          </button>
        </div>
      ),
    }),
  ], [syncing, settingMaster, isSuperAdmin]);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-ink-primary flex items-center gap-2">
          <Globe size={20} /> Domains
        </h1>
        <div className="flex gap-2">
          <button onClick={load} className="btn-ghost" disabled={loading}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
          <button onClick={() => setShowForm(s => !s)} className="btn-primary flex items-center gap-2">
            <Plus size={14} /> Add Domain
          </button>
        </div>
      </div>

      {/* Pill legend */}
      <div className="flex flex-wrap items-center gap-3 text-[11px] text-ink-muted px-1">
        <span className="font-medium text-ink-faint uppercase tracking-wide text-[10px]">Legend:</span>
        <span className="inline-flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-ok" /> Active
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-warn animate-pulse" /> Issue
        </span>
        <span className="inline-flex items-center gap-1 opacity-40">
          <span className="w-1.5 h-1.5 rounded-full bg-ink-muted" /> Hidden = not installed
        </span>
      </div>

      {showForm && (
        <div className="card">
          <h2 className="text-sm font-semibold text-ink-primary mb-4">Add New Domain</h2>
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
              <button type="submit" disabled={adding} className="btn-primary">
                {adding ? 'Adding…' : 'Add Domain'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Reset DNS dialog */}
      {resetTarget && (
        <ResetDnsDialog
          domain={resetTarget}
          onConfirm={confirmResetDns}
          onCancel={() => setResetTarget(null)}
          resetting={resetting}
        />
      )}

      {/* Delete confirm */}
      {deleting && (
        <div className="card border-bad/30 bg-bad/5">
          <p className="text-sm text-ink-primary mb-3">Delete this domain? This cannot be undone.</p>
          <div className="flex gap-2">
            <button onClick={() => confirmDelete(deleting)} className="btn-primary bg-bad hover:bg-bad/80 border-bad/50 text-xs px-3 py-1.5">
              Delete
            </button>
            <button onClick={() => setDeleting(null)} className="btn-ghost text-xs px-3 py-1.5">Cancel</button>
          </div>
        </div>
      )}

      <DataTable columns={columns} data={domains} loading={loading} emptyMessage="No domains yet — add one above" />
    </div>
  );
}
