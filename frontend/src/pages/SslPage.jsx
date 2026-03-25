import { useState, useEffect } from 'react';
import { ShieldCheck, Plus, Download, Upload, Globe, AlertTriangle, CheckCircle } from 'lucide-react';
import api from '../utils/api';

export default function SslPage() {
  const [domains,   setDomains]   = useState([]);
  const [domain,    setDomain]    = useState('');
  const [uploading, setUploading] = useState(false);
  const [cert,      setCert]      = useState('');
  const [key,       setKey]       = useState('');
  const [msg,       setMsg]       = useState('');
  const [error,     setError]     = useState('');

  useEffect(() => {
    api.get('/api/domains').then(r => {
      const list = r.data?.domains || r.data || [];
      setDomains(list);
      if (list.length) setDomain(list[0].name || list[0]);
    }).catch(() => {});
  }, []);

  const handleUpload = async () => {
    if (!domain || (!cert && !key)) return;
    setUploading(true); setError(''); setMsg('');
    try {
      await api.post(`/api/container/${domain}/secure/ssl`, { cert, key });
      setMsg('Certificate uploaded successfully.');
      setCert(''); setKey('');
    } catch (e) {
      setError(e?.response?.data?.detail || 'Upload failed — is the domain container running?');
    } finally { setUploading(false); }
  };

  const handleDownload = (filetype) => {
    const token = localStorage.getItem('access_token') || '';
    window.open(`/api/container/${domain}/ssl/download/${filetype}`, '_blank');
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-[20px] font-bold text-ink-primary flex items-center gap-2">
          <ShieldCheck size={20} className="text-brand" /> SSL / TLS
        </h1>
        <p className="text-[13px] text-ink-muted mt-0.5">
          Certificates are issued via Traefik + Let's Encrypt automatically. Manual upload and download also supported.
        </p>
      </div>

      {/* Info banner */}
      <div className="flex items-start gap-2 bg-brand/8 border border-brand/20 rounded-xl px-4 py-3 text-[13px] text-ink-secondary">
        <CheckCircle size={14} className="text-brand mt-0.5 flex-shrink-0" />
        <span>
          Let's Encrypt certificates are provisioned automatically by Traefik when a domain is pointed to this server.
          Use the upload section below for custom/wildcard certificates.
        </span>
      </div>

      {/* Domain selector */}
      <div className="panel p-4 space-y-4">
        <div className="flex items-center gap-3">
          <Globe size={15} className="text-ink-muted" />
          <h2 className="text-[13px] font-semibold text-ink-primary">Domain</h2>
          <select
            value={domain}
            onChange={e => { setDomain(e.target.value); setMsg(''); setError(''); }}
            className="input w-56 ml-auto"
          >
            {domains.length === 0 && <option value="">No domains</option>}
            {domains.map(d => {
              const name = d.name || d;
              return <option key={name} value={name}>{name}</option>;
            })}
          </select>
        </div>

        {/* Download buttons */}
        <div>
          <p className="text-[11px] text-ink-muted uppercase tracking-wide font-semibold mb-2">Download Certificate Files</p>
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={() => handleDownload('cert')}
              disabled={!domain}
              className="btn-ghost flex items-center gap-1.5 text-xs py-1.5 px-3"
            >
              <Download size={12} /> Download Certificate (.crt)
            </button>
            <button
              onClick={() => handleDownload('key')}
              disabled={!domain}
              className="btn-ghost flex items-center gap-1.5 text-xs py-1.5 px-3"
            >
              <Download size={12} /> Download Private Key (.key)
            </button>
          </div>
          <p className="text-[11px] text-ink-muted mt-1.5">
            Keys are stored securely inside each domain's container at <code className="text-ink-secondary">/var/config/ssl/</code> — never on the main system.
          </p>
        </div>

        <hr className="border-panel-border" />

        {/* Upload section */}
        <div>
          <p className="text-[11px] text-ink-muted uppercase tracking-wide font-semibold mb-3 flex items-center gap-1.5">
            <Upload size={12} /> Upload Custom Certificate
          </p>
          {error && (
            <div className="flex items-center gap-2 text-bad-light bg-bad/10 border border-bad/20 rounded-lg px-3 py-2 text-xs mb-3">
              <AlertTriangle size={12} /> {error}
            </div>
          )}
          {msg && (
            <div className="text-ok-light bg-ok/10 border border-ok/20 rounded-lg px-3 py-2 text-xs mb-3">
              {msg}
            </div>
          )}
          <div className="space-y-3">
            <div>
              <label className="block text-[11px] text-ink-muted mb-1">Certificate (PEM)</label>
              <textarea
                value={cert}
                onChange={e => setCert(e.target.value)}
                className="input font-mono text-xs"
                rows={4}
                placeholder="-----BEGIN CERTIFICATE-----&#10;..."
              />
            </div>
            <div>
              <label className="block text-[11px] text-ink-muted mb-1">Private Key (PEM)</label>
              <textarea
                value={key}
                onChange={e => setKey(e.target.value)}
                className="input font-mono text-xs"
                rows={4}
                placeholder="-----BEGIN PRIVATE KEY-----&#10;..."
              />
            </div>
            <button
              onClick={handleUpload}
              disabled={uploading || !domain || (!cert && !key)}
              className="btn-primary flex items-center gap-1.5 text-sm"
            >
              <Upload size={13} />
              {uploading ? 'Uploading…' : 'Upload Certificate'}
            </button>
          </div>
        </div>
      </div>

      {/* Certificate table — populated when Let's Encrypt certs are tracked */}
      <div className="panel overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-panel-border">
              {['Domain', 'Issuer', 'Expires', 'Auto-renew', 'Status', 'Actions'].map(h => (
                <th key={h} className="tbl-head">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td colSpan={6} className="text-center py-10 text-ink-muted text-sm">
                Certificate tracking coming soon — Let's Encrypt certs auto-renew via Traefik.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
