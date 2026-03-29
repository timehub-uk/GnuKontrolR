/**
 * BackupProgressCard
 * Popup overlay shown while a full-site backup is running.
 * Polls /api/container/{domain}/site-backup/status/{job_id} every 1.5s.
 */
import { useEffect, useRef, useState } from 'react';
import {
  HardDrive, CheckCircle, AlertCircle, Loader,
  ArrowLeft, ShieldCheck, X,
} from 'lucide-react';
import api from '../utils/api';

const TYPE_LABELS = {
  files:   'Web Files',
  website: 'Website + Uploads',
  db:      'Database',
  full:    'Full Site',
};

const TYPE_ICONS = {
  files:   '📁',
  website: '🌐',
  db:      '🗄️',
  full:    '💾',
};

const PHASE_LABEL = {
  'Initialising':  'Preparing environment',
  'Database dump': 'Exporting database',
  'Compression':   'Compressing archive',
  'Verification':  'Verifying integrity',
  'Complete':      'Complete',
  'Starting':      'Starting',
};

export default function BackupProgressCard({ domain, jobId, backupType, onClose, onDone }) {
  const [job,     setJob]     = useState(null);
  const [error,   setError]   = useState('');
  const timerRef              = useRef(null);
  const doneRef               = useRef(false);

  useEffect(() => {
    if (!jobId) return;

    async function poll() {
      try {
        const r = await api.get(`/api/container/${domain}/site-backup/status/${jobId}`);
        setJob(r.data);

        if (r.data.status === 'done' && !doneRef.current) {
          doneRef.current = true;
          clearInterval(timerRef.current);
          onDone?.(r.data.result);
        } else if (r.data.status === 'error') {
          clearInterval(timerRef.current);
          setError(r.data.error || 'Backup failed');
        }
      } catch (e) {
        setError(e?.response?.data?.detail || 'Lost contact with container');
        clearInterval(timerRef.current);
      }
    }

    poll();
    timerRef.current = setInterval(poll, 1500);
    return () => clearInterval(timerRef.current);
  }, [jobId, domain, onDone]);

  const pct     = job?.pct ?? 0;
  const current = job?.current ?? 'Starting…';
  const msgs    = job?.messages ?? [];
  const isDone  = job?.status === 'done';
  const isError = job?.status === 'error' || !!error;

  const phaseLabel = PHASE_LABEL[current] || current;

  // Determine which step is active
  const steps = [
    { label: 'Prepare',  threshold: 10 },
    { label: 'Archive',  threshold: 75 },
    { label: 'Compress', threshold: 80 },
    { label: 'Verify',   threshold: 90 },
    { label: 'Complete', threshold: 100 },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-panel-800 border border-panel-600 rounded-2xl shadow-2xl overflow-hidden">

        {/* Header */}
        <div className={`px-6 py-4 flex items-center justify-between border-b border-panel-700
          ${isDone ? 'bg-green-900/20' : isError ? 'bg-red-900/20' : 'bg-brand-900/20'}`}>
          <div className="flex items-center gap-3">
            <span className="text-2xl">{TYPE_ICONS[backupType] || '💾'}</span>
            <div>
              <h2 className="font-semibold text-white text-sm">
                {TYPE_LABELS[backupType] || backupType} Backup
              </h2>
              <p className="text-xs text-gray-400">{domain}</p>
            </div>
          </div>
          {(isDone || isError) && (
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-white transition-colors"
            >
              <X size={18} />
            </button>
          )}
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-5">

          {/* Progress bar */}
          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs text-gray-400">
              <span>{isError ? 'Failed' : isDone ? 'Complete' : phaseLabel}</span>
              <span className="font-mono font-medium text-white">{pct}%</span>
            </div>
            <div className="h-2.5 bg-panel-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-700 ease-out
                  ${isError ? 'bg-red-500' : isDone ? 'bg-green-500' : 'bg-brand-500'}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>

          {/* Step indicators */}
          <div className="flex items-center justify-between">
            {steps.map((step, i) => {
              const reached = pct >= step.threshold;
              const active  = pct >= (steps[i - 1]?.threshold ?? 0) && pct < step.threshold;
              return (
                <div key={step.label} className="flex flex-col items-center gap-1 flex-1">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center transition-all
                    ${reached && !isError
                      ? 'bg-green-500/20 text-green-400'
                      : active && !isError
                      ? 'bg-brand-500/20 text-brand-400 ring-1 ring-brand-500 animate-pulse'
                      : isError && active
                      ? 'bg-red-500/20 text-red-400'
                      : 'bg-panel-700 text-gray-600'
                    }`}>
                    {reached && !isError
                      ? <CheckCircle size={13} />
                      : active && !isError
                      ? <Loader size={13} className="animate-spin" />
                      : <span className="text-[10px]">{i + 1}</span>
                    }
                  </div>
                  <span className={`text-[10px] text-center leading-tight
                    ${reached && !isError ? 'text-green-400' : active ? 'text-brand-300' : 'text-gray-600'}`}>
                    {step.label}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Current activity */}
          {!isDone && !isError && (
            <div className="flex items-center gap-2 bg-panel-700/50 rounded-lg px-3 py-2">
              <Loader size={13} className="animate-spin text-brand-400 flex-shrink-0" />
              <span className="text-xs text-gray-300 truncate">{msgs[msgs.length - 1]?.msg || 'Working…'}</span>
            </div>
          )}

          {/* Log messages */}
          {msgs.length > 1 && (
            <div className="bg-panel-900/60 rounded-lg p-3 max-h-28 overflow-y-auto space-y-0.5">
              {msgs.map((m, i) => (
                <div key={i} className="flex items-start gap-2 text-xs">
                  <span className="text-gray-600 font-mono flex-shrink-0">{m.pct}%</span>
                  <span className={i === msgs.length - 1 ? 'text-gray-200' : 'text-gray-500'}>
                    {m.msg}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Done state */}
          {isDone && (
            <div className="flex items-center gap-3 bg-green-900/20 border border-green-800/40 rounded-lg px-4 py-3">
              <ShieldCheck size={20} className="text-green-400 flex-shrink-0" />
              <div className="text-sm">
                <p className="text-green-300 font-medium">Backup complete & verified</p>
                {job?.result && (
                  <p className="text-xs text-gray-400 mt-0.5">
                    {job.result.filename} &mdash; {(job.result.size / 1024 / 1024).toFixed(1)} MB
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Error state */}
          {isError && (
            <div className="flex items-center gap-3 bg-red-900/20 border border-red-800/40 rounded-lg px-4 py-3">
              <AlertCircle size={20} className="text-red-400 flex-shrink-0" />
              <div className="text-sm">
                <p className="text-red-300 font-medium">Backup failed</p>
                <p className="text-xs text-gray-400 mt-0.5">{error || job?.error}</p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-panel-700 bg-panel-900/40">
          {isDone ? (
            <button
              onClick={onClose}
              className="w-full flex items-center justify-center gap-2 btn-primary"
            >
              <ArrowLeft size={15} /> Return to Backups
            </button>
          ) : isError ? (
            <button
              onClick={onClose}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-panel-700 text-gray-300 hover:bg-panel-600 text-sm transition-colors"
            >
              <ArrowLeft size={15} /> Return to Backups
            </button>
          ) : (
            <p className="text-xs text-gray-500 text-center">
              Backup running — you can navigate away, it will continue in the background.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
