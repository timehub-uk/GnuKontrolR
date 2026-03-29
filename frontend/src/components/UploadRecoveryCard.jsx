/**
 * UploadRecoveryCard
 * Wizard: drag-drop / select file → upload + scan → manifest review → section select → recovery progress → done
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Upload, CheckCircle, AlertCircle, Loader, ArrowLeft,
  X, ShieldCheck, Database, FolderOpen, Globe, Lock, Settings,
  ShieldAlert, FileArchive, ArrowRight,
} from 'lucide-react';
import api from '../utils/api';

const SECTION_ICONS = {
  files:    Globe,
  uploads:  FolderOpen,
  private:  Lock,
  config:   Settings,
  database: Database,
};

function parseManifest(xml) {
  const parser = new DOMParser();
  const doc    = parser.parseFromString(xml, 'text/xml');
  return Array.from(doc.querySelectorAll('section')).map(n => ({
    id:       n.getAttribute('id'),
    label:    n.getAttribute('label') || n.getAttribute('id'),
    included: n.getAttribute('included') === 'true',
    tar_path: n.getAttribute('tar_path') || '',
    size:     parseInt(n.getAttribute('size') || '0', 10),
  }));
}

function fmtBytes(b) {
  if (!b) return '';
  if (b >= 1048576) return ` (${(b / 1048576).toFixed(1)} MB)`;
  return ` (${(b / 1024).toFixed(0)} KB)`;
}

const STEPS = ['Upload', 'Scan', 'Review', 'Restore', 'Complete'];

export default function UploadRecoveryCard({ domain, onClose }) {
  // phase: 'drop' | 'uploading' | 'scan' | 'review' | 'running' | 'done' | 'error'
  const [phase,      setPhase]      = useState('drop');
  const [dragOver,   setDragOver]   = useState(false);
  const [uploadPct,  setUploadPct]  = useState(0);
  const [scanResult, setScanResult] = useState(null);  // response from upload endpoint
  const [sections,   setSections]   = useState([]);
  const [selected,   setSelected]   = useState({});
  const [errMsg,     setErrMsg]     = useState('');

  // Recovery job
  const [job,      setJob]      = useState(null);
  const timerRef               = useRef(null);
  const fileInputRef           = useRef(null);

  const stepIndex = { drop: 0, uploading: 0, scan: 1, review: 2, running: 3, done: 4, error: -1 }[phase] ?? 0;

  const handleFile = useCallback(async (file) => {
    if (!file || !file.name.endsWith('.tar.gz')) {
      setErrMsg('Please select a .tar.gz backup archive.');
      return;
    }
    setErrMsg('');
    setPhase('uploading');
    setUploadPct(0);

    const token = localStorage.getItem('access_token') || '';
    const xhr   = new XMLHttpRequest();
    xhr.open('POST', `/api/container/${domain}/site-backup/upload`);
    xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.setRequestHeader('X-Filename', file.name);
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');

    xhr.upload.onprogress = e => {
      if (e.lengthComputable) setUploadPct(Math.round(e.loaded / e.total * 90));
    };

    xhr.onload = () => {
      setUploadPct(100);
      setPhase('scan');
      try {
        const data = JSON.parse(xhr.responseText);
        if (!data.ok) { setErrMsg(data.error || 'Upload rejected'); setPhase('error'); return; }
        setScanResult(data);
        if (data.xml) {
          const secs = parseManifest(data.xml);
          setSections(secs);
          const init = {};
          secs.filter(s => s.included).forEach(s => { init[s.id] = true; });
          setSelected(init);
        }
        setPhase('review');
      } catch {
        setErrMsg('Invalid response from server'); setPhase('error');
      }
    };
    xhr.onerror = () => { setErrMsg('Upload failed — check connection'); setPhase('error'); };
    xhr.send(file);
  }, [domain]);

  const onDrop = useCallback(e => {
    e.preventDefault(); setDragOver(false);
    handleFile(e.dataTransfer?.files?.[0]);
  }, [handleFile]);

  // Poll recovery job
  useEffect(() => {
    if (phase !== 'running' || !job?.jobId) return;
    async function poll() {
      try {
        const r = await api.get(`/api/container/${domain}/site-backup/recovery-status/${job.jobId}`);
        setJob(prev => ({ ...prev, ...r.data }));
        if (r.data.status === 'done')  { clearInterval(timerRef.current); setPhase('done'); }
        if (r.data.status === 'error') { clearInterval(timerRef.current); setPhase('error'); setErrMsg(r.data.error || 'Recovery failed'); }
      } catch (e) {
        clearInterval(timerRef.current);
        setErrMsg(e?.response?.data?.detail || 'Lost contact with container');
        setPhase('error');
      }
    }
    poll();
    timerRef.current = setInterval(poll, 1500);
    return () => clearInterval(timerRef.current);
  }, [phase, job?.jobId, domain]);

  async function startRecovery() {
    const sectionIds = Object.entries(selected).filter(([, v]) => v).map(([k]) => k);
    if (!sectionIds.length || !scanResult?.filename) return;
    try {
      const r = await api.post(`/api/container/${domain}/site-backup/${scanResult.filename}/recover`, { sections: sectionIds });
      setJob({ jobId: r.data.job_id, status: 'running', pct: 0, messages: [], current: 'Starting…' });
      setPhase('running');
    } catch (e) {
      setErrMsg(e?.response?.data?.detail || 'Failed to start recovery');
      setPhase('error');
    }
  }

  const pct  = job?.pct ?? 0;
  const msgs = job?.messages ?? [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg bg-panel-800 border border-panel-600 rounded-2xl shadow-2xl overflow-hidden">

        {/* Header */}
        <div className={`px-6 py-4 flex items-center justify-between border-b border-panel-700
          ${phase === 'done' ? 'bg-green-900/20' : phase === 'error' ? 'bg-red-900/20' : 'bg-brand-900/20'}`}>
          <div className="flex items-center gap-3">
            <Upload size={18} className={phase === 'done' ? 'text-green-400' : phase === 'error' ? 'text-red-400' : 'text-brand-400'} />
            <div>
              <h2 className="font-semibold text-white text-sm">Upload &amp; Restore Backup</h2>
              <p className="text-xs text-gray-400">{domain}</p>
            </div>
          </div>
          {(phase === 'drop' || phase === 'done' || phase === 'error') && (
            <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors"><X size={18} /></button>
          )}
        </div>

        {/* Step bar */}
        <div className="flex border-b border-panel-700">
          {STEPS.map((s, i) => (
            <div key={s} className={`flex-1 py-2 text-center text-[11px] font-medium transition-colors
              ${i < stepIndex ? 'text-green-400' : i === stepIndex ? 'text-brand-300 bg-brand-900/10' : 'text-gray-600'}`}>
              {i < stepIndex ? <CheckCircle size={11} className="inline mr-1" /> : null}{s}
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4 min-h-[200px]">

          {/* Drop zone */}
          {(phase === 'drop') && (
            <div
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`flex flex-col items-center justify-center gap-3 border-2 border-dashed rounded-xl py-12 cursor-pointer transition-all
                ${dragOver ? 'border-brand-500 bg-brand-900/20' : 'border-panel-600 bg-panel-700/20 hover:border-brand-600 hover:bg-brand-900/10'}`}
            >
              <FileArchive size={32} className={dragOver ? 'text-brand-400' : 'text-gray-500'} />
              <div className="text-center">
                <p className="text-sm text-gray-300">Drag &amp; drop a <span className="font-mono text-brand-300">.tar.gz</span> backup archive</p>
                <p className="text-xs text-gray-500 mt-1">or click to select file</p>
              </div>
              <input ref={fileInputRef} type="file" accept=".tar.gz" className="hidden"
                onChange={e => handleFile(e.target.files?.[0])} />
            </div>
          )}

          {errMsg && (phase === 'drop' || phase === 'error') && (
            <p className="text-xs text-red-400 flex items-center gap-1.5">
              <AlertCircle size={13} /> {errMsg}
            </p>
          )}

          {/* Uploading */}
          {phase === 'uploading' && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-gray-300 text-sm">
                <Loader size={14} className="animate-spin text-brand-400" />
                Uploading archive…
              </div>
              <div className="h-2.5 bg-panel-700 rounded-full overflow-hidden">
                <div className="h-full bg-brand-500 rounded-full transition-all duration-300" style={{ width: `${uploadPct}%` }} />
              </div>
              <p className="text-xs text-gray-500 text-right">{uploadPct}%</p>
            </div>
          )}

          {/* Scan result (shown briefly before review) */}
          {phase === 'scan' && (
            <div className="flex items-center gap-3 py-4 text-gray-300 text-sm">
              <Loader size={16} className="animate-spin text-brand-400" />
              Running security checks…
            </div>
          )}

          {/* Review */}
          {phase === 'review' && scanResult && (
            <div className="space-y-4">
              {/* Security summary */}
              <div className="flex items-center gap-3 bg-green-900/20 border border-green-800/40 rounded-lg px-4 py-2.5">
                <ShieldAlert size={16} className="text-green-400 flex-shrink-0" />
                <div className="text-xs">
                  <p className="text-green-300 font-medium">{scanResult.scan}</p>
                  <p className="text-gray-400 font-mono mt-0.5">{scanResult.filename} — {(scanResult.size / 1048576).toFixed(1)} MB</p>
                </div>
              </div>

              {sections.length > 0 ? (
                <>
                  <p className="text-xs text-gray-400">Select sections to restore:</p>
                  <div className="space-y-2">
                    {sections.map(sec => {
                      const Icon = SECTION_ICONS[sec.id] || FolderOpen;
                      return (
                        <label key={sec.id}
                          className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-all
                            ${!sec.included ? 'opacity-40 cursor-not-allowed border-panel-600 bg-panel-700/30' :
                              selected[sec.id]
                                ? 'border-brand-500/50 bg-brand-900/20'
                                : 'border-panel-600 bg-panel-700/30 hover:border-panel-500'
                            }`}
                        >
                          <input type="checkbox" checked={!!selected[sec.id]} disabled={!sec.included}
                            onChange={e => setSelected(prev => ({ ...prev, [sec.id]: e.target.checked }))}
                            className="accent-brand-500" />
                          <Icon size={14} className={selected[sec.id] ? 'text-brand-400' : 'text-gray-500'} />
                          <div className="flex-1">
                            <p className="text-sm font-medium text-white">{sec.label}{fmtBytes(sec.size)}</p>
                            {!sec.included && <p className="text-[11px] text-gray-600">Not in this backup</p>}
                          </div>
                        </label>
                      );
                    })}
                  </div>
                </>
              ) : (
                <p className="text-sm text-gray-400">No manifest found — archive will be saved to backup storage but cannot be section-restored.</p>
              )}
            </div>
          )}

          {/* Running */}
          {phase === 'running' && (
            <div className="space-y-4">
              <div className="space-y-2">
                <div className="flex justify-between text-xs text-gray-400">
                  <span>{job?.current || 'Working…'}</span>
                  <span className="font-mono text-white">{pct}%</span>
                </div>
                <div className="h-2.5 bg-panel-700 rounded-full overflow-hidden">
                  <div className="h-full bg-brand-500 rounded-full transition-all duration-700" style={{ width: `${pct}%` }} />
                </div>
              </div>
              {msgs.length > 0 && (
                <div className="bg-panel-900/60 rounded-lg p-3 max-h-36 overflow-y-auto space-y-0.5">
                  {msgs.map((m, i) => (
                    <div key={i} className="flex items-start gap-2 text-xs">
                      <span className="text-gray-600 font-mono flex-shrink-0">{m.pct}%</span>
                      <span className={i === msgs.length - 1 ? 'text-gray-200' : 'text-gray-500'}>{m.msg}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Done */}
          {phase === 'done' && (
            <div className="flex items-center gap-3 bg-green-900/20 border border-green-800/40 rounded-lg px-4 py-4">
              <ShieldCheck size={22} className="text-green-400 flex-shrink-0" />
              <div>
                <p className="text-green-300 font-medium">Recovery complete &amp; verified</p>
                <p className="text-xs text-gray-400 mt-1">All selected sections have been restored successfully.</p>
              </div>
            </div>
          )}

          {/* Error */}
          {phase === 'error' && (
            <div className="flex items-center gap-3 bg-red-900/20 border border-red-800/40 rounded-lg px-4 py-3">
              <AlertCircle size={20} className="text-red-400 flex-shrink-0" />
              <div>
                <p className="text-red-300 font-medium text-sm">Failed</p>
                <p className="text-xs text-gray-400 mt-0.5">{errMsg}</p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-panel-700 bg-panel-900/40 flex gap-2 justify-end">
          {phase === 'review' && sections.length > 0 && (
            <>
              <button onClick={onClose} className="btn-ghost text-sm py-1.5 px-4">Cancel</button>
              <button
                onClick={startRecovery}
                disabled={!Object.values(selected).some(Boolean)}
                className="btn-primary flex items-center gap-2 text-sm py-1.5 px-4 disabled:opacity-40"
              >
                <ArrowRight size={14} /> Start Restore
              </button>
            </>
          )}
          {phase === 'review' && sections.length === 0 && (
            <button onClick={onClose} className="btn-ghost text-sm py-1.5 px-4">Close</button>
          )}
          {(phase === 'done' || phase === 'error') && (
            <button onClick={onClose} className="btn-primary flex items-center justify-center gap-2 w-full">
              <ArrowLeft size={15} /> Return to Backups
            </button>
          )}
          {phase === 'running' && (
            <p className="text-xs text-gray-500 text-center w-full">Restoring — do not navigate away.</p>
          )}
        </div>
      </div>
    </div>
  );
}
