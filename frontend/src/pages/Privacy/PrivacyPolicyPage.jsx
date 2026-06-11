import { useState, useEffect } from 'react';
import { Shield, ArrowLeft, CheckCircle, XCircle, Loader } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import api from '../../utils/api';

export default function PrivacyPolicyPage() {
  const navigate = useNavigate();
  const [policy, setPolicy] = useState(null);
  const [loading, setLoading] = useState(true);
  const [consenting, setConsenting] = useState(false);
  const [consented, setConsented] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .get('/api/compliance/consent/status')
      .then((res) => {
        const items = res.data?.consents || [];
        const pc = items.find((c) => c.consent_type === 'privacy_policy');
        setConsented(pc?.accepted || false);
      })
      .catch(() => setPolicy(null))
      .finally(() => setLoading(false));
  }, []);

  const accept = async () => {
    setConsenting(true);
    try {
      await api.post('/api/compliance/consent/privacy_policy/accept');
      setConsented(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to record consent.');
    } finally {
      setConsenting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader className="w-6 h-6 text-brand animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="p-2 rounded-lg hover:bg-panel-hover text-ink-muted hover:text-ink-primary transition-colors"
        >
          <ArrowLeft size={20} />
        </button>
        <div className="w-10 h-10 rounded-xl bg-brand/10 flex items-center justify-center">
          <Shield className="w-5 h-5 text-brand" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-ink-primary">Privacy Policy</h1>
          <p className="text-sm text-ink-muted">How we collect, use, and protect your personal data</p>
        </div>
      </div>

      {/* Consent Status */}
      {consented && (
        <div className="flex items-center gap-2 px-4 py-3 bg-ok/10 border border-ok/20 rounded-lg">
          <CheckCircle size={18} className="text-ok shrink-0" />
          <span className="text-sm text-ok">You have accepted the Privacy Policy.</span>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 px-4 py-3 bg-error/10 border border-error/20 rounded-lg">
          <XCircle size={18} className="text-error shrink-0" />
          <span className="text-sm text-error">{error}</span>
        </div>
      )}

      {/* Policy Content */}
      <div className="bg-panel-card border border-panel-subtle rounded-xl p-6 space-y-4">
        <h2 className="text-lg font-semibold text-ink-primary">1. Information We Collect</h2>
        <p className="text-sm text-ink-secondary leading-relaxed">
          We collect information you provide directly to us, including your name, email address,
          company details, billing information, and account credentials. We also automatically
          collect technical data such as IP addresses, browser types, and usage patterns to
          maintain and improve our services.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">2. How We Use Your Data</h2>
        <p className="text-sm text-ink-secondary leading-relaxed">
          Your personal data is used to provision and manage your hosting services, process
          transactions, send service-related communications, provide technical support, and
          comply with legal obligations. We may also use anonymised aggregate data for
          platform analytics and improvement.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">3. Legal Basis for Processing</h2>
        <p className="text-sm text-ink-secondary leading-relaxed">
          We process your personal data based on the following lawful grounds: performance of
          a contract (service delivery), legitimate interests (security and fraud prevention),
          legal obligations (data retention and regulatory compliance), and consent (marketing
          and optional analytics).
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">4. Data Sharing</h2>
        <p className="text-sm text-ink-secondary leading-relaxed">
          We do not sell your personal data. We may share data with trusted sub-processors
          (e.g., payment processors, cloud infrastructure providers) who are contractually
          bound to protect your data. We may also disclose data when required by law or to
          protect our legal rights.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">5. Data Retention</h2>
        <p className="text-sm text-ink-secondary leading-relaxed">
          We retain your personal data for as long as your account is active and for a period
          of up to 12 months thereafter, unless a longer retention period is required by law.
          You may request erasure of your data at any time by submitting a Data Subject Access
          Request.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">6. Your Rights</h2>
        <p className="text-sm text-ink-secondary leading-relaxed">
          Under applicable data protection laws, you have the right to: access your personal
          data, rectify inaccurate data, request erasure (right to be forgotten), restrict
          processing, data portability, and object to processing. To exercise these rights,
          visit the Data Subject Access Request page or contact our Data Protection Officer.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">7. Security Measures</h2>
        <p className="text-sm text-ink-secondary leading-relaxed">
          We implement appropriate technical and organisational measures to protect your
          personal data, including encryption at rest and in transit, access controls,
          regular security audits, and incident response procedures.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">8. Cookie Policy</h2>
        <p className="text-sm text-ink-secondary leading-relaxed">
          We use essential cookies required for platform functionality, analytics cookies to
          improve our services, and (with your consent) marketing cookies. You can manage your
          cookie preferences at any time via the Cookie Settings page.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">9. International Transfers</h2>
        <p className="text-sm text-ink-secondary leading-relaxed">
          Your data may be transferred to and processed in countries other than your own.
          We ensure appropriate safeguards are in place, including Standard Contractual
          Clauses and adequacy decisions where applicable.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">10. Contact</h2>
        <p className="text-sm text-ink-secondary leading-relaxed">
          If you have questions about this Privacy Policy or wish to exercise your data
          protection rights, please contact our Data Protection Officer at
          <a href="mailto:dpo@gnukontrolr.com" className="text-brand hover:underline ml-1">
            dpo@gnukontrolr.com
          </a>.
        </p>

        <p className="text-xs text-ink-muted pt-4 border-t border-panel-subtle">
          Version 1.0 &mdash; Last updated: January 2026
        </p>
      </div>

      {/* Accept Button */}
      <div className="flex justify-end">
        <button
          onClick={accept}
          disabled={consented || consenting}
          className={`px-6 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
            consented
              ? 'bg-ok/10 text-ok cursor-default'
              : 'bg-brand hover:bg-brand-hover text-white disabled:opacity-50'
          }`}
        >
          {consenting ? (
            <span className="flex items-center gap-2">
              <Loader size={16} className="animate-spin" />
              Recording Consent…
            </span>
          ) : consented ? (
            <span className="flex items-center gap-2">
              <CheckCircle size={16} />
              Consent Recorded
            </span>
          ) : (
            'Accept Privacy Policy'
          )}
        </button>
      </div>
    </div>
  );
}
