import { ArrowLeft, FileText, CheckCircle, Loader } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useState } from 'react';
import api from '../../utils/api';

export default function TermsOfServicePage() {
  const navigate = useNavigate();
  const [consenting, setConsenting] = useState(false);
  const [consented, setConsented] = useState(false);
  const [error, setError] = useState(null);

  const accept = async () => {
    setConsenting(true);
    try {
      await api.post('/api/compliance/consent/terms_of_service/accept');
      setConsented(true);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to record consent.');
    } finally {
      setConsenting(false);
    }
  };

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
          <FileText className="w-5 h-5 text-brand" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-ink-primary">Terms of Service</h1>
          <p className="text-sm text-ink-muted">Agreement governing use of the platform</p>
        </div>
      </div>

      {error && (
        <div className="px-4 py-3 bg-error/10 border border-error/20 rounded-lg text-sm text-error">
          {error}
        </div>
      )}

      <div className="bg-panel-card border border-panel-subtle rounded-xl p-6 space-y-4 text-sm text-ink-secondary leading-relaxed">
        <h2 className="text-lg font-semibold text-ink-primary">1. Acceptance of Terms</h2>
        <p>
          By accessing or using the GnuKontrolR platform ("the Service"), you agree to be bound
          by these Terms of Service. If you do not agree, you may not use the Service.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">2. Description of Service</h2>
        <p>
          The Service provides web hosting management, domain management, email services, database
          hosting, SSL certificate management, and related infrastructure services. We reserve the
          right to modify, suspend, or discontinue any aspect of the Service with reasonable notice.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">3. User Obligations</h2>
        <p>
          You are responsible for maintaining the confidentiality of your account credentials,
          for all activities that occur under your account, and for ensuring that your use of the
          Service complies with all applicable laws and regulations. You must not use the Service
          for any illegal or unauthorised purpose.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">4. Acceptable Use</h2>
        <p>
          You agree not to: (a) upload or distribute malware, viruses, or harmful code; (b)
          engage in phishing, spamming, or denial-of-service attacks; (c) host illegal content;
          (d) attempt to breach the security of the Service or other users' accounts; (e) use
          the Service in a way that exceeds reasonable resource limits.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">5. Service Level Agreement</h2>
        <p>
          We strive to maintain 99.9% uptime for the control panel and underlying infrastructure.
          Scheduled maintenance will be announced via the notification system. Credits may be
          available for qualifying downtime as outlined in your specific service plan.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">6. Fees and Payment</h2>
        <p>
          Service fees are billed according to the pricing terms of your selected plan. All fees
          are non-refundable unless otherwise specified. Late payments may result in service
          suspension. We may change fees with 30 days' notice.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">7. Termination</h2>
        <p>
          Either party may terminate this agreement at any time. Upon termination, your access to
          the Service will be revoked, and your data will be retained for 90 days before permanent
          deletion. We may terminate or suspend access immediately for breach of these terms.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">8. Limitation of Liability</h2>
        <p>
          To the maximum extent permitted by law, the Service is provided "as is" without warranty.
          We shall not be liable for any indirect, incidental, or consequential damages arising from
          your use of the Service. Our total liability is limited to the fees paid in the 12 months
          preceding the claim.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">9. Data Ownership</h2>
        <p>
          You retain all ownership rights to your data. We claim no intellectual property rights
          over the content you host on the Service. We may use anonymised aggregate data for
          platform improvement and marketing.
        </p>

        <h2 className="text-lg font-semibold text-ink-primary">10. Changes to Terms</h2>
        <p>
          We may update these terms at any time. Material changes will be communicated via email
          and in-platform notification. Continued use of the Service after changes constitutes
          acceptance of the updated terms.
        </p>

        <p className="text-xs text-ink-muted pt-4 border-t border-panel-subtle">
          Version 1.0 &mdash; Last updated: January 2026
        </p>
      </div>

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
            'Accept Terms of Service'
          )}
        </button>
      </div>
    </div>
  );
}
