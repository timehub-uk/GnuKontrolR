import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Eye, EyeOff } from 'lucide-react';

// ── Logo SVG ──────────────────────────────────────────────────────────────────
function Logo({ size = 48 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="lg-logo" x1="0" y1="0" x2="48" y2="48" gradientUnits="userSpaceOnUse">
          <stop stopColor="#6366f1"/>
          <stop offset="1" stopColor="#8b5cf6"/>
        </linearGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="2" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>
      {/* Background rounded rect */}
      <rect width="48" height="48" rx="13" fill="url(#lg-logo)"/>
      {/* Server rack rows */}
      <rect x="9" y="12" width="30" height="7" rx="2.5" fill="white" fillOpacity="0.92"/>
      <rect x="9" y="22" width="30" height="7" rx="2.5" fill="white" fillOpacity="0.55"/>
      <rect x="9" y="32" width="18" height="4" rx="2" fill="white" fillOpacity="0.25"/>
      {/* Status dots */}
      <circle cx="33" cy="15.5" r="2" fill="#4ade80" filter="url(#glow)"/>
      <circle cx="33" cy="25.5" r="2" fill="white" fillOpacity="0.4"/>
      {/* Network connector lines */}
      <line x1="11" y1="36" x2="15" y2="36" stroke="white" strokeOpacity="0.4" strokeWidth="1.5" strokeLinecap="round"/>
    </svg>
  );
}

// ── Repeating SVG background pattern ─────────────────────────────────────────
function BgPattern() {
  return (
    <svg
      className="absolute inset-0 w-full h-full"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <defs>
        <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
          {/* Grid lines */}
          <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(99,102,241,0.07)" strokeWidth="1"/>
        </pattern>
        <pattern id="dots" width="40" height="40" patternUnits="userSpaceOnUse">
          <circle cx="20" cy="20" r="1" fill="rgba(99,102,241,0.12)"/>
        </pattern>
        <pattern id="combined" width="40" height="40" patternUnits="userSpaceOnUse">
          <rect width="40" height="40" fill="url(#grid)"/>
          <rect width="40" height="40" fill="url(#dots)"/>
        </pattern>
        {/* Radial gradient mask — bright centre fading out */}
        <radialGradient id="fade" cx="50%" cy="50%" r="55%">
          <stop offset="0%"   stopColor="white" stopOpacity="0.06"/>
          <stop offset="60%"  stopColor="white" stopOpacity="0.025"/>
          <stop offset="100%" stopColor="white" stopOpacity="0"/>
        </radialGradient>
        {/* Diagonal accent lines */}
        <pattern id="diag" width="80" height="80" patternUnits="userSpaceOnUse" patternTransform="rotate(30)">
          <line x1="0" y1="0" x2="0" y2="80" stroke="rgba(139,92,246,0.04)" strokeWidth="1"/>
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#combined)"/>
      <rect width="100%" height="100%" fill="url(#diag)"/>
      <rect width="100%" height="100%" fill="url(#fade)"/>
    </svg>
  );
}

// ── Floating orb decorations ──────────────────────────────────────────────────
function Orbs() {
  return (
    <>
      {/* Top-left orb */}
      <div
        className="absolute top-0 left-0 w-[500px] h-[500px] rounded-full pointer-events-none"
        style={{
          background: 'radial-gradient(circle, rgba(99,102,241,0.08) 0%, transparent 65%)',
          transform: 'translate(-30%, -30%)',
        }}
      />
      {/* Bottom-right orb */}
      <div
        className="absolute bottom-0 right-0 w-[400px] h-[400px] rounded-full pointer-events-none"
        style={{
          background: 'radial-gradient(circle, rgba(139,92,246,0.07) 0%, transparent 65%)',
          transform: 'translate(25%, 25%)',
        }}
      />
    </>
  );
}

// ── Login page ────────────────────────────────────────────────────────────────
export default function LoginPage() {
  const { login }  = useAuth();
  const navigate   = useNavigate();
  const [form, setForm]   = useState({ username: '', password: '' });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [show, setShow]   = useState(false);

  const canSubmit = form.username.trim().length > 0 && form.password.length > 0;

  const submit = async e => {
    e.preventDefault();
    if (!canSubmit) return;
    setError('');
    setLoading(true);
    try {
      await login(form.username.trim(), form.password);
      navigate('/');
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 429) {
        setError(detail || 'Too many failed attempts. Please wait before trying again.');
      } else {
        setError(detail || 'Invalid username or password.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-panel-base flex items-center justify-center px-4 relative overflow-hidden">

      {/* Decorative background */}
      <BgPattern />
      <Orbs />

      {/* Login card */}
      <div className="relative w-full max-w-[380px] animate-slide-up">

        {/* Logo + brand */}
        <div className="flex flex-col items-center mb-8">
          <div style={{ filter: 'drop-shadow(0 0 20px rgba(99,102,241,0.35))' }}>
            <Logo size={52} />
          </div>
          <h1 className="mt-4 text-[22px] font-bold text-ink-primary tracking-tight">GnuKontrolR</h1>
          <p className="text-[13px] text-ink-muted mt-1">Hosting Control Panel</p>
        </div>

        {/* Card */}
        <div
          className="rounded-2xl p-7"
          style={{
            background: '#111113',
            border: '1px solid #1f1f23',
            boxShadow: '0 25px 60px rgba(0,0,0,0.5), 0 0 0 1px rgba(99,102,241,0.05)',
          }}
        >
          <p className="text-[13px] text-ink-muted text-center mb-6">Sign in to your account</p>

          <form onSubmit={submit} className="space-y-4" noValidate>
            {/* Username */}
            <div>
              <label className="block text-[11px] font-semibold text-ink-muted uppercase tracking-wider mb-1.5">
                Username
              </label>
              <input
                className="input"
                value={form.username}
                onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                placeholder="admin"
                autoComplete="username"
                autoFocus
                spellCheck={false}
              />
            </div>

            {/* Password */}
            <div>
              <label className="block text-[11px] font-semibold text-ink-muted uppercase tracking-wider mb-1.5">
                Password
              </label>
              <div className="relative">
                <input
                  className="input pr-10"
                  type={show ? 'text' : 'password'}
                  value={form.password}
                  onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                  placeholder="••••••••"
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShow(s => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-muted hover:text-ink-secondary transition-colors"
                  tabIndex={-1}
                  aria-label={show ? 'Hide password' : 'Show password'}
                >
                  {show ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="flex items-start gap-2 bg-bad/10 border border-bad/20 rounded-lg px-3 py-2.5 animate-fade-in">
                <svg className="w-3.5 h-3.5 text-bad-light flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd"/>
                </svg>
                <p className="text-[12px] text-bad-light leading-snug">{error}</p>
              </div>
            )}

            {/* Submit — only visible when both fields have content */}
            <div
              className="transition-all duration-200 overflow-hidden"
              style={{ maxHeight: canSubmit ? '60px' : '0', opacity: canSubmit ? 1 : 0 }}
            >
              <button
                type="submit"
                disabled={loading || !canSubmit}
                className="btn-primary w-full mt-1 py-2.5 text-[14px]"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                    </svg>
                    Signing in…
                  </span>
                ) : 'Sign in →'}
              </button>
            </div>
          </form>
        </div>

        {/* Footer */}
        <p className="text-center text-[11px] text-ink-muted mt-5">
          GnuKontrolR · Secure Hosting Control Panel
        </p>
      </div>
    </div>
  );
}
