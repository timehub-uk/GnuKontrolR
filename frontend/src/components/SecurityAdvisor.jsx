/**
 * SecurityAdvisor
 * Real-time security audit panel for a domain.
 * Connects via WebSocket (falls back to polling) to the security check endpoint.
 * Shows scored findings with severity, auto-fix buttons, and advice.
 */
import { useState } from 'react';
import {
  Shield, ShieldAlert, ShieldCheck, ShieldOff,
  RefreshCw, Loader, ChevronDown, ChevronRight,
  Zap, AlertTriangle, Info, CheckCircle, X,
} from 'lucide-react';
import { useLiveCheck } from '../hooks/useLiveCheck';
import api from '../utils/api';

const SEV = {
  critical: { icon: ShieldOff,   color: 'text-red-400',    bg: 'bg-red-900/30 border-red-800',    label: 'Critical' },
  high:     { icon: ShieldAlert,  color: 'text-orange-400', bg: 'bg-orange-900/30 border-orange-800', label: 'High' },
  medium:   { icon: AlertTriangle,color: 'text-yellow-400', bg: 'bg-yellow-900/30 border-yellow-800', label: 'Medium' },
  low:      { icon: Info,         color: 'text-blue-400',   bg: 'bg-blue-900/20 border-blue-900',   label: 'Low' },
  pass:     { icon: CheckCircle,  color: 'text-green-400',  bg: 'bg-green-900/20 border-green-900', label: 'Pass' },
};

function scoreColor(score) {
  if (score >= 90) return 'text-green-400';
  if (score >= 70) return 'text-yellow-400';
  if (score >= 50) return 'text-orange-400';
  return 'text-red-400';
}

function ScoreRing({ score }) {
  const r   = 22;
  const c   = 2 * Math.PI * r;
  const off = c - (score / 100) * c;
  return (
    <div className="relative w-16 h-16 flex items-center justify-center">
      <svg className="absolute inset-0 -rotate-90" viewBox="0 0 56 56">
        <circle cx="28" cy="28" r={r} fill="none" stroke="#1f2937" strokeWidth="4" />
        <circle cx="28" cy="28" r={r} fill="none"
          stroke={score >= 80 ? '#22c55e' : score >= 60 ? '#eab308' : '#f97316'}
          strokeWidth="4" strokeDasharray={c} strokeDashoffset={off}
          strokeLinecap="round" className="transition-all duration-700" />
      </svg>
      <span className={`text-sm font-bold z-10 ${scoreColor(score)}`}>{score}</span>
    </div>
  );
}

// ── Auto-fix progress card ────────────────────────────────────────────────────
const FIX_STEPS = [
  'Connecting to container API…',
  'Writing security header config…',
  'Reloading nginx…',
  'Verifying headers…',
];

function FixProgressCard({ check, domain, onDone }) {
  const [step,    setStep]    = useState(0);   // 0 = idle, 1-4 = in progress, 5 = done, -1 = error
  const [errMsg,  setErrMsg]  = useState('');
  const [result,  setResult]  = useState('');

  const run = async () => {
    setStep(1);
    setErrMsg('');

    // Simulate step progression while the request runs
    let s = 1;
    const tick = setInterval(() => {
      s = Math.min(s + 1, FIX_STEPS.length);
      setStep(s);
    }, 600);

    try {
      const r = await api.post(`/api/security/fix/${domain}`, { check_id: check.id });
      clearInterval(tick);
      setStep(FIX_STEPS.length + 1);  // done
      setResult(r.data.message || 'Fix applied.');
    } catch (e) {
      clearInterval(tick);
      setStep(-1);
      setErrMsg(e?.response?.data?.detail || 'Auto-fix failed');
    }
  };

  // Idle state — just show the button
  if (step === 0) {
    return (
      <button
        onClick={run}
        className="flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-brand/20 text-brand hover:bg-brand/35 transition-colors border border-brand/30"
      >
        <Zap size={10} />
        Auto-fix
      </button>
    );
  }

  // In-progress / done / error card
  return (
    <div className="mt-2 rounded-xl border border-panel-subtle bg-panel-card p-3 space-y-2 text-[11px]">
      <div className="flex items-center gap-1.5 font-semibold text-ink-primary">
        {step < 0 ? (
          <X size={13} className="text-bad-light" />
        ) : step > FIX_STEPS.length ? (
          <CheckCircle size={13} className="text-ok" />
        ) : (
          <Loader size={13} className="animate-spin text-brand" />
        )}
        {step < 0 ? 'Fix failed' : step > FIX_STEPS.length ? 'Fix complete' : 'Applying fix…'}
      </div>

      {step > 0 && step <= FIX_STEPS.length && (
        <div className="space-y-1">
          {FIX_STEPS.map((label, i) => (
            <div key={i} className={`flex items-center gap-1.5 ${i < step - 1 ? 'text-ok' : i === step - 1 ? 'text-brand' : 'text-ink-faint'}`}>
              {i < step - 1 ? <CheckCircle size={10} /> : i === step - 1 ? <Loader size={10} className="animate-spin" /> : <div className="w-2.5 h-2.5 rounded-full border border-current opacity-30" />}
              {label}
            </div>
          ))}
        </div>
      )}

      {step > FIX_STEPS.length && result && (
        <p className="text-ok whitespace-pre-wrap text-[10px]">{result}</p>
      )}

      {step < 0 && errMsg && (
        <p className="text-bad-light">{errMsg}</p>
      )}

      {(step > FIX_STEPS.length || step < 0) && (
        <button
          onClick={() => { setStep(0); onDone?.(); }}
          className="w-full py-1 rounded-lg bg-ok/10 hover:bg-ok/20 text-ok text-[11px] font-semibold transition-colors border border-ok/25"
        >
          Done
        </button>
      )}
    </div>
  );
}

function CheckRow({ check, domain, onFixed }) {
  const [expanded, setExpanded]       = useState(false);
  const [showFixCard, setShowFixCard] = useState(false);
  const sev = SEV[check.severity] || SEV.low;
  const Icon = sev.icon;

  return (
    <div className={`rounded-lg border p-3 ${sev.bg}`}>
      <div className="flex items-start gap-2">
        <Icon size={15} className={`mt-0.5 flex-shrink-0 ${sev.color}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 justify-between">
            <span className="text-sm font-medium text-gray-200">{check.title}</span>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              {check.auto_fixable && check.severity !== 'pass' && !showFixCard && (
                <button
                  onClick={() => setShowFixCard(true)}
                  className="flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-brand/20 text-brand hover:bg-brand/35 transition-colors border border-brand/30"
                >
                  <Zap size={10} />
                  Auto-fix
                </button>
              )}
              {check.details && (
                <button onClick={() => setExpanded(e => !e)} className="text-gray-500 hover:text-gray-300">
                  {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </button>
              )}
            </div>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">{check.message}</p>
          {showFixCard && (
            <FixProgressCard
              check={check}
              domain={domain}
              onDone={() => { setShowFixCard(false); onFixed?.(); }}
            />
          )}
        </div>
      </div>

      {expanded && check.details && (
        <div className="mt-2 ml-5 space-y-1.5 border-t border-white/5 pt-2">
          {check.details.map((d, i) => (
            <p key={i} className="text-xs text-gray-400">{d}</p>
          ))}
          {check.remediation && (
            <div className="bg-panel-900/60 rounded p-2 text-xs text-gray-300 font-mono whitespace-pre-wrap">
              {check.remediation}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function SecurityAdvisor({ domain }) {
  // Use REST endpoint for polling; WS endpoint for live mode
  const endpoint = domain
    ? `/api/security/check/${domain}`
    : null;

  const { checks, loading, error, refresh } = useLiveCheck(endpoint, {
    mode: 'poll',
    interval: 30000,
    enabled: !!domain,
  });

  const score = checks.length
    ? Math.round((checks.filter(c => c.severity === 'pass').length / checks.length) * 100)
    : 0;

  const bySeverity = ['critical','high','medium','low','pass'].reduce((acc, s) => {
    acc[s] = checks.filter(c => c.severity === s);
    return acc;
  }, {});

  const issueCount = checks.filter(c => c.severity !== 'pass').length;

  if (!domain) {
    return (
      <div className="card text-center py-8 text-gray-500">
        <Shield size={24} className="mx-auto mb-2 opacity-40" />
        Select a domain to run a security audit.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header + score */}
      <div className="card flex items-center gap-4">
        <ScoreRing score={score} />
        <div className="flex-1">
          <h3 className="font-semibold text-white text-sm">Security Score — {domain}</h3>
          <p className="text-xs text-gray-400 mt-0.5">
            {loading ? 'Scanning…' : `${issueCount} issue${issueCount !== 1 ? 's' : ''} found · ${checks.filter(c => c.severity === 'pass').length} checks passed`}
          </p>
          <div className="flex gap-2 mt-1.5 text-xs">
            {['critical','high','medium','low'].map(s => {
              const n = bySeverity[s]?.length;
              if (!n) return null;
              return (
                <span key={s} className={`px-1.5 py-0.5 rounded ${SEV[s].bg} ${SEV[s].color}`}>
                  {n} {s}
                </span>
              );
            })}
          </div>
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="text-gray-400 hover:text-white p-1.5 rounded-lg hover:bg-panel-700 transition-colors"
          title="Re-scan"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {error && (
        <div className="card text-sm text-red-400 flex items-center gap-2">
          <X size={14} /> {error}
        </div>
      )}

      {/* Check list */}
      {!loading && checks.length > 0 && (
        <div className="space-y-2">
          {['critical','high','medium','low'].map(sev =>
            bySeverity[sev]?.length > 0 && (
              <div key={sev} className="space-y-1.5">
                <p className="text-xs uppercase font-semibold tracking-wider text-gray-500">
                  {SEV[sev].label} ({bySeverity[sev].length})
                </p>
                {bySeverity[sev].map(c => (
                  <CheckRow key={c.id} check={c} domain={domain} onFixed={refresh} />
                ))}
              </div>
            )
          )}
          {bySeverity.pass?.length > 0 && (
            <details className="group">
              <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-300 list-none flex items-center gap-1">
                <ChevronRight size={12} className="group-open:rotate-90 transition-transform" />
                {bySeverity.pass.length} passing checks
              </summary>
              <div className="mt-1.5 space-y-1.5">
                {bySeverity.pass.map(c => (
                  <CheckRow key={c.id} check={c} domain={domain} onFixed={refresh} />
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      {!loading && checks.length === 0 && !error && (
        <div className="card text-center py-6 text-gray-500 text-sm">
          <ShieldCheck size={20} className="mx-auto mb-2 text-green-500" />
          No issues found.
        </div>
      )}
    </div>
  );
}
