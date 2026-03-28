/**
 * FilesPage — Domain file manager.
 *
 * Features:
 *  - Domain selector
 *  - Area tabs: public_html | uploads | private
 *  - Directory listing with click-to-enter navigation
 *  - Breadcrumb path bar + Back button
 *  - File editor (text files ≤ 512 KB) with Save
 *  - New file / New folder creation
 *  - Delete file or directory (with confirmation)
 *  - Refresh
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  FolderOpen, Folder, File, ArrowLeft, RefreshCw, Plus,
  Pencil, Trash2, Save, X, FolderPlus, FileText, ChevronRight,
  AlertTriangle, Loader, HardDrive, Upload, ShieldCheck,
} from 'lucide-react';
import api from '../utils/api';
import { toast } from '../utils/toast';

// ── Helpers ───────────────────────────────────────────────────────────────────
function fmtSize(b) {
  if (b == null || b === '') return '—';
  if (b >= 1073741824) return (b / 1073741824).toFixed(1) + ' GB';
  if (b >= 1048576)    return (b / 1048576).toFixed(1) + ' MB';
  if (b >= 1024)       return (b / 1024).toFixed(0) + ' KB';
  return b + ' B';
}

function fmtDate(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
}

// Detect if a filename is text-editable
const TEXT_EXTS = new Set([
  '.php', '.html', '.htm', '.css', '.js', '.ts', '.jsx', '.tsx',
  '.json', '.xml', '.yaml', '.yml', '.md', '.txt', '.sh', '.env',
  '.htaccess', '.conf', '.ini', '.log', '.svg', '.csv', '.sql',
]);
function isEditable(name) {
  const dot = name.lastIndexOf('.');
  return dot >= 0 && TEXT_EXTS.has(name.slice(dot).toLowerCase());
}

const AREAS = [
  { id: 'public',  label: 'public_html', icon: FolderOpen },
  { id: 'uploads', label: 'uploads',     icon: Folder     },
  { id: 'private', label: 'private',     icon: Folder     },
];

// ── Breadcrumb ────────────────────────────────────────────────────────────────
function Breadcrumb({ path, onNavigate }) {
  const parts = path ? path.split('/').filter(Boolean) : [];
  return (
    <div className="flex items-center gap-1 text-[12px] font-mono overflow-x-auto">
      <button
        onClick={() => onNavigate('')}
        className="text-brand hover:text-brand-light transition-colors flex-shrink-0"
      >
        /
      </button>
      {parts.map((p, i) => (
        <span key={i} className="flex items-center gap-1 flex-shrink-0">
          <ChevronRight size={11} className="text-ink-faint" />
          <button
            onClick={() => onNavigate(parts.slice(0, i + 1).join('/'))}
            className={`hover:text-ink-primary transition-colors ${
              i === parts.length - 1 ? 'text-ink-primary font-semibold' : 'text-ink-muted'
            }`}
          >
            {p}
          </button>
        </span>
      ))}
    </div>
  );
}

// ── File Editor Modal ─────────────────────────────────────────────────────────
function FileEditor({ domain, area, path, onClose, onSaved }) {
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving,  setSaving]  = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get(`/api/container/${domain}/files/read`, {
          params: { path, area },
        });
        setContent(data.content ?? '');
      } catch (e) {
        toast.error(e?.response?.data?.detail || 'Cannot read file');
        onClose();
      } finally {
        setLoading(false);
      }
    })();
  }, [domain, area, path]);  // eslint-disable-line

  const save = async () => {
    setSaving(true);
    try {
      await api.post(`/api/container/${domain}/files/write`, { path, content }, { params: { area } });
      toast.success('Saved');
      onSaved?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const filename = path.split('/').pop();

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col"
      style={{ background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(4px)' }}
    >
      <div className="flex items-center justify-between px-4 py-3 bg-panel-surface border-b border-panel-subtle flex-shrink-0">
        <div className="flex items-center gap-2">
          <FileText size={14} className="text-brand" />
          <span className="text-[13px] font-semibold text-ink-primary font-mono">{filename}</span>
          <span className="text-[11px] text-ink-faint">{path}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={save}
            disabled={saving || loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-ok/15 hover:bg-ok/25 text-ok text-[12px] font-semibold transition-colors disabled:opacity-50"
          >
            {saving ? <Loader size={12} className="animate-spin" /> : <Save size={12} />}
            Save
          </button>
          <button onClick={onClose} className="p-1.5 rounded-lg text-ink-muted hover:text-ink-primary hover:bg-panel-elevated transition-colors">
            <X size={14} />
          </button>
        </div>
      </div>
      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="w-6 h-6 border-2 border-brand border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <textarea
          value={content}
          onChange={e => setContent(e.target.value)}
          className="flex-1 bg-panel-base text-[12px] font-mono text-ink-primary p-4 resize-none focus:outline-none"
          spellCheck={false}
        />
      )}
    </div>
  );
}

// ── New item dialog ───────────────────────────────────────────────────────────
function NewItemDialog({ type, currentPath, onConfirm, onClose }) {
  const [name, setName] = useState('');
  const inputRef = useRef(null);
  useEffect(() => { inputRef.current?.focus(); }, []);

  const submit = () => {
    if (!name.trim()) return;
    onConfirm(currentPath ? `${currentPath}/${name.trim()}` : name.trim());
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-panel-card border border-panel-subtle rounded-2xl shadow-2xl w-full max-w-sm p-5 space-y-4">
        <h3 className="text-[14px] font-semibold text-ink-primary">
          {type === 'folder' ? 'New Folder' : 'New File'}
        </h3>
        <input
          ref={inputRef}
          value={name}
          onChange={e => setName(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submit()}
          placeholder={type === 'folder' ? 'folder-name' : 'filename.php'}
          className="w-full bg-panel-elevated border border-panel-subtle rounded-xl px-3 py-2 text-[13px] font-mono text-ink-primary focus:outline-none focus:border-brand"
        />
        <div className="flex gap-2">
          <button onClick={submit} disabled={!name.trim()}
            className="flex-1 py-2 rounded-xl bg-brand/15 hover:bg-brand/25 text-brand text-[12px] font-semibold transition-colors disabled:opacity-50">
            Create
          </button>
          <button onClick={onClose}
            className="px-4 py-2 rounded-xl bg-panel-elevated text-ink-muted text-[12px] transition-colors hover:text-ink-primary">
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Upload progress item ──────────────────────────────────────────────────────
function UploadItem({ name, status, scan }) {
  return (
    <div className={`flex items-center gap-2.5 px-3 py-2 rounded-lg border text-[11px] ${
      status === 'done'   ? 'bg-ok/8 border-ok/20 text-ok'      :
      status === 'error'  ? 'bg-bad/8 border-bad/20 text-bad-light' :
      status === 'virus'  ? 'bg-bad/15 border-bad/30 text-bad-light' :
      'bg-brand/8 border-brand/20 text-brand'
    }`}>
      {status === 'uploading' && <Loader size={11} className="animate-spin flex-shrink-0" />}
      {status === 'done'      && <ShieldCheck size={11} className="flex-shrink-0" />}
      {status === 'virus'     && <AlertTriangle size={11} className="flex-shrink-0" />}
      {status === 'error'     && <X size={11} className="flex-shrink-0" />}
      <span className="truncate flex-1">{name}</span>
      {status === 'done' && scan && scan !== 'skipped' && (
        <span className="text-[9px] bg-ok/15 px-1.5 py-0.5 rounded-full border border-ok/25 flex-shrink-0">
          {scan === 'clean' ? 'Clean' : scan}
        </span>
      )}
      {status === 'virus' && (
        <span className="text-[9px] bg-bad/20 px-1.5 py-0.5 rounded-full border border-bad/30 flex-shrink-0">Rejected</span>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function FilesPage() {
  const [domains,     setDomains]     = useState([]);
  const [domain,      setDomain]      = useState('');
  const [area,        setArea]        = useState('public');
  const [path,        setPath]        = useState('');
  const [entries,     setEntries]     = useState([]);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState('');

  const [editPath,    setEditPath]    = useState(null);
  const [newDialog,   setNewDialog]   = useState(null);  // 'file' | 'folder' | null
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [dragOver,    setDragOver]    = useState(false);
  const [uploads,     setUploads]     = useState([]);     // {name, status, scan}
  const [showUploadConfirm, setShowUploadConfirm] = useState(null);  // File[] pending

  // Load domains
  useEffect(() => {
    api.get('/api/domains').then(r => {
      const list = r.data?.domains || r.data || [];
      setDomains(list);
      if (list.length) setDomain(list[0].name || list[0]);
    }).catch(() => {});
  }, []);

  const loadFiles = useCallback(async (d = domain, a = area, p = path) => {
    if (!d) return;
    setLoading(true);
    setError('');
    try {
      const { data } = await api.get(`/api/container/${d}/files`, { params: { path: p, area: a } });
      const items = data.entries ?? data.files ?? data ?? [];
      setEntries(Array.isArray(items) ? items : []);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Could not reach container — is it running?');
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, [domain, area, path]);

  useEffect(() => {
    if (domain) loadFiles(domain, area, path);
  }, [domain, area]); // eslint-disable-line

  const navigate = (newPath) => {
    setPath(newPath);
    loadFiles(domain, area, newPath);
  };

  const goBack = () => {
    const parent = path.includes('/') ? path.substring(0, path.lastIndexOf('/')) : '';
    navigate(parent);
  };

  const openDir = (name) => {
    navigate(path ? `${path}/${name}` : name);
  };

  const createItem = async (newPath, type) => {
    try {
      if (type === 'folder') {
        await api.post(`/api/container/${domain}/files/mkdir`, { path: newPath }, { params: { area } });
        toast.success('Folder created');
      } else {
        await api.post(`/api/container/${domain}/files/write`, { path: newPath, content: '' }, { params: { area } });
        toast.success('File created');
      }
      setNewDialog(null);
      await loadFiles(domain, area, path);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Create failed');
    }
  };

  const deleteItem = async (name, isDir) => {
    const fullPath = path ? `${path}/${name}` : name;
    try {
      await api.delete(`/api/container/${domain}/files`, { params: { path: fullPath, area } });
      toast.success(`Deleted ${name}`);
      setDeleteTarget(null);
      await loadFiles(domain, area, path);
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Delete failed');
    }
  };

  const uploadFiles = async (fileList) => {
    setShowUploadConfirm(null);
    const items = Array.from(fileList);
    // Initialize all as 'uploading'
    setUploads(items.map(f => ({ name: f.name, status: 'uploading', scan: null })));

    for (let i = 0; i < items.length; i++) {
      const file = items[i];
      const formData = new FormData();
      formData.append('file', file);
      formData.append('path', path);
      try {
        const { data } = await api.post(
          `/api/container/${domain}/files/upload?area=${area}`,
          formData,
          { headers: { 'Content-Type': 'multipart/form-data' } },
        );
        setUploads(prev => prev.map((u, idx) =>
          idx === i ? { ...u, status: 'done', scan: data.scan } : u
        ));
      } catch (e) {
        const detail = e?.response?.data?.detail || '';
        const isVirus = detail.toLowerCase().includes('malware') || detail.toLowerCase().includes('infected');
        setUploads(prev => prev.map((u, idx) =>
          idx === i ? { ...u, status: isVirus ? 'virus' : 'error' } : u
        ));
        toast.error(`${file.name}: ${detail || 'Upload failed'}`);
      }
    }
    await loadFiles(domain, area, path);
    // Clear upload list after 5 s
    setTimeout(() => setUploads([]), 5000);
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    if (!domain) return;
    const files = Array.from(e.dataTransfer.files);
    if (files.length) setShowUploadConfirm(files);
  };

  const dirs  = entries.filter(e => e.type === 'dir'  || e.is_dir);
  const files = entries.filter(e => e.type === 'file' || e.is_file || (!e.is_dir && e.type !== 'dir'));

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-brand/15 flex items-center justify-center">
            <HardDrive size={18} className="text-brand" />
          </div>
          <div>
            <h1 className="text-[17px] font-bold text-ink-primary">File Manager</h1>
            <p className="text-[11px] text-ink-muted">Browse and edit domain files</p>
          </div>
        </div>
      </div>

      {/* Domain + area selectors */}
      <div className="flex flex-wrap gap-3 items-center">
        {/* Domain picker */}
        <select
          value={domain}
          onChange={e => { setDomain(e.target.value); setPath(''); }}
          className="bg-panel-card border border-panel-subtle rounded-xl px-3 py-2 text-[13px] text-ink-primary focus:outline-none focus:border-brand"
        >
          {domains.length === 0 && <option value="">No domains</option>}
          {domains.map(d => (
            <option key={d.id ?? d} value={d.name ?? d}>{d.name ?? d}</option>
          ))}
        </select>

        {/* Area tabs */}
        <div className="flex gap-1 bg-panel-elevated/40 rounded-xl p-1 border border-panel-subtle">
          {AREAS.map(a => (
            <button
              key={a.id}
              onClick={() => { setArea(a.id); setPath(''); loadFiles(domain, a.id, ''); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-medium transition-colors ${
                area === a.id
                  ? 'bg-panel-card text-ink-primary shadow-sm border border-panel-subtle'
                  : 'text-ink-muted hover:text-ink-secondary'
              }`}
            >
              <a.icon size={12} />
              {a.label}
            </button>
          ))}
        </div>

        <div className="ml-auto flex gap-2">
          <button
            onClick={() => setNewDialog('folder')}
            disabled={!domain}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-panel-elevated border border-panel-subtle text-[12px] text-ink-muted hover:text-ink-primary hover:border-brand/40 transition-colors disabled:opacity-40"
          >
            <FolderPlus size={13} /> New Folder
          </button>
          <button
            onClick={() => setNewDialog('file')}
            disabled={!domain}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-panel-elevated border border-panel-subtle text-[12px] text-ink-muted hover:text-ink-primary hover:border-brand/40 transition-colors disabled:opacity-40"
          >
            <Plus size={13} /> New File
          </button>
          <button
            onClick={() => loadFiles(domain, area, path)}
            disabled={loading}
            className="p-2 rounded-xl text-ink-muted hover:text-ink-primary hover:bg-panel-elevated transition-colors"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Path bar */}
      {domain && (
        <div className="flex items-center gap-2 bg-panel-card border border-panel-subtle rounded-xl px-3 py-2">
          <button
            onClick={goBack}
            disabled={!path}
            className="p-1 rounded text-ink-muted hover:text-ink-primary transition-colors disabled:opacity-30"
            title="Go up"
          >
            <ArrowLeft size={14} />
          </button>
          <Breadcrumb path={path} onNavigate={navigate} />
        </div>
      )}

      {/* Upload progress list */}
      {uploads.length > 0 && (
        <div className="space-y-1.5">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-ink-faint">Upload Progress</p>
          {uploads.map((u, i) => <UploadItem key={i} {...u} />)}
        </div>
      )}

      {/* Upload confirmation dialog */}
      {showUploadConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(4px)' }}
        >
          <div className="bg-panel-card border border-panel-subtle rounded-2xl shadow-2xl w-full max-w-sm p-5 space-y-4">
            <div className="flex items-center gap-2">
              <Upload size={15} className="text-brand" />
              <h3 className="text-[14px] font-semibold text-ink-primary">Upload Files?</h3>
            </div>
            <p className="text-[12px] text-ink-muted">
              {showUploadConfirm.length} file{showUploadConfirm.length !== 1 ? 's' : ''} will be scanned for malware then
              uploaded to <span className="font-mono text-ink-primary">/{path || ''}</span>.
              Ownership will be set to <span className="font-mono text-ink-secondary">www-data</span>.
            </p>
            <ul className="max-h-32 overflow-y-auto space-y-0.5">
              {Array.from(showUploadConfirm).map((f, i) => (
                <li key={i} className="text-[11px] font-mono text-ink-secondary truncate">• {f.name}</li>
              ))}
            </ul>
            <div className="flex gap-2">
              <button
                onClick={() => uploadFiles(showUploadConfirm)}
                className="flex-1 py-2 rounded-xl bg-brand/15 hover:bg-brand/25 text-brand text-[12px] font-semibold transition-colors"
              >
                <ShieldCheck size={12} className="inline mr-1" />Scan &amp; Upload
              </button>
              <button
                onClick={() => setShowUploadConfirm(null)}
                className="px-4 py-2 rounded-xl bg-panel-elevated text-ink-muted text-[12px] transition-colors hover:text-ink-primary"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* File listing */}
      <div
        className={`relative bg-panel-card border rounded-2xl overflow-hidden transition-colors ${
          dragOver ? 'border-brand/60 bg-brand/5' : 'border-panel-subtle'
        }`}
        onDrop={onDrop}
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget)) setDragOver(false); }}
      >
        {/* Drag overlay */}
        {dragOver && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 pointer-events-none">
            <div className="w-12 h-12 rounded-2xl bg-brand/20 flex items-center justify-center">
              <Upload size={22} className="text-brand" />
            </div>
            <p className="text-[13px] font-semibold text-brand">Drop files to upload</p>
            <p className="text-[11px] text-ink-muted">Files will be virus-scanned before transfer</p>
          </div>
        )}
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-6 h-6 border-2 border-brand border-t-transparent rounded-full animate-spin" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center py-12 gap-2 text-ink-muted">
            <AlertTriangle size={22} className="text-warn" />
            <span className="text-[13px]">{error}</span>
          </div>
        ) : !domain ? (
          <div className="flex flex-col items-center py-12 gap-2 text-ink-muted">
            <FolderOpen size={22} />
            <span className="text-[13px]">Select a domain to browse files</span>
          </div>
        ) : entries.length === 0 ? (
          <div className="flex flex-col items-center py-12 gap-2 text-ink-muted">
            <Folder size={22} />
            <span className="text-[13px]">Empty directory</span>
          </div>
        ) : (
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-panel-subtle bg-panel-elevated/40">
                <th className="text-left px-4 py-2.5 text-[10px] font-semibold uppercase tracking-wide text-ink-faint">Name</th>
                <th className="text-left px-3 py-2.5 text-[10px] font-semibold uppercase tracking-wide text-ink-faint hidden sm:table-cell">Size</th>
                <th className="text-left px-3 py-2.5 text-[10px] font-semibold uppercase tracking-wide text-ink-faint hidden md:table-cell">Modified</th>
                <th className="px-3 py-2.5 w-16" />
              </tr>
            </thead>
            <tbody className="divide-y divide-panel-subtle/40">
              {/* Directories first */}
              {dirs.map((entry, i) => (
                <tr
                  key={entry.name}
                  className="hover:bg-panel-elevated/30 cursor-pointer transition-colors"
                  onClick={() => openDir(entry.name)}
                >
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <Folder size={14} className="text-warn flex-shrink-0" />
                      <span className="text-ink-primary font-medium">{entry.name}/</span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-ink-faint hidden sm:table-cell">—</td>
                  <td className="px-3 py-2.5 text-ink-faint hidden md:table-cell">{fmtDate(entry.modified ?? entry.mtime)}</td>
                  <td className="px-3 py-2.5">
                    <button
                      onClick={e => { e.stopPropagation(); setDeleteTarget({ name: entry.name, isDir: true }); }}
                      className="p-1 rounded text-ink-faint hover:text-bad-light hover:bg-bad/10 transition-colors"
                      title="Delete"
                    >
                      <Trash2 size={12} />
                    </button>
                  </td>
                </tr>
              ))}
              {/* Files */}
              {files.map((entry) => (
                <tr key={entry.name} className="hover:bg-panel-elevated/30 transition-colors">
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <File size={14} className="text-brand flex-shrink-0" />
                      <span className="text-ink-secondary">{entry.name}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-ink-faint hidden sm:table-cell">{fmtSize(entry.size)}</td>
                  <td className="px-3 py-2.5 text-ink-faint hidden md:table-cell">{fmtDate(entry.modified ?? entry.mtime)}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-1">
                      {isEditable(entry.name) && (
                        <button
                          onClick={() => setEditPath(path ? `${path}/${entry.name}` : entry.name)}
                          className="p-1 rounded text-ink-faint hover:text-brand hover:bg-brand/10 transition-colors"
                          title="Edit"
                        >
                          <Pencil size={12} />
                        </button>
                      )}
                      <button
                        onClick={() => setDeleteTarget({ name: entry.name, isDir: false })}
                        className="p-1 rounded text-ink-faint hover:text-bad-light hover:bg-bad/10 transition-colors"
                        title="Delete"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>  {/* end file listing */}

      {/* File editor (fullscreen modal) */}
      {editPath && (
        <FileEditor
          domain={domain}
          area={area}
          path={editPath}
          onClose={() => setEditPath(null)}
          onSaved={() => loadFiles(domain, area, path)}
        />
      )}

      {/* New file/folder dialog */}
      {newDialog && (
        <NewItemDialog
          type={newDialog}
          currentPath={path}
          onConfirm={(newPath) => createItem(newPath, newDialog)}
          onClose={() => setNewDialog(null)}
        />
      )}

      {/* Delete confirm */}
      {deleteTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}
        >
          <div className="bg-panel-card border border-bad/30 rounded-2xl shadow-2xl w-full max-w-sm p-5 space-y-4">
            <div className="flex items-center gap-2">
              <AlertTriangle size={16} className="text-bad-light" />
              <h3 className="text-[14px] font-semibold text-ink-primary">Delete {deleteTarget.isDir ? 'Folder' : 'File'}?</h3>
            </div>
            <p className="text-[12px] text-ink-muted">
              <span className="font-mono text-bad-light">{deleteTarget.name}</span>
              {deleteTarget.isDir && ' and all its contents'} will be permanently deleted.
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => deleteItem(deleteTarget.name, deleteTarget.isDir)}
                className="flex-1 py-2 rounded-xl bg-bad/15 hover:bg-bad/25 text-bad-light text-[12px] font-semibold transition-colors"
              >
                Delete
              </button>
              <button
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 rounded-xl bg-panel-elevated text-ink-muted text-[12px] transition-colors hover:text-ink-primary"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
