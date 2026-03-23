/**
 * ConfigBackupsPanel
 * Shows the 3-deep rolling config snapshots for a domain.
 * Lets admins one-click restore any snapshot for nginx / php / env / ssl.
 *
 * Props:
 *   domain   string  — the domain whose backups to display
 */
import { useState, useEffect, useCallback } from 'react';
import {
  History, RotateCcw, ChevronDown, ChevronRight,
  CheckCircle, AlertCircle, Loader, ShieldCheck,
} from 'lucide-react';
import api from '../utils/api';

const AREAS = [
  { id: 'nginx', label: 'Nginx Config',  icon: '⚙️' },
  { id: 'php',   label: 'PHP Settings',  icon: '🐘' },
  { id: 'env',   label: 'Environment',   icon: '🔐' },
  { id: 'ssl',   label: 'SSL / TLS',     icon: '🔒' },
];

function SnapshotRow({ snap, filename, area, domain, onRestored }) {
  const [state, setState] = useState('idle');   // idle | confirming | restoring | done | err
  const [msg,   setMsg]   = useState('');

  async function restore() {
    if (state === 'confirming') {
      setState('restoring');
      try {
        await api.post(`/api/container/${domain}/restore/${area}`, {
          filename,
          ts: snap.ts,
        });
        setState('done');
        setMsg('Restored successfully');
        onRestored?.();
      } catch (e) {
        setState('err');
        setMsg(e?.response?.data?.detail || 'Restore failed');
      }
    } else {
      setState('confirming');
    }
  }

  const dt = new Date(snap.ts * 1000);
  const age = _humanAge(snap.ts);

  return (
    <div className="flex items-center justify-between py-1.5 px-2 rounded hover:bg-panel-700/40 group">
      <div className="flex items-center gap-2 text-xs">
        <History size={12} className="text-gray-500 flex-shrink-0" />
        <span className="text-gray-300 font-mono">{dt.toLocaleString()}</span>
        <span className="text-gray-500">({age})</span>
        <span className="text-gray-600">{(snap.size / 1024).toFixed(1)} KB</span>
      </div>

      <div className="flex items-center gap-1.5">
        {msg && (
          <span className={`text-xs ${state === 'done' ? 'text-green-400' : 'text-red-400'}`}>
            {msg}
          </span>
        )}

        {state === 'confirming' ? (
          <>
            <span className="text-xs text-yellow-400">Confirm?</span>
            <button
              onClick={restore}
              className="text-xs px-2 py-0.5 rounded bg-yellow-600/30 text-yellow-300 hover:bg-yellow-600/50 transition-colors"
            >
              Yes, restore
            </button>
            <button
              onClick={() => setState('idle')}
              className="text-xs px-2 py-0.5 rounded bg-panel-600 text-gray-400 hover:bg-panel-500 transition-colors"
            >
              Cancel
            </button>
          </>
        ) : state === 'restoring' ? (
          <Loader size={13} className="animate-spin text-brand-400" />
        ) : state === 'done' ? (
          <CheckCircle size={13} className="text-green-400" />
        ) : (
          <button
            onClick={restore}
            className="opacity-0 group-hover:opacity-100 flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-brand-600/30 text-brand-300 hover:bg-brand-600/50 transition-all"
          >
            <RotateCcw size={10} /> Restore
          </button>
        )}
      </div>
    </div>
  );
}

function FileBackups({ file, area, domain, onRestored }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-panel-600 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 bg-panel-700/40 hover:bg-panel-700 transition-colors"
      >
        <div className="flex items-center gap-2">
          {open ? <ChevronDown size={13} className="text-gray-500" /> : <ChevronRight size={13} className="text-gray-500" />}
          <span className="text-sm font-mono text-gray-200">{file.filename}</span>
        </div>
        <span className="text-xs text-gray-500">{file.snapshots.length} snapshot{file.snapshots.length !== 1 ? 's' : ''}</span>
      </button>
      {open && (
        <div className="px-2 py-1 space-y-0.5 bg-panel-800/40">
          {file.snapshots.map(snap => (
            <SnapshotRow
              key={snap.ts}
              snap={snap}
              filename={file.filename}
              area={area}
              domain={domain}
              onRestored={onRestored}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function AreaSection({ area, domain }) {
  const [files,   setFiles]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [open,    setOpen]    = useState(false);
  const [error,   setError]   = useState('');

  const fetch = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const r = await api.get(`/api/container/${domain}/backups/${area.id}`);
      setFiles(r.data.files || []);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Failed to load backups');
    } finally {
      setLoading(false);
    }
  }, [domain, area.id]);

  useEffect(() => {
    if (open && files === null) fetch();
  }, [open, files, fetch]);

  const total = files?.reduce((n, f) => n + f.snapshots.length, 0) ?? 0;

  return (
    <div className="border border-panel-600 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 bg-panel-700/50 hover:bg-panel-700 transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <span>{area.icon}</span>
          <span className="font-medium text-sm text-gray-200">{area.label}</span>
          {files !== null && total > 0 && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-brand-600/25 text-brand-300">
              {total}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {loading && <Loader size={13} className="animate-spin text-gray-500" />}
          {open ? <ChevronDown size={14} className="text-gray-500" /> : <ChevronRight size={14} className="text-gray-500" />}
        </div>
      </button>

      {open && (
        <div className="p-3 space-y-2">
          {error && (
            <p className="flex items-center gap-1.5 text-xs text-red-400">
              <AlertCircle size={12} /> {error}
            </p>
          )}
          {!loading && files !== null && files.length === 0 && (
            <p className="text-xs text-gray-500 text-center py-2">No snapshots yet — changes will appear here automatically.</p>
          )}
          {files?.map(f => (
            <FileBackups
              key={f.filename}
              file={f}
              area={area.id}
              domain={domain}
              onRestored={fetch}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default function ConfigBackupsPanel({ domain }) {
  if (!domain) {
    return (
      <div className="card text-center py-8 text-gray-500">
        <History size={24} className="mx-auto mb-2 opacity-40" />
        Select a domain to view config backups.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="card flex items-center gap-3">
        <ShieldCheck size={20} className="text-brand-400 flex-shrink-0" />
        <div>
          <h3 className="font-semibold text-white text-sm">Config Snapshots — {domain}</h3>
          <p className="text-xs text-gray-400 mt-0.5">
            Up to 3 rolling backups per config file. Restore any version instantly.
          </p>
        </div>
      </div>

      {/* Area sections */}
      <div className="space-y-2">
        {AREAS.map(area => (
          <AreaSection key={area.id} area={area} domain={domain} />
        ))}
      </div>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function _humanAge(ts) {
  const secs = Math.floor(Date.now() / 1000) - ts;
  if (secs < 60)   return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}
