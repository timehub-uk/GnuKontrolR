import { useState, useRef } from 'react';
import { Shield, FolderOpen, FileText, ChevronRight, Eye, Lock, AlertCircle, Loader } from 'lucide-react';
import api from '../utils/api';

const TEXT_EXTS = new Set([
  '.php','.html','.htm','.js','.jsx','.ts','.tsx',
  '.css','.scss','.json','.xml','.yaml','.yml','.toml',
  '.env','.ini','.conf','.txt','.md','.sh','.py',
  '.rb','.java','.go','.rs','.sql','.log','.htaccess',
]);

export default function AdminContentPage() {
  const [pin, setPin]             = useState('');
  const [token, setToken]         = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [pinErr, setPinErr]       = useState('');

  const [domains, setDomains]   = useState([]);
  const [domain, setDomain]     = useState('');
  const [path, setPath]         = useState('');
  const [breadcrumbs, setBreadcrumbs] = useState([]);
  const [entries, setEntries]   = useState([]);
  const [fileContent, setFileContent] = useState(null);
  const [browsing, setBrowsing] = useState(false);
  const [error, setError]       = useState('');

  const pinInputRef = useRef(null);

  async function verifyPin() {
    if (pin.length !== 6) { setPinErr('PIN must be 6 digits'); return; }
    setVerifying(true);
    setPinErr('');
    try {
      const r = await api.post('/api/admin/content/pin/verify', { pin });
      setToken(r.data.content_token);
      // Load domain list
      const dr = await api.get('/api/admin/content/domains', {
        headers: { 'X-Content-Token': r.data.content_token }
      });
      setDomains(dr.data.domains || []);
    } catch (e) {
      setPinErr(e.response?.data?.detail || 'PIN verification failed');
    } finally {
      setVerifying(false);
    }
  }

  async function browse(d, p = '', crumbs = []) {
    setBrowsing(true);
    setFileContent(null);
    setError('');
    try {
      const r = await api.get(`/api/admin/content/domains/${d}/files`, {
        params: { path: p },
        headers: { 'X-Content-Token': token },
      });
      setDomain(d);
      setPath(p);
      setBreadcrumbs(crumbs);
      setEntries(r.data.entries || []);
    } catch (e) {
      setError(e.response?.data?.detail || 'Browse failed');
    } finally {
      setBrowsing(false);
    }
  }

  async function readFile(name) {
    const filePath = path ? `${path}/${name}` : name;
    setBrowsing(true);
    setError('');
    try {
      const r = await api.get(`/api/admin/content/domains/${domain}/read`, {
        params: { path: filePath },
        headers: { 'X-Content-Token': token },
      });
      setFileContent(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || 'Read failed');
    } finally {
      setBrowsing(false);
    }
  }

  function navigateIn(entry) {
    if (entry.type === 'dir') {
      const newPath = path ? `${path}/${entry.name}` : entry.name;
      const newCrumbs = [...breadcrumbs, { label: entry.name, path: newPath }];
      browse(domain, newPath, newCrumbs);
    } else if (entry.readable) {
      readFile(entry.name);
    }
  }

  function navigateCrumb(crumb) {
    const idx = breadcrumbs.indexOf(crumb);
    const newCrumbs = breadcrumbs.slice(0, idx + 1);
    browse(domain, crumb.path, newCrumbs);
  }

  function formatSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }

  // ── PIN entry screen ────────────────────────────────────────────────────
  if (!token) {
    return (
      <div className="space-y-6 max-w-md mx-auto mt-12">
        <div className="text-center space-y-2">
          <div className="inline-flex p-4 bg-panel-700 rounded-2xl mb-2">
            <Shield size={32} className="text-brand-400" />
          </div>
          <h1 className="text-xl font-bold text-white">Admin Content Viewer</h1>
          <p className="text-sm text-gray-400">
            Enter your 6-digit support PIN to access domain file contents.
          </p>
        </div>

        <div className="card space-y-4">
          <label className="block text-sm text-gray-400">Support PIN</label>
          <input
            ref={pinInputRef}
            type="password"
            inputMode="numeric"
            pattern="\d{6}"
            maxLength={6}
            className="input text-center text-2xl tracking-widest font-mono"
            placeholder="••••••"
            value={pin}
            onChange={e => setPin(e.target.value.replace(/\D/g, '').slice(0, 6))}
            onKeyDown={e => e.key === 'Enter' && verifyPin()}
          />
          {pinErr && (
            <p className="text-red-400 text-sm flex items-center gap-1">
              <AlertCircle size={14} /> {pinErr}
            </p>
          )}
          <button
            className="btn-primary w-full flex items-center justify-center gap-2"
            onClick={verifyPin}
            disabled={verifying || pin.length !== 6}
          >
            {verifying ? <Loader size={16} className="animate-spin" /> : <Lock size={16} />}
            Verify PIN
          </button>
          <p className="text-xs text-gray-500 text-center">
            Set your PIN in Settings → Security.
          </p>
        </div>
      </div>
    );
  }

  // ── Authenticated ────────────────────────────────────────────────────────
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Shield size={20} className="text-brand-400" /> Domain Content Viewer
        </h1>
        <button
          className="btn-ghost text-xs text-red-400"
          onClick={() => { setToken(null); setDomain(''); setEntries([]); setFileContent(null); }}
        >
          Lock
        </button>
      </div>

      {/* Domain picker */}
      {!domain && (
        <div className="card space-y-3">
          <p className="text-sm text-gray-400">Select a domain to browse:</p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {domains.map(d => (
              <button
                key={d}
                className="card text-left hover:border-brand-500 cursor-pointer text-sm font-medium text-white"
                onClick={() => browse(d, '', [])}
              >
                <FolderOpen size={14} className="inline mr-2 text-brand-400" />
                {d}
              </button>
            ))}
          </div>
          {domains.length === 0 && (
            <p className="text-sm text-gray-500">No domain directories found in {'/var/webpanel/sites'}.</p>
          )}
        </div>
      )}

      {/* Breadcrumb + back */}
      {domain && !fileContent && (
        <>
          <div className="flex items-center gap-1 text-sm flex-wrap">
            <button
              className="text-brand-400 hover:text-brand-300"
              onClick={() => { setDomain(''); setPath(''); setEntries([]); }}
            >
              Domains
            </button>
            <ChevronRight size={14} className="text-gray-500" />
            <button
              className="text-brand-400 hover:text-brand-300"
              onClick={() => browse(domain, '', [])}
            >
              {domain}
            </button>
            {breadcrumbs.map(crumb => (
              <>
                <ChevronRight size={14} className="text-gray-500" />
                <button
                  key={crumb.path}
                  className="text-brand-400 hover:text-brand-300"
                  onClick={() => navigateCrumb(crumb)}
                >
                  {crumb.label}
                </button>
              </>
            ))}
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          <div className="card p-0 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-panel-700 text-gray-400 text-xs uppercase">
                <tr>
                  {['Name', 'Type', 'Size', 'Modified'].map(h =>
                    <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
                  )}
                </tr>
              </thead>
              <tbody>
                {browsing && (
                  <tr><td colSpan={4} className="text-center py-6 text-gray-500">
                    <Loader size={16} className="animate-spin inline mr-2" />Loading…
                  </td></tr>
                )}
                {!browsing && entries.length === 0 && (
                  <tr><td colSpan={4} className="text-center py-6 text-gray-500">Empty directory</td></tr>
                )}
                {entries.map(e => (
                  <tr
                    key={e.name}
                    className={`border-t border-panel-700 hover:bg-panel-700/50 ${
                      (e.type === 'dir' || e.readable) ? 'cursor-pointer' : ''
                    }`}
                    onClick={() => navigateIn(e)}
                  >
                    <td className="px-4 py-2.5 flex items-center gap-2">
                      {e.type === 'dir'
                        ? <FolderOpen size={14} className="text-brand-400" />
                        : <FileText size={14} className={e.readable ? 'text-gray-400' : 'text-gray-600'} />
                      }
                      <span className={e.readable || e.type === 'dir' ? 'text-white' : 'text-gray-500'}>
                        {e.name}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-gray-400 text-xs">{e.ext || (e.type === 'dir' ? 'folder' : '—')}</td>
                    <td className="px-4 py-2.5 text-gray-400 text-xs">{e.type === 'dir' ? '—' : formatSize(e.size)}</td>
                    <td className="px-4 py-2.5 text-gray-500 text-xs">{new Date(e.modified).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* File viewer */}
      {fileContent && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm">
              <button
                className="text-brand-400 hover:text-brand-300"
                onClick={() => setFileContent(null)}
              >
                ← Back
              </button>
              <span className="text-gray-500">/</span>
              <span className="text-white font-mono">{fileContent.name}</span>
              <span className="text-xs text-gray-500">({formatSize(fileContent.size)})</span>
            </div>
            <Eye size={14} className="text-gray-500" />
          </div>
          <div className="card p-0 overflow-hidden">
            <pre className="p-4 text-xs text-gray-300 font-mono overflow-auto max-h-[70vh] leading-relaxed whitespace-pre-wrap break-words">
              {fileContent.content}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
