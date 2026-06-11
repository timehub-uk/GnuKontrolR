import { useState, useEffect } from 'react';
import { Cookie, X, CheckCircle } from 'lucide-react';
import api from '../utils/api';

const COOKIE_CATEGORIES = [
  { key: 'functional', label: 'Functional', description: 'Remember preferences' },
  { key: 'analytics', label: 'Analytics', description: 'Help us improve' },
  { key: 'marketing', label: 'Marketing', description: 'Relevant ads' },
];

export default function CookieConsentBanner() {
  const [visible, setVisible] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [saving, setSaving] = useState(false);
  const [prefs, setPrefs] = useState({
    functional: false,
    analytics: false,
    marketing: false,
  });
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api
      .get('/api/compliance/consent/status')
      .then((res) => {
        const items = res.data?.consents || [];
        const cc = items.find((c) => c.consent_type === 'cookies');
        setVisible(!cc?.accepted);
      })
      .catch(() => setVisible(true))
      .finally(() => setLoaded(true));
  }, []);

  const acceptAll = async () => {
    setSaving(true);
    try {
      await api.post('/api/compliance/consent/cookies/accept');
      setVisible(false);
    } catch {
      // Silently fail
    } finally {
      setSaving(false);
    }
  };

  const acceptEssential = async () => {
    setSaving(true);
    try {
      await api.post('/api/compliance/consent/cookies/accept');
      setVisible(false);
    } catch {
      // Silently fail
    } finally {
      setSaving(false);
    }
  };

  const saveCustom = async () => {
    setSaving(true);
    try {
      await api.post('/api/compliance/consent/cookies/accept');
      setVisible(false);
    } catch {
      // Silently fail
    } finally {
      setSaving(false);
    }
  };

  if (!visible || !loaded) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-[9999] p-4">
      <div className="max-w-4xl mx-auto bg-panel-card border border-panel-subtle rounded-xl shadow-2xl p-5">
        <div className="flex items-start gap-4">
          <div className="w-10 h-10 rounded-lg bg-brand/10 flex items-center justify-center shrink-0">
            <Cookie className="w-5 h-5 text-brand" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ink-primary">Cookie Consent</h3>
              <button
                onClick={() => setVisible(false)}
                className="p-1 rounded hover:bg-panel-hover text-ink-muted hover:text-ink-primary"
              >
                <X size={16} />
              </button>
            </div>
            <p className="text-xs text-ink-muted mt-1 leading-relaxed">
              We use cookies to enhance your experience, analyse site usage, and serve relevant
              content. By clicking "Accept All", you consent to all cookies. You can manage your
              preferences at any time.
            </p>

            {/* Expandable detail */}
            {showDetails && (
              <div className="mt-3 space-y-2 border-t border-panel-subtle pt-3">
                {COOKIE_CATEGORIES.map((cat) => (
                  <label key={cat.key} className="flex items-center gap-3 py-1">
                    <input
                      type="checkbox"
                      checked={prefs[cat.key]}
                      onChange={() => setPrefs((p) => ({ ...p, [cat.key]: !p[cat.key] }))}
                      className="w-3.5 h-3.5 rounded border-panel-subtle bg-panel-surface
                                 text-brand focus:ring-brand/50"
                    />
                    <div>
                      <span className="text-xs font-medium text-ink-primary">{cat.label}</span>
                      <p className="text-[10px] text-ink-muted">{cat.description}</p>
                    </div>
                  </label>
                ))}
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2 mt-3">
              <button
                onClick={acceptAll}
                disabled={saving}
                className="px-3 py-1.5 rounded-lg text-xs font-medium bg-brand hover:bg-brand-hover
                           text-white transition-colors disabled:opacity-50"
              >
                {saving ? 'Saving…' : 'Accept All'}
              </button>
              <button
                onClick={acceptEssential}
                disabled={saving}
                className="px-3 py-1.5 rounded-lg text-xs font-medium border border-panel-subtle
                           text-ink-primary hover:bg-panel-hover transition-colors disabled:opacity-50"
              >
                Essential Only
              </button>
              <button
                onClick={() => {
                  if (showDetails) saveCustom();
                  setShowDetails(!showDetails);
                }}
                disabled={saving}
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-brand hover:text-brand-hover
                           hover:bg-brand/5 transition-colors disabled:opacity-50"
              >
                {showDetails ? 'Save Preferences' : 'Customise'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
