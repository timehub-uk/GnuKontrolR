import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Shield, ShieldCheck, Globe, BarChart3, HardDrive,
  RefreshCw, Server, Check, ChevronRight, ChevronLeft,
  Sparkles, ExternalLink, Clock, Activity, Settings,
} from 'lucide-react';
import api from '../utils/api';
import { toast } from 'sonner';

const STEPS = [
  {
    id: 'secrets',
    icon: Shield,
    title: 'Change Default Secrets',
    description: 'Update all default passwords and secrets in .env — database credentials, JWT secret, API keys.',
    action: { label: 'Open Settings', path: '/settings' },
    field: 'secrets_changed',
  },
  {
    id: 'fail2ban',
    icon: ShieldCheck,
    title: 'Enable Fail2ban Rules',
    description: 'Protect SSH, web panel, and mail services from brute-force attacks. Pre-configured jails are ready.',
    action: { label: 'Open Security → Fail2ban', path: '/security' },
    field: 'fail2ban_done',
  },
  {
    id: 'geo',
    icon: Globe,
    title: 'Configure Geo-Blocking',
    description: 'Restrict access by country to reduce attack surface. Recommended: block high-risk regions.',
    action: { label: 'Open Security → Geo', path: '/security' },
    field: 'geo_block_done',
  },
  {
    id: 'grafana',
    icon: BarChart3,
    title: 'Review Grafana Dashboards',
    description: 'Check system metrics, container resource usage, and DNS query patterns for anomalies.',
    action: { label: 'Open Grafana', path: null, external: 'http://localhost:3001' },
    field: 'grafana_done',
  },
  {
    id: 'backup_cron',
    icon: HardDrive,
    title: 'Schedule Automated Backups',
    description: 'Daily backups at 2 AM — includes all site files, databases, DNS zones, and panel config.',
    action: null,
    field: 'backup_cron_set',
    hasToggle: true,
  },
  {
    id: 'cve_cron',
    icon: Activity,
    title: 'CVE Monitoring & Auto-Updates',
    description: 'Weekly CVE feed check (Mon 6 AM) and panel update check (Sun 5 AM). Stay informed on threats.',
    action: null,
    field: 'cve_cron_set',
    hasToggle: true,
  },
  {
    id: 'services',
    icon: Server,
    title: 'Disable Unused Services',
    description: 'Review the service list and disable anything you don\'t need — reduces resource usage and attack surface.',
    action: { label: 'Open Master Services', path: '/services' },
    field: 'services_pruned',
  },
];

export default function SetupWizard() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);
  const [completed, setCompleted] = useState(false);
  const [stepState, setStepState] = useState({});
  const [creatingCrons, setCreatingCrons] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get('/api/setup/status');
        if (!data.completed) {
          setStep(data.step_index || 0);
          setStepState(data.steps || {});
          setVisible(true);
        }
      } catch {
        // non-fatal — setup API may not exist on first deploy
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const markStep = async (field, value = true) => {
    try {
      await api.post('/api/setup/step', { field, value, step_index: step });
      setStepState(prev => ({ ...prev, [field]: value }));
    } catch { /* non-fatal */ }
  };

  const totalSteps = STEPS.length;

  const isStepDone = (idx) => {
    const s = STEPS[idx];
    if (s.hasToggle) return stepState[s.field] === true;
    return stepState[s.field] === true;
  };

  const canProceed = step < totalSteps - 1 || isStepDone(step);

  const nextStep = () => {
    if (step < totalSteps - 1) {
      setStep(s => s + 1);
    }
  };

  const prevStep = () => {
    if (step > 0) setStep(s => s - 1);
  };

  const skipStep = async () => {
    await markStep(STEPS[step].field, false);
    nextStep();
  };

  const handleAction = async (s) => {
    if (s.action?.path) {
      navigate(s.action.path);
    } else if (s.action?.external) {
      window.open(s.action.external, '_blank', 'noopener');
    }
    await markStep(s.field, true);
  };

  const handleFinish = async () => {
    setCreatingCrons(true);
    try {
      await api.post('/api/setup/crons', {
        backup: true,
        cve: true,
        update: true,
      });
      await api.post('/api/setup/complete');
      toast.success('Setup complete! Crons created for backup, CVE monitoring, and updates.');
      setCompleted(true);
      setTimeout(() => setVisible(false), 500);
    } catch (err) {
      toast.error('Failed to finalize setup: ' + (err?.response?.data?.detail || err.message));
    } finally {
      setCreatingCrons(false);
    }
  };

  const current = STEPS[step];
  const progress = ((step + 1) / totalSteps) * 100;

  if (!visible || completed) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl bg-panel-800 border border-panel-border rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 pt-6 pb-4 border-b border-panel-border">
          <div className="flex items-center gap-3 mb-1">
            <div className="w-9 h-9 rounded-xl bg-brand/15 flex items-center justify-center">
              <Sparkles size={18} className="text-brand-light" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-ink-primary">Welcome to GnuKontrolR</h2>
              <p className="text-xs text-ink-muted">Let's get your panel set up securely in a few steps</p>
            </div>
          </div>
          {/* Progress bar */}
          <div className="mt-4 w-full h-1 bg-panel-border rounded-full overflow-hidden">
            <div
              className="h-full bg-brand rounded-full transition-all duration-400 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="flex justify-between mt-1.5 text-[10px] text-ink-faint">
            <span>Step {step + 1} of {totalSteps}</span>
            <span>{Math.round(progress)}%</span>
          </div>
        </div>

        {/* Body */}
        <div className="px-6 py-6 min-h-[240px]">
          <div className="flex items-start gap-4 mb-4">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
              isStepDone(step) ? 'bg-ok/15' : 'bg-panel-elevated'
            }`}>
              <current.icon
                size={20}
                className={isStepDone(step) ? 'text-ok' : 'text-brand-light'}
              />
            </div>
            <div className="flex-1">
              <h3 className="text-base font-semibold text-ink-primary mb-1">{current.title}</h3>
              <p className="text-sm text-ink-muted leading-relaxed">{current.description}</p>
            </div>
            {isStepDone(step) && (
              <div className="w-6 h-6 rounded-full bg-ok/15 flex items-center justify-center flex-shrink-0">
                <Check size={14} className="text-ok" />
              </div>
            )}
          </div>

          {/* Action area */}
          <div className="mt-4 pl-14">
            {current.action && !isStepDone(step) && (
              <button
                onClick={() => handleAction(current)}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-light transition-colors"
              >
                {current.action.label}
                {current.action.external ? (
                  <ExternalLink size={14} />
                ) : (
                  <ChevronRight size={14} />
                )}
              </button>
            )}

            {current.hasToggle && (
              <div className="flex items-center gap-3">
                <button
                  onClick={async () => {
                    await markStep(current.field, true);
                    setStepState(prev => ({ ...prev, [current.field]: true }));
                  }}
                  disabled={stepState[current.field]}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    stepState[current.field]
                      ? 'bg-ok/15 text-ok cursor-default'
                      : 'bg-brand text-white hover:bg-brand-light'
                  }`}
                >
                  {stepState[current.field] ? (
                    <span className="flex items-center gap-2"><Check size={14} /> Enabled</span>
                  ) : (
                    <span className="flex items-center gap-2"><Clock size={14} /> Enable Cron</span>
                  )}
                </button>
                <span className="text-xs text-ink-faint">
                  {stepState[current.field] ? 'Cron will run on schedule' : 'This creates a system crontab entry'}
                </span>
              </div>
            )}

            {isStepDone(step) && !current.hasToggle && (
              <div className="flex items-center gap-2 text-ok text-sm">
                <Check size={14} />
                <span>Completed</span>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-panel-border flex items-center justify-between">
          <div className="flex gap-2">
            {STEPS.map((_, idx) => (
              <div
                key={idx}
                className={`w-2 h-2 rounded-full transition-colors ${
                  idx === step
                    ? 'bg-brand'
                    : isStepDone(idx)
                    ? 'bg-ok'
                    : 'bg-panel-border'
                }`}
              />
            ))}
          </div>

          <div className="flex items-center gap-2">
            {step < totalSteps - 1 ? (
              <>
                <button
                  onClick={skipStep}
                  className="px-3 py-1.5 text-xs text-ink-muted hover:text-ink-secondary transition-colors"
                >
                  Skip
                </button>
                {canProceed ? (
                  <button
                    onClick={nextStep}
                    className="inline-flex items-center gap-1 px-4 py-1.5 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-light transition-colors"
                  >
                    Next <ChevronRight size={14} />
                  </button>
                ) : (
                  <button
                    onClick={async () => {
                      await markStep(current.field, true);
                      nextStep();
                    }}
                    className="inline-flex items-center gap-1 px-4 py-1.5 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-light transition-colors"
                  >
                    Mark Done <Check size={14} />
                  </button>
                )}
              </>
            ) : (
              <button
                onClick={handleFinish}
                disabled={creatingCrons}
                className="inline-flex items-center gap-2 px-5 py-2 rounded-lg bg-ok text-white text-sm font-medium hover:bg-ok/90 transition-colors disabled:opacity-50"
              >
                {creatingCrons ? (
                  <><RefreshCw size={14} className="animate-spin" /> Finalizing…</>
                ) : (
                  <><Sparkles size={14} /> Complete Setup</>
                )}
              </button>
            )}

            {step > 0 && (
              <button
                onClick={prevStep}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs text-ink-muted hover:text-ink-secondary transition-colors"
              >
                <ChevronLeft size={14} /> Back
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
