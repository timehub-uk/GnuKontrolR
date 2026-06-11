import { useState, useEffect } from 'react';
import {
  Shield, Smartphone, Key, Plus, Trash2, CheckCircle,
  XCircle, Loader, AlertTriangle, Copy, Download,
} from 'lucide-react';
import { toast } from 'sonner';
import api from '../utils/api';

export default function MfaSetupPage() {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [enrolling, setEnrolling] = useState(false);
  const [enrollData, setEnrollData] = useState(null);   // { secret, uri, qrcode_b64, device_id }
  const [verifyCode, setVerifyCode] = useState('');
  const [deviceName, setDeviceName] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState(null);
  const [recoveryCodes, setRecoveryCodes] = useState(null); // shown after first verify

  const loadDevices = async () => {
    try {
      const res = await api.get('/api/mfa/devices');
      setDevices(res.data.devices || []);
    } catch {
      // No MFA devices yet
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadDevices(); }, []);

  const startEnroll = async () => {
    setEnrolling(true);
    setError(null);
    try {
      const res = await api.post('/api/mfa/enroll', { device_name: deviceName || 'Authenticator App' });
      setEnrollData(res.data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start enrollment.');
    }
  };

  const confirmEnroll = async () => {
    if (!verifyCode.trim() || !enrollData) return;
    setVerifying(true);
    setError(null);
    try {
      const res = await api.post('/api/mfa/verify', {
        device_id: enrollData.device_id,
        code: verifyCode.trim(),
      });
      toast.success('MFA device enrolled successfully');
      if (res.data?.recovery_codes?.length) {
        setRecoveryCodes(res.data.recovery_codes);
      } else {
        setEnrollData(null);
        setVerifyCode('');
        setDeviceName('');
        loadDevices();
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid code. Please try again.');
    } finally {
      setVerifying(false);
    }
  };

  const downloadRecoveryCodes = () => {
    if (!recoveryCodes) return;
    const text = [
      'GnuKontrolR - MFA Recovery Codes',
      '=================================',
      'Generated: ' + new Date().toISOString(),
      '',
      'Store these codes in a safe place. Each code can be used only once.',
      'If you lose access to your authenticator app, use one of these codes to log in.',
      '',
      ...recoveryCodes.map((c, i) => `${i + 1}. ${c}`),
      '',
      'After using a code, generate new ones from the MFA settings page.',
      '',
    ].join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'gnukontrolr-mfa-recovery-codes.txt';
    a.click();
    URL.revokeObjectURL(url);
  };

  const finishEnroll = () => {
    setEnrollData(null);
    setRecoveryCodes(null);
    setVerifyCode('');
    setDeviceName('');
    loadDevices();
  };

  const removeDevice = async (deviceId) => {
    if (!confirm('Remove this MFA device?')) return;
    try {
      await api.delete(`/api/mfa/devices/${deviceId}`);
      toast.success('Device removed');
      loadDevices();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to remove device.');
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
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-brand/10 flex items-center justify-center">
          <Shield className="w-5 h-5 text-brand" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-ink-primary">Multi-Factor Authentication</h1>
          <p className="text-sm text-ink-muted">Add an extra layer of security to your account</p>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 px-4 py-3 bg-error/10 border border-error/20 rounded-lg">
          <XCircle size={18} className="text-error shrink-0" />
          <span className="text-sm text-error">{error}</span>
        </div>
      )}

      {/* Existing Devices */}
      {devices.length > 0 && (
        <div className="bg-panel-card border border-panel-subtle rounded-xl p-4 space-y-3">
          <h2 className="text-sm font-semibold text-ink-primary">Registered Devices</h2>
          {devices.map((d) => (
            <div
              key={d.id}
              className="flex items-center justify-between p-3 rounded-lg bg-panel-surface border border-panel-subtle"
            >
              <div className="flex items-center gap-3">
                <Smartphone className="w-5 h-5 text-brand" />
                <div>
                  <span className="text-sm text-ink-primary">{d.device_name}</span>
                  <p className="text-xs text-ink-muted">
                    Added {new Date(d.created_at).toLocaleDateString()}
                    {d.last_used_at && ` · Last used ${new Date(d.last_used_at).toLocaleDateString()}`}
                  </p>
                </div>
              </div>
              <button
                onClick={() => removeDevice(d.id)}
                className="p-2 rounded-lg hover:bg-error/10 text-ink-muted hover:text-error transition-colors"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* No Devices */}
      {devices.length === 0 && !enrollData && (
        <div className="bg-panel-card border border-panel-subtle rounded-xl p-8 text-center">
          <Smartphone className="w-12 h-12 text-ink-muted mx-auto mb-3" />
          <h2 className="text-lg font-semibold text-ink-primary mb-1">No MFA Devices</h2>
          <p className="text-sm text-ink-muted mb-4">
            Add an authenticator app to secure your account with time-based one-time passwords.
          </p>
        </div>
      )}

      {/* Enrollment Form */}
      {!enrollData ? (
        <div className="bg-panel-card border border-panel-subtle rounded-xl p-5 space-y-4">
          <h2 className="text-sm font-semibold text-ink-primary">Add New Device</h2>
          <div>
            <label className="block text-xs text-ink-muted mb-1">Device Name (optional)</label>
            <input
              type="text"
              value={deviceName}
              onChange={(e) => setDeviceName(e.target.value)}
              placeholder="e.g., My Phone"
              className="w-full px-3 py-2 rounded-lg bg-panel-surface border border-panel-subtle
                         text-ink-primary placeholder-ink-muted text-sm
                         focus:outline-none focus:ring-2 focus:ring-brand/50"
            />
          </div>
          <button
            onClick={startEnroll}
            disabled={enrolling}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                       bg-brand hover:bg-brand-hover text-white transition-colors disabled:opacity-50"
          >
            {enrolling ? (
              <><Loader size={16} className="animate-spin" /> Preparing…</>
            ) : (
              <><Plus size={16} /> Add Device</>
            )}
          </button>
        </div>
      ) : (
        /* QR Code & Verification */
        <div className="bg-panel-card border border-panel-subtle rounded-xl p-6 space-y-5">
          <h2 className="text-sm font-semibold text-ink-primary">Scan QR Code</h2>
          <p className="text-xs text-ink-muted">
            Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.),
            then enter the 6-digit code below to verify.
          </p>

          {/* QR Code */}
          {enrollData.qrcode_b64 && (
            <div className="flex justify-center">
              <img
                src={`data:image/png;base64,${enrollData.qrcode_b64}`}
                alt="MFA QR Code"
                className="w-48 h-48 rounded-lg border border-panel-subtle"
              />
            </div>
          )}

          {/* Manual entry fallback */}
          {enrollData.secret && (
            <div className="bg-panel-surface border border-panel-subtle rounded-lg p-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-ink-muted">Secret Key (manual entry):</p>
                  <code className="text-sm font-mono text-ink-primary">{enrollData.secret}</code>
                </div>
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(enrollData.secret);
                    toast.success('Secret key copied');
                  }}
                  className="p-2 rounded-lg hover:bg-panel-hover text-ink-muted hover:text-ink-primary"
                >
                  <Copy size={16} />
                </button>
              </div>
            </div>
          )}

          {/* Verification Code */}
          <div className="space-y-2">
            <label className="block text-xs text-ink-muted">Verification Code</label>
            <input
              type="text"
              value={verifyCode}
              onChange={(e) => setVerifyCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="000000"
              maxLength={6}
              className="w-full max-w-[200px] px-3 py-2 rounded-lg bg-panel-surface border border-panel-subtle
                         text-ink-primary text-center text-2xl font-mono tracking-widest
                         focus:outline-none focus:ring-2 focus:ring-brand/50"
            />
          </div>

          <div className="flex gap-2">
            <button
              onClick={confirmEnroll}
              disabled={verifying || verifyCode.length !== 6}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                         bg-brand hover:bg-brand-hover text-white transition-colors disabled:opacity-50"
            >
              {verifying ? (
                <><Loader size={16} className="animate-spin" /> Verifying…</>
              ) : (
                <><CheckCircle size={16} /> Verify &amp; Enable</>
              )}
            </button>
            <button
              onClick={() => setEnrollData(null)}
              className="px-4 py-2 rounded-lg text-sm font-medium border border-panel-subtle
                         text-ink-muted hover:text-ink-primary hover:bg-panel-hover"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Recovery Codes Display */}
      {recoveryCodes && (
        <div className="bg-panel-card border border-amber-500/30 rounded-xl p-6 space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center">
              <Key className="w-5 h-5 text-amber-400" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-ink-primary">Recovery Codes</h2>
              <p className="text-xs text-ink-muted">
                Save these codes in a safe place. Each code can be used <strong>only once</strong> to
                access your account if you lose your authenticator device.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {recoveryCodes.map((code, i) => (
              <div
                key={i}
                className="px-3 py-2 rounded-lg bg-panel-surface border border-panel-subtle
                           font-mono text-sm text-ink-primary tracking-wide text-center"
              >
                {code.match(/.{1,4}/g).join('-')}
              </div>
            ))}
          </div>

          <div className="flex gap-2">
            <button
              onClick={downloadRecoveryCodes}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                         bg-brand hover:bg-brand-hover text-white transition-colors"
            >
              <Download size={16} />
              Download as .txt
            </button>
            <button
              onClick={() => {
                const text = recoveryCodes.join('\n');
                navigator.clipboard.writeText(text);
                toast.success('Recovery codes copied to clipboard');
              }}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                         border border-panel-subtle text-ink-primary hover:bg-panel-hover transition-colors"
            >
              <Copy size={16} />
              Copy All
            </button>
            <button
              onClick={finishEnroll}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                         bg-ok hover:bg-ok/80 text-white transition-colors ml-auto"
            >
              <CheckCircle size={16} />
              Done — Continue
            </button>
          </div>

          <div className="flex items-start gap-2 px-3 py-2 bg-amber-500/10 border border-amber-500/20 rounded-lg">
            <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />
            <p className="text-[11px] text-amber-300">
              <strong>Important:</strong> These codes will not be shown again. Download or copy them now.
              If you lose access to both your authenticator app and these recovery codes, you will be
              locked out of your account.
            </p>
          </div>
        </div>
      )}

      {/* Info Box */}
      <div className="flex items-start gap-3 px-4 py-3 bg-brand/5 border border-brand/10 rounded-lg">
        <AlertTriangle size={16} className="text-brand shrink-0 mt-0.5" />
        <div className="text-xs text-ink-muted leading-relaxed">
          <strong className="text-ink-primary">Tip:</strong> After enabling MFA, your next login will
          require both your password and a code from your authenticator app. Make sure you have access
          to your authenticator app before logging out.
        </div>
      </div>
    </div>
  );
}
