import { useState, useEffect, useCallback } from 'react';
import { HardDrive, History, Plus, Trash2, Download, RefreshCw, AlertTriangle, Globe, Database, FolderOpen, PackageOpen, ArchiveRestore, Upload } from 'lucide-react';
import api from '../utils/api';
import ConfigBackupsPanel from '../components/ConfigBackupsPanel';
import BackupProgressCard from '../components/BackupProgressCard';
import RecoveryCard from '../components/RecoveryCard';
import UploadRecoveryCard from '../components/UploadRecoveryCard';

const BACKUP_TYPES = [
  { id: 'website', label: 'Full Website',   icon: Globe,        desc: 'Web files + database dump' },
  { id: 'files',   label: 'Files Only',     icon: FolderOpen,   desc: 'Web root files only' },
  { id: 'db',      label: 'Database Only',  icon: Database,     desc: 'MariaDB dump only' },
  { id: 'full',    label: 'Complete Domain', icon: PackageOpen, desc: 'Files + DB + all config' },
];

function fmtBytes(b) {
  if (b == null) return '—';
  if (b >= 1073741824) return (b / 1073741824).toFixed(1) + ' GB';
  if (b >= 1048576)    return (b / 1048576).toFixed(1) + ' MB';
  return (b / 1024).toFixed(0) + ' KB';
}
function fmtDate(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString();
}

export default function BackupsPage() {
  const [domains,        setDomains]        = useState([]);
  const [selectedDomain, setSelectedDomain] = useState('');
  const [tab,            setTab]            = useState('config');
  const [backupType,     setBackupType]     = useState('website');

  // Full-site backup state
  const [backups,       setBackups]       = useState([]);
  const [loadingList,   setLoadingList]   = useState(false);
  const [deleteConfirm,  setDeleteConfirm]  = useState(null);
  const [error,          setError]          = useState('');
  const [activeJob,      setActiveJob]      = useState(null);
  const [recoveryFile,   setRecoveryFile]   = useState(null);   // filename string → opens RecoveryCard
  const [showUpload,     setShowUpload]     = useState(false);  // → opens UploadRecoveryCard

  useEffect(() => {
    api.get('/api/domains').then(r => {
      const list = r.data?.domains || r.data || [];
      setDomains(list);
      if (list.length && !selectedDomain) setSelectedDomain(list[0].name || list[0]);
    }).catch(() => {});
  }, []);

  const loadBackups = useCallback(() => {
    if (!selectedDomain) return;
    setLoadingList(true);
    setError('');
    api.get(`/api/container/${selectedDomain}/site-backup/list`)
      .then(r => setBackups(r.data?.backups || []))
      .catch(() => setError('Could not reach container — is it running?'))
      .finally(() => setLoadingList(false));
  }, [selectedDomain]);

  useEffect(() => {
    if (tab === 'fullsite') loadBackups();
  }, [tab, selectedDomain, loadBackups]);

  const handleCreate = async () => {
    setError('');
    try {
      const r = await api.post(`/api/container/${selectedDomain}/site-backup/create`, { type: backupType });
      setActiveJob({ jobId: r.data.job_id, backupType });
    } catch (e) {
      setError(e?.response?.data?.detail || 'Backup creation failed');
    }
  };

  const handleDelete = async (filename) => {
    setError('');
    try {
      await api.delete(`/api/container/${selectedDomain}/site-backup/${filename}`);
      setBackups(prev => prev.filter(b => b.filename !== filename));
      setDeleteConfirm(null);
    } catch {
      setError('Delete failed');
    }
  };

  const handleDownload = async (filename) => {
    const token = localStorage.getItem('access_token') || '';
    try {
      const resp = await fetch(`/api/container/${selectedDomain}/site-backup/download/${filename}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) { setError('Download failed: not authenticated'); return; }
      const blob = await resp.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError('Download failed');
    }
  };

  const handleJobClose = () => {
    setActiveJob(null);
    loadBackups();
  };

  return (
    <div className="space-y-5">
      {activeJob && (
        <BackupProgressCard
          domain={selectedDomain}
          jobId={activeJob.jobId}
          backupType={activeJob.backupType}
          onClose={handleJobClose}
        />
      )}
      {recoveryFile && (
        <RecoveryCard
          domain={selectedDomain}
          filename={recoveryFile}
          onClose={() => { setRecoveryFile(null); loadBackups(); }}
        />
      )}
      {showUpload && (
        <UploadRecoveryCard
          domain={selectedDomain}
          onClose={() => { setShowUpload(false); loadBackups(); }}
        />
      )}
      <div>
        <h1 className="text-[20px] font-bold text-ink-primary">Backups</h1>
        <p className="text-[13px] text-ink-muted mt-0.5">Config snapshots and full-site archives per domain</p>
      </div>

      {/* Domain selector + tabs */}
      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={selectedDomain}
          onChange={e => { setSelectedDomain(e.target.value); setError(''); setMsg(''); }}
          className="input w-56"
        >
          {domains.length === 0 && <option value="">No domains</option>}
          {domains.map(d => {
            const name = d.name || d;
            return <option key={name} value={name}>{name}</option>;
          })}
        </select>

        <div className="flex border border-panel-border rounded-lg overflow-hidden">
          {[
            { id: 'config',   label: 'Config Snapshots', icon: History },
            { id: 'fullsite', label: 'Full Site Backup',  icon: HardDrive },
          ].map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm transition-colors ${
                tab === id
                  ? 'bg-brand/15 text-brand-light'
                  : 'text-ink-muted hover:text-ink-primary hover:bg-panel-elevated'
              }`}
            >
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'config' && <ConfigBackupsPanel domain={selectedDomain} />}

      {tab === 'fullsite' && (
        <div className="space-y-3">
          {/* Backup type selector */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            {BACKUP_TYPES.map(bt => (
              <button
                key={bt.id}
                onClick={() => setBackupType(bt.id)}
                className={`flex flex-col items-start gap-1 p-3 rounded-xl border text-left transition-all ${
                  backupType === bt.id
                    ? 'bg-brand/10 border-brand/30 text-brand'
                    : 'bg-panel-elevated/30 border-panel-subtle text-ink-muted hover:border-brand/20'
                }`}
              >
                <bt.icon size={14} className={backupType === bt.id ? 'text-brand' : ''} />
                <span className="text-[11px] font-semibold">{bt.label}</span>
                <span className="text-[10px] text-ink-faint">{bt.desc}</span>
              </button>
            ))}
          </div>

          {/* Toolbar */}
          <div className="flex items-center justify-between">
            <p className="text-[12px] text-ink-muted">
              Backups stored in container — max 10 kept per domain.
            </p>
            <div className="flex gap-2">
              <button
                onClick={loadBackups}
                disabled={loadingList}
                className="btn-ghost flex items-center gap-1.5 py-1.5 px-3 text-xs"
              >
                <RefreshCw size={13} className={loadingList ? 'animate-spin' : ''} />
                Refresh
              </button>
              <button
                onClick={() => setShowUpload(true)}
                disabled={!selectedDomain}
                className="btn-ghost flex items-center gap-1.5 py-1.5 px-3 text-xs border border-panel-border"
              >
                <Upload size={13} /> Upload Recovery
              </button>
              <button
                onClick={handleCreate}
                disabled={!!activeJob || !selectedDomain}
                className="btn-primary flex items-center gap-1.5 py-1.5 px-3 text-xs min-w-[140px]"
              >
                <Plus size={13} /> Create {BACKUP_TYPES.find(b => b.id === backupType)?.label} Backup
              </button>
            </div>
          </div>

          {error && (
            <div className="flex items-center gap-2 text-bad-light bg-bad/10 border border-bad/20 rounded-lg px-4 py-2.5 text-sm">
              <AlertTriangle size={14} /> {error}
            </div>
          )}

          {/* Delete confirmation modal */}
          {deleteConfirm && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
              <div className="bg-panel-card border border-panel-border rounded-xl p-6 max-w-sm w-full mx-4 space-y-4">
                <div className="flex items-center gap-2 text-bad-light">
                  <AlertTriangle size={18} />
                  <h3 className="font-semibold text-ink-primary">Delete backup?</h3>
                </div>
                <p className="text-[13px] text-ink-secondary">
                  This will permanently delete <span className="font-mono text-ink-primary">{deleteConfirm}</span>. This cannot be undone.
                </p>
                <div className="flex gap-2 justify-end">
                  <button className="btn-ghost text-sm py-1.5 px-4" onClick={() => setDeleteConfirm(null)}>
                    Cancel
                  </button>
                  <button className="btn-danger text-sm py-1.5 px-4" onClick={() => handleDelete(deleteConfirm)}>
                    Delete
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Backup list */}
          <div className="panel overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-panel-border">
                  <th className="tbl-head">Filename</th>
                  <th className="tbl-head">Type</th>
                  <th className="tbl-head">Unique ID</th>
                  <th className="tbl-head">Size</th>
                  <th className="tbl-head">Created</th>
                  <th className="tbl-head text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {loadingList && (
                  <tr><td colSpan={6} className="text-center py-8 text-ink-muted text-sm">Loading…</td></tr>
                )}
                {!loadingList && backups.length === 0 && (
                  <tr>
                    <td colSpan={6} className="text-center py-10 text-ink-muted text-sm">
                      No backups yet for <strong className="text-ink-secondary">{selectedDomain || 'this domain'}</strong>.
                      Click <span className="text-brand-light">Create Backup</span> to make one.
                    </td>
                  </tr>
                )}
                {backups.map(b => (
                  <tr key={b.filename} className="border-b border-panel-border/50 hover:bg-panel-elevated transition-colors">
                    <td className="tbl-cell font-mono text-xs text-ink-secondary">{b.filename}</td>
                    <td className="tbl-cell">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide
                        ${{
                          full:    'bg-purple-500/15 text-purple-300',
                          website: 'bg-blue-500/15 text-blue-300',
                          files:   'bg-teal-500/15 text-teal-300',
                          db:      'bg-amber-500/15 text-amber-300',
                        }[b.backup_type] || 'bg-panel-elevated text-ink-muted'}`}>
                        {b.backup_type || '—'}
                      </span>
                    </td>
                    <td className="tbl-cell">
                      <div className="flex items-center gap-1.5">
                        {b.verified && (
                          <span title="Verified — recorded in panel database" className="text-ok-light flex-shrink-0">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
                          </span>
                        )}
                        <span className="font-mono text-[10px] text-ink-muted">
                          {b.unique_id ? b.unique_id.slice(0, 8) + '…' : <span className="text-ink-faint italic">not recorded</span>}
                        </span>
                      </div>
                    </td>
                    <td className="tbl-cell">{fmtBytes(b.size)}</td>
                    <td className="tbl-cell text-ink-muted">{fmtDate(b.created)}</td>
                    <td className="tbl-cell">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => handleDownload(b.filename)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium text-brand-light bg-brand/10 hover:bg-brand/20 transition-colors"
                          title="Download backup"
                        >
                          <Download size={12} /> Download
                        </button>
                        <button
                          onClick={() => setRecoveryFile(b.filename)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium text-ok-light bg-ok/10 hover:bg-ok/20 transition-colors"
                          title="Restore this backup"
                        >
                          <ArchiveRestore size={12} /> Recover
                        </button>
                        <button
                          onClick={() => setDeleteConfirm(b.filename)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs text-ink-muted hover:text-bad-light hover:bg-bad/10 transition-colors"
                          title="Delete backup"
                        >
                          <Trash2 size={12} /> Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
