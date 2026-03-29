/**
 * RecoveryCard
 * Opened when the user clicks "Recover" on a backup row.
 * 1. Fetches manifest XML → parses sections
 * 2. Shows checkboxes for available sections
 * 3. Starts async recovery job, polls progress
 * 4. Shows complete / error state + "Return to Backups" button
 */
import { useEffect, useRef, useState } from 'react';
import {
  ArchiveRestore, CheckCircle, AlertCircle, Loader,
  ArrowLeft, X, ShieldCheck, Database, FolderOpen,
  Globe, Lock, Settings,
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
  const parser  = new DOMParser();
  const doc     = parser.parseFromString(xml, 'text/xml');
  const nodes   = doc.querySelectorAll('section');
  return Array.from(nodes).map(n => ({
    id:       n.getAttribute('id'),
    label:    n.getAttribute('label') || n.getAttribute('id'),
    icon:     n.getAttribute('icon') || '📦',
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

export default function RecoveryCard({ domain, filename, onClose }) {
  // Phase: 'loading' | 'select' | 'running' | 'done' | 'error'
  const [phase,    setPhase]    = useState('loading');
  const [sections, setSections] = useState([]);
  const [selected, setSelected] = useState({});
  const [metaErr,  setMetaErr]  = useState('');

  // Job polling
  const [job,      setJob]      = useState(null);
  const [pollErr,  setPollErr]  = useState('');
  const timerRef               = useRef(null);

  // Load manifest
  useEffect(() => {
    api.get(`/api/container/${domain}/site-backup/${filename}/meta`)
      .then(r => {
        const secs = parseManifest(r.data.xml);
        setSections(secs);
        const init = {};
        secs.filter(s => s.included).forEach(s => { init[s.id] = true; });
        setSelected(init);
        setPhase('select');
      })
      .catch(e => {
        setMetaErr(e?.response?.data?.detail || 'Failed to read backup manifest');
        setPhase('error');
      });
  }, [domain, filename]);

  // Poll recovery job
  useEffect(() => {
    if (phase !== 'running' || !job?.jobId) return;
    async function poll() {
      try {
        const r = await api.get(`/api/container/${domain}/site-backup/recovery-status/${job.jobId}`);
        setJob(prev => ({ ...prev, ...r.data }));
        if (r.data.status === 'done')  { clearInterval(timerRef.current); setPhase('done'); }
        if (r.data.status === 'error') { clearInterval(timerRef.current); setPhase('error'); setPollErr(r.data.error || 'Recovery failed'); }
      } catch (e) {
        clearInterval(timerRef.current);
        setPollErr(e?.response?.data?.detail || 'Lost contact with container');
        setPhase('error');
      }
    }
    poll();
    timerRef.current = setInterval(poll, 1500);
    return () => clearInterval(timerRef.current);
  }, [phase, job?.jobId, domain]);

  async function startRecovery() {
    const sectionIds = Object.entries(selected).filter(([, v]) => v).map(([k]) => k);
    if (!sectionIds.length) return;
    try {
      const r = await api.post(`/api/container/${domain}/site-backup/${filename}/recover`, { sections: sectionIds });
      setJob({ jobId: r.data.job_id, status: 'running', pct: 0, messages: [], current: 'Starting…' });
      setPhase('running');
    } catch (e) {
      setMetaErr(e?.response?.data?.detail || 'Failed to start recovery');
      setPhase('error');
    }
  }

  const pct      = job?.pct ?? 0;
  const msgs     = job?.messages ?? [];
  const current  = job?.current ?? 'Starting…';
  const isDone   = phase === 'done';
  const isError  = phase === 'error';
  const isRunning = phase === 'running';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-lg bg-panel-800 border border-panel-600 rounded-2xl shadow-2xl overflow-hidden">

        {/* Header */}
        <div className={`px-6 py-4 flex items-center justify-between border-b border-panel-700
          ${isDone ? 'bg-green-900/20' : isError ? 'bg-red-900/20' : 'bg-brand-900/20'}`}>
          <div className="flex items-center gap-3">
            <ArchiveRestore size={20} className={isDone ? 'text-green-400' : isError ? 'text-red-400' : 'text-brand-400'} />
            <div>
              <h2 className="font-semibold text-white text-sm">Restore Backup</h2>
              <p className="text-xs text-gray-400 font-mono">{filename}</p>
            </div>
          </div>
          {(isDone || isError || phase === 'select') && (
            <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">
              <X size={18} />
            </button>
          )}
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4">

          {/* Loading manifest */}
          {phase === 'loading' && (
            <div className="flex items-center gap-3 py-6 text-gray-400">
              <Loader size={18} className="animate-spin text-brand-400" />
              <span className="text-sm">Reading backup manifest…</span>
            </div>
          )}

          {/* Section selector */}
          {phase === 'select' && (
            <>
              <p className="text-xs text-gray-400">
                Select which sections to restore from <span className="font-mono text-gray-300">{filename}</span>:
              </p>
              <div className="space-y-2">
                {sections.map(sec => {
                  const Icon = SECTION_ICONS[sec.id] || FolderOpen;
                  return (
                    <label
                      key={sec.id}
                      className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-all
                        ${!sec.included ? 'opacity-40 cursor-not-allowed border-panel-600 bg-panel-700/30' :
                          selected[sec.id]
                            ? 'border-brand-500/50 bg-brand-900/20'
                            : 'border-panel-600 bg-panel-700/30 hover:border-panel-500'
                        }`}
                    >
                      <input
                        type="checkbox"
                        checked={!!selected[sec.id]}
                        disabled={!sec.included}
                        onChange={e => setSelected(prev => ({ ...prev, [sec.id]: e.target.checked }))}
                        className="accent-brand-500"
                      />
                      <Icon size={15} className={selected[sec.id] ? 'text-brand-400' : 'text-gray-500'} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-white">{sec.label}{fmtBytes(sec.size)}</p>
                        {!sec.included && <p className="text-[11px] text-gray-600">Not included in this backup</p>}
                      </div>
                      {sec.included && selected[sec.id] && (
                        <CheckCircle size={14} className="text-brand-400 flex-shrink-0" />
                      )}
                    </label>
                  );
                })}
              </div>
              {metaErr && (
                <p className="text-xs text-red-400 flex items-center gap-1">
                  <AlertCircle size={12} /> {metaErr}
                </p>
              )}
            </>
          )}

          {/* Running — progress */}
          {isRunning && (
            <div className="space-y-4">
              <div className="space-y-2">
                <div className="flex justify-between text-xs text-gray-400">
                  <span>{current}</span>
                  <span className="font-mono text-white">{pct}%</span>
                </div>
                <div className="h-2.5 bg-panel-700 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full bg-brand-500 transition-all duration-700 ease-out"
                    style={{ width: `${pct}%` }}
                  />
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
          {isDone && (
            <div className="flex items-center gap-3 bg-green-900/20 border border-green-800/40 rounded-lg px-4 py-3">
              <ShieldCheck size={20} className="text-green-400 flex-shrink-0" />
              <div className="text-sm">
                <p className="text-green-300 font-medium">Recovery complete</p>
                <p className="text-xs text-gray-400 mt-0.5">All selected sections have been restored successfully.</p>
              </div>
            </div>
          )}

          {/* Error */}
          {isError && (
            <div className="flex items-center gap-3 bg-red-900/20 border border-red-800/40 rounded-lg px-4 py-3">
              <AlertCircle size={20} className="text-red-400 flex-shrink-0" />
              <div className="text-sm">
                <p className="text-red-300 font-medium">Recovery failed</p>
                <p className="text-xs text-gray-400 mt-0.5">{metaErr || pollErr || 'An unknown error occurred.'}</p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-panel-700 bg-panel-900/40 flex gap-2 justify-end">
          {phase === 'select' && (
            <>
              <button onClick={onClose} className="btn-ghost text-sm py-1.5 px-4">Cancel</button>
              <button
                onClick={startRecovery}
                disabled={!Object.values(selected).some(Boolean)}
                className="btn-primary flex items-center gap-2 text-sm py-1.5 px-4 disabled:opacity-40"
              >
                <ArchiveRestore size={14} /> Start Recovery
              </button>
            </>
          )}
          {(isDone || isError) && (
            <button onClick={onClose} className="btn-primary flex items-center justify-center gap-2 w-full">
              <ArrowLeft size={15} /> Return to Backups
            </button>
          )}
          {isRunning && (
            <p className="text-xs text-gray-500 text-center w-full">
              Recovery in progress — do not navigate away.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
