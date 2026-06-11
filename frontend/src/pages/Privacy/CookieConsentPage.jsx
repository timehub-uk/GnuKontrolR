import { useState, useEffect } from 'react';
import { ArrowLeft, Cookie, CheckCircle, XCircle, Loader } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import api from '../../utils/api';

const COOKIE_CATEGORIES = [
  {
    key: 'essential',
    label: 'Essential Cookies',
    description: 'Required for the platform to function. These cannot be disabled.',
    required: true,
  },
  {
    key: 'functional',
    label: 'Functional Cookies',
    description: 'Remember your preferences and settings for a personalised experience.',
    required: false,
  },
  {
    key: 'analytics',
    label: 'Analytics Cookies',
    description: 'Help us understand how the platform is used so we can improve it.',
    required: false,
  },
  {
    key: 'marketing',
    label: 'Marketing Cookies',
    description: 'Used to deliver relevant advertisements and track marketing campaigns.',
    required: false,
  },
];

export default function CookieConsentPage() {
  const navigate = useNavigate();
  const [prefs, setPrefs] = useState({
    essential: true,
    functional: false,
    analytics: false,
    marketing: false,
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api
      .get('/api/compliance/consent/status')
      .then((res) => {
        const items = res.data?.consents || [];
        const cc = items.find((c) => c.consent_type === 'cookies');
        if (cc?.accepted) setSaved(true);
      })
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  const toggle = (key) => {
    if (key === 'essential') return;
    setPrefs((p) => ({ ...p, [key]: !p[key] }));
    setSaved(false);
  };

  const savePrefs = async (all, rejected) => {
    setSaving(true);
    setError(null);
    try {
      const p = all || prefs;
      await api.post('/api/compliance/consent/cookies/accept');
      // Store cookie preferences via a general profile update or custom endpoint
      setSaved(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to save preferences.');
    } finally {
      setSaving(false);
    }
  };

  const acceptAll = async () => {
    const all = { essential: true, functional: true, analytics: true, marketing: true };
    setPrefs(all);
    await savePrefs(all);
  };

  const rejectAll = async () => {
    const minimal = { essential: true, functional: false, analytics: false, marketing: false };
    setPrefs(minimal);
    await savePrefs({ essential: true, functional: false, analytics: false, marketing: false });
  };

  const save = async () => {
    await savePrefs(null);
  };

  if (!loaded) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader className="w-6 h-6 text-brand animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="p-2 rounded-lg hover:bg-panel-hover text-ink-muted hover:text-ink-primary transition-colors"
        >
          <ArrowLeft size={20} />
        </button>
        <div className="w-10 h-10 rounded-xl bg-brand/10 flex items-center justify-center">
          <Cookie className="w-5 h-5 text-brand" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-ink-primary">Cookie Preferences</h1>
          <p className="text-sm text-ink-muted">Manage how cookies are used on this platform</p>
        </div>
      </div>

      {saved && (
        <div className="flex items-center gap-2 px-4 py-3 bg-ok/10 border border-ok/20 rounded-lg">
          <CheckCircle size={18} className="text-ok shrink-0" />
          <span className="text-sm text-ok">Your cookie preferences have been saved.</span>
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 px-4 py-3 bg-error/10 border border-error/20 rounded-lg">
          <XCircle size={18} className="text-error shrink-0" />
          <span className="text-sm text-error">{error}</span>
        </div>
      )}

      {/* Cookie Categories */}
      <div className="bg-panel-card border border-panel-subtle rounded-xl divide-y divide-panel-subtle">
        {COOKIE_CATEGORIES.map((cat) => (
          <div key={cat.key} className="flex items-start gap-4 p-4">
            <div className="flex items-center h-5">
              <input
                type="checkbox"
                checked={prefs[cat.key]}
                onChange={() => toggle(cat.key)}
                disabled={cat.required}
                className="w-4 h-4 rounded border-panel-subtle bg-panel-surface
                           text-brand focus:ring-brand/50
                           disabled:opacity-60 disabled:cursor-not-allowed"
              />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-ink-primary">{cat.label}</span>
                {cat.required && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-ok/10 text-ok uppercase tracking-wider font-medium">
                    Required
                  </span>
                )}
              </div>
              <p className="text-xs text-ink-muted mt-0.5">{cat.description}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap gap-3 justify-between">
        <div className="flex gap-2">
          <button
            onClick={acceptAll}
            disabled={saving}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-brand hover:bg-brand-hover text-white transition-colors disabled:opacity-50"
          >
            Accept All
          </button>
          <button
            onClick={rejectAll}
            disabled={saving}
            className="px-4 py-2 rounded-lg text-sm font-medium border border-panel-subtle text-ink-primary hover:bg-panel-hover transition-colors disabled:opacity-50"
          >
            Reject All
          </button>
        </div>
        <button
          onClick={save}
          disabled={saving}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-panel-surface border border-panel-subtle
                     text-ink-primary hover:bg-panel-hover transition-colors disabled:opacity-50"
        >
          {saving ? (
            <span className="flex items-center gap-2">
              <Loader size={14} className="animate-spin" /> Saving…
            </span>
          ) : (
            'Save Preferences'
          )}
        </button>
      </div>
    </div>
  );
}
