/**
 * MarketplacePage — one-click app installer + SFTP key management.
 *
 * Tabs:   CMS  |  Webmail  |  Analytics  |  Collaboration  |  Developer  |  Utilities  |  Tools  |  SFTP
 *
 * Install flow:
 *   1. Click "Install" on an app card
 *   2. Fill in domain, path, credentials (auto-generated, editable)
 *   3. Watch the live install log stream (polling every 2 s)
 *   4. Get the final credentials card once done
 *
 * SFTP flow:
 *   1. Select domain → Generate Keys
 *   2. Private key shown once with download button
 *   3. Connection card with per-client instructions (FileZilla / WinSCP / Cyberduck)
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../utils/api';

// ── Custom app logos (SVG) ─────────────────────────────────────────────────────

function Logo({ children, bg = '#1f2937', size = 44 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 44 44" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="44" height="44" rx="10" fill={bg} />
      {children}
    </svg>
  );
}

const APP_LOGOS = {
  wordpress: (
    <Logo bg="#21759b">
      <text x="22" y="30" textAnchor="middle" fontSize="22" fontWeight="800" fill="white" fontFamily="Georgia,serif">W</text>
    </Logo>
  ),
  joomla: (
    <Logo bg="#f4a623">
      {/* Joomla-style lightning bolt */}
      <path d="M16 10h8l-4 9h5l-9 15 2-10h-5z" fill="white" />
    </Logo>
  ),
  drupal: (
    <Logo bg="#0078b8">
      {/* Drupal drop */}
      <path d="M22 8 C22 8 14 16 14 23 a8 8 0 0 0 16 0 C30 16 22 8 22 8z" fill="white" />
      <circle cx="18.5" cy="22" r="2" fill="#0078b8" />
      <circle cx="25.5" cy="22" r="2" fill="#0078b8" />
    </Logo>
  ),
  grav: (
    <Logo bg="#1e293b">
      {/* Spiral / planet rings */}
      <circle cx="22" cy="22" r="7" stroke="#a3e635" strokeWidth="2" fill="none"/>
      <ellipse cx="22" cy="22" rx="14" ry="5" stroke="#a3e635" strokeWidth="1.5" fill="none"/>
      <circle cx="22" cy="22" r="3" fill="#a3e635"/>
    </Logo>
  ),
  roundcube: (
    <Logo bg="#3c8a2e">
      {/* Envelope */}
      <rect x="10" y="14" width="24" height="17" rx="2" stroke="white" strokeWidth="1.5" fill="none"/>
      <path d="M10 16l12 9 12-9" stroke="white" strokeWidth="1.5" fill="none"/>
      {/* Cube corner accent */}
      <rect x="27" y="26" width="8" height="8" rx="1" fill="white" opacity="0.8"/>
    </Logo>
  ),
  snappymail: (
    <Logo bg="#0ea5e9">
      {/* Lightning in envelope */}
      <rect x="9" y="13" width="26" height="18" rx="2" stroke="white" strokeWidth="1.5" fill="none"/>
      <path d="M9 16l13 9 13-9" stroke="white" strokeWidth="1.5" fill="none"/>
      <path d="M22 15l-3 7h4l-3 7" stroke="#fde047" strokeWidth="1.8" strokeLinecap="round"/>
    </Logo>
  ),
  phpmyadmin: (
    <Logo bg="#f97316">
      {/* Database cylinder */}
      <ellipse cx="22" cy="15" rx="10" ry="3.5" fill="white" opacity="0.9"/>
      <rect x="12" y="15" width="20" height="14" fill="white" opacity="0.15"/>
      <ellipse cx="22" cy="29" rx="10" ry="3.5" fill="white" opacity="0.9"/>
      <line x1="12" y1="15" x2="12" y2="29" stroke="white" opacity="0.9" strokeWidth="1.5"/>
      <line x1="32" y1="15" x2="32" y2="29" stroke="white" opacity="0.9" strokeWidth="1.5"/>
      <text x="22" y="24" textAnchor="middle" fontSize="9" fontWeight="700" fill="#f97316" fontFamily="monospace">SQL</text>
    </Logo>
  ),
  adminer: (
    <Logo bg="#6366f1">
      <text x="22" y="32" textAnchor="middle" fontSize="26" fontWeight="900" fill="white" fontFamily="monospace">A</text>
    </Logo>
  ),
  // ── New logos ───────────────────────────────────────────────────────────────
  ghost: (
    <Logo bg="#15171a">
      {/* Ghost: oval body, eyes, wavy scalloped bottom */}
      <ellipse cx="22" cy="19" rx="10" ry="11" fill="white"/>
      <rect x="12" y="19" width="20" height="10" fill="white"/>
      {/* Scalloped bottom */}
      <path d="M12 29 Q15 34 18 29 Q21 34 24 29 Q27 34 30 29 Q31 27 32 26 L12 26 Z" fill="#15171a"/>
      <path d="M12 29 Q15 25 18 29 Q21 25 24 29 Q27 25 30 29 L30 32 Q27 37 24 32 Q21 37 18 32 Q15 37 12 32 Z" fill="white"/>
      {/* Eyes */}
      <circle cx="18" cy="18" r="1.8" fill="#15171a"/>
      <circle cx="26" cy="18" r="1.8" fill="#15171a"/>
    </Logo>
  ),
  october: (
    <Logo bg="#0d7470">
      {/* Leaf outline with center vein */}
      <path d="M22 9 C14 12 11 20 13 30 C17 26 25 24 31 18 C28 13 22 9 22 9Z" stroke="white" strokeWidth="1.5" fill="none" strokeLinejoin="round"/>
      <path d="M22 9 C20 18 16 25 13 30" stroke="white" strokeWidth="1.2" fill="none"/>
    </Logo>
  ),
  concrete: (
    <Logo bg="#1e3a5f">
      {/* Stylized C made of 3 horizontal stacked rectangles (concrete blocks) */}
      <rect x="13" y="12" width="16" height="5" rx="1" fill="white"/>
      <rect x="13" y="19.5" width="10" height="5" rx="1" fill="white"/>
      <rect x="13" y="27" width="16" height="5" rx="1" fill="white"/>
    </Logo>
  ),
  typo3: (
    <Logo bg="#f49700">
      {/* Bold T3 text */}
      <text x="22" y="31" textAnchor="middle" fontSize="18" fontWeight="800" fill="white" fontFamily="Arial,sans-serif">T3</text>
    </Logo>
  ),
  strapi: (
    <Logo bg="#4945ff">
      {/* S-arrow: S shape with right-pointing arrow tip */}
      <path d="M27 13 C27 13 18 13 16 17 C14 21 22 22 22 22 C22 22 29 23 28 27 C27 31 18 31 18 31" stroke="white" strokeWidth="2.5" fill="none" strokeLinecap="round"/>
      <path d="M25 28 L29 31 L25 34" stroke="white" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
    </Logo>
  ),
  matomo: (
    <Logo bg="#3152a0">
      {/* Bar chart: 3 rising bars + small eye dot at top right */}
      <rect x="10" y="26" width="6" height="8" rx="1" fill="white"/>
      <rect x="19" y="20" width="6" height="14" rx="1" fill="white"/>
      <rect x="28" y="14" width="6" height="20" rx="1" fill="white"/>
      <circle cx="32" cy="11" r="3" fill="white"/>
      <circle cx="32" cy="11" r="1.2" fill="#3152a0"/>
    </Logo>
  ),
  umami: (
    <Logo bg="#1f2937">
      {/* Clean u letterform */}
      <text x="22" y="33" textAnchor="middle" fontSize="22" fontWeight="700" fill="white" fontFamily="Georgia,serif">u</text>
    </Logo>
  ),
  freshrss: (
    <Logo bg="#ea6400">
      {/* RSS icon: dot at bottom-left, two expanding arcs */}
      <circle cx="13" cy="31" r="2.5" fill="white"/>
      <path d="M13 24 A10 10 0 0 1 20 31" stroke="white" strokeWidth="2.2" fill="none" strokeLinecap="round"/>
      <path d="M13 17 A17 17 0 0 1 30 31" stroke="white" strokeWidth="2.2" fill="none" strokeLinecap="round"/>
    </Logo>
  ),
  nextcloud: (
    <Logo bg="#0082c9">
      {/* Cloud outline with flat bottom */}
      <path d="M14 28 C10 28 8 25 8 22 C8 19 10 17 13 17 C13 13 16 11 20 11 C23 11 26 13 27 16 C30 16 34 18 34 22 C34 25 31 28 28 28 Z" stroke="white" strokeWidth="1.8" fill="none"/>
    </Logo>
  ),
  bookstack: (
    <Logo bg="#c47a2b">
      {/* Stacked book spines — 3 rectangles at slight angles */}
      <rect x="10" y="28" width="24" height="5" rx="1" fill="white"/>
      <rect x="11" y="22" width="22" height="5" rx="1" fill="white" opacity="0.85"/>
      <rect x="12" y="16" width="20" height="5" rx="1" fill="white" opacity="0.7"/>
    </Logo>
  ),
  wikijs: (
    <Logo bg="#1976d2">
      {/* W shape */}
      <path d="M9 14 L14 32 L22 20 L30 32 L35 14" stroke="white" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round"/>
      {/* Small gear teeth around bottom edge */}
      <path d="M14 34 L16 32 M22 36 L22 33 M30 34 L28 32" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
    </Logo>
  ),
  gitea: (
    <Logo bg="#609926">
      {/* Tea cup with cat ear on rim */}
      <path d="M12 20 Q12 32 22 32 Q32 32 32 20 Z" stroke="white" strokeWidth="1.5" fill="none"/>
      <path d="M12 20 L32 20" stroke="white" strokeWidth="1.5"/>
      {/* Handle */}
      <path d="M32 22 Q38 22 38 26 Q38 30 32 30" stroke="white" strokeWidth="1.5" fill="none"/>
      {/* Cat ears */}
      <path d="M16 20 L14 14 L19 18" stroke="white" strokeWidth="1.2" fill="none" strokeLinejoin="round"/>
      <path d="M28 20 L30 14 L25 18" stroke="white" strokeWidth="1.2" fill="none" strokeLinejoin="round"/>
    </Logo>
  ),
  codeserver: (
    <Logo bg="#0066b8">
      {/* Curly braces { } with cursor underscore */}
      <text x="22" y="28" textAnchor="middle" fontSize="16" fontWeight="700" fill="white" fontFamily="monospace">{"{ }"}</text>
      <rect x="19" y="30" width="6" height="2" rx="1" fill="white" opacity="0.8"/>
    </Logo>
  ),
  n8n: (
    <Logo bg="#ea580c">
      {/* 3-node workflow: 3 circles connected by lines */}
      <circle cx="10" cy="22" r="4" fill="white"/>
      <circle cx="22" cy="22" r="4" fill="white"/>
      <circle cx="34" cy="22" r="4" fill="white"/>
      <line x1="14" y1="22" x2="18" y2="22" stroke="white" strokeWidth="2"/>
      <line x1="26" y1="22" x2="30" y2="22" stroke="white" strokeWidth="2"/>
    </Logo>
  ),
  nodered: (
    <Logo bg="#8f0000">
      {/* Filled circle (Node-RED dot) with small flow lines */}
      <circle cx="22" cy="20" r="7" fill="white"/>
      <path d="M10 30 Q16 26 22 28 Q28 30 34 26" stroke="white" strokeWidth="1.5" fill="none" strokeLinecap="round"/>
    </Logo>
  ),
  filebrowser: (
    <Logo bg="#0ea5e9">
      {/* Folder outline with up-arrow on tab */}
      <path d="M10 18 L10 33 L34 33 L34 18 L22 18 L19 14 L10 14 Z" stroke="white" strokeWidth="1.5" fill="none" strokeLinejoin="round"/>
      {/* Up arrow */}
      <path d="M22 22 L22 29 M19 25 L22 22 L25 25" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </Logo>
  ),
  uptime: (
    <Logo bg="#3ba55d">
      {/* Monitor/screen outline with small bear face inside */}
      <rect x="9" y="12" width="26" height="18" rx="2" stroke="white" strokeWidth="1.5" fill="none"/>
      <line x1="18" y1="30" x2="16" y2="34" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
      <line x1="26" y1="30" x2="28" y2="34" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
      {/* Bear face: eyes */}
      <circle cx="18" cy="21" r="1.5" fill="white"/>
      <circle cx="26" cy="21" r="1.5" fill="white"/>
      {/* Nose */}
      <circle cx="22" cy="24" r="1" fill="white" opacity="0.7"/>
    </Logo>
  ),
  vaultwarden: (
    <Logo bg="#175ddc">
      {/* Shield outline with key silhouette */}
      <path d="M22 10 L32 14 L32 23 C32 29 27 33 22 35 C17 33 12 29 12 23 L12 14 Z" stroke="white" strokeWidth="1.5" fill="none" strokeLinejoin="round"/>
      {/* Key */}
      <circle cx="22" cy="22" r="4" stroke="white" strokeWidth="1.5" fill="none"/>
      <path d="M26 22 L31 22 M29 22 L29 25" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
    </Logo>
  ),
  invoiceninja: (
    <Logo bg="#1d7c5c">
      {/* Invoice/document outline with 3 horizontal lines */}
      <rect x="12" y="9" width="20" height="26" rx="2" stroke="white" strokeWidth="1.5" fill="none"/>
      <line x1="16" y1="17" x2="28" y2="17" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
      <line x1="16" y1="22" x2="28" y2="22" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
      <line x1="16" y1="27" x2="23" y2="27" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
    </Logo>
  ),
  symfony: (
    <Logo bg="#1a1a2e">
      {/* Symfony S-knot mark */}
      <path d="M28 14c-1.5-1.8-3.5-2.8-5.5-2.8-3.5 0-6 2.5-6 5.5 0 2.5 1.5 4 4 5.5 2 1.2 3 2 3 3.5 0 1.5-1.2 2.5-2.8 2.5-1.5 0-2.8-.7-3.8-1.8l-1.5 2.2C17 30.3 19 31.5 21.5 31.5c3.8 0 6.5-2.5 6.5-6 0-2.8-1.8-4.5-4.2-6-2-1.2-2.8-2-2.8-3.2 0-1.2 1-2 2.5-2 1.2 0 2.2.5 3 1.5L28 14z" fill="white"/>
    </Logo>
  ),
  laravel: (
    <Logo bg="#f9322c">
      {/* Laravel L letter */}
      <text x="22" y="31" textAnchor="middle" fontSize="24" fontWeight="700" fill="white" fontFamily="Georgia,serif">L</text>
    </Logo>
  ),
  codeigniter: (
    <Logo bg="#ef4444">
      {/* CodeIgniter flame */}
      <path d="M22 10c0 0-2 4-2 8 0 1.5.5 3 1.5 3.5-0.5-1.5 0-3.5 1.5-4.5 0 3 2 5 2 8 0 3.5-2.5 6-5 6-3.5 0-6-2.5-6-6 0-5 4-9 5-12 .5 1 1 2 1 3.5 1-2 2-4.5 2-6.5z" fill="white"/>
    </Logo>
  ),
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function randPass(n = 20) {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$';
  return Array.from(crypto.getRandomValues(new Uint8Array(n)))
    .map(b => chars[b % chars.length]).join('');
}

function randIdent(prefix, n = 8) {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  const suffix = Array.from(crypto.getRandomValues(new Uint8Array(n)))
    .map(b => chars[b % chars.length]).join('');
  return `${prefix}_${suffix}`;
}

// ── Small UI atoms ─────────────────────────────────────────────────────────────

function Badge({ children, color = 'gray' }) {
  const map = {
    gray: 'bg-panel-700 text-gray-400',
    blue: 'bg-blue-900/30 text-blue-300',
    green: 'bg-green-900/30 text-green-400',
    orange: 'bg-orange-900/30 text-orange-300',
    purple: 'bg-purple-900/30 text-purple-300',
  };
  return (
    <span className={`text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ${map[color] ?? map.gray}`}>
      {children}
    </span>
  );
}

function Field({ label, value, onChange, type = 'text', mono = false, readOnly = false, help }) {
  const [show, setShow] = useState(false);
  const isPass = type === 'password';
  return (
    <div className="space-y-1">
      <label className="text-xs text-gray-500">{label}</label>
      <div className="relative flex">
        <input
          type={isPass && !show ? 'password' : 'text'}
          value={value}
          onChange={e => onChange?.(e.target.value)}
          readOnly={readOnly}
          className={`input flex-1 text-sm ${mono ? 'font-mono' : ''} ${readOnly ? 'opacity-60' : ''}`}
        />
        {isPass && (
          <button type="button" onClick={() => setShow(s => !s)}
            className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs">
            {show ? 'hide' : 'show'}
          </button>
        )}
      </div>
      {help && <p className="text-[10px] text-gray-600">{help}</p>}
    </div>
  );
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); }}
      className="text-xs px-2 py-1 rounded bg-panel-700 border border-panel-600 hover:border-panel-500 text-gray-400 hover:text-white transition-colors"
    >
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  );
}

// ── Install modal ─────────────────────────────────────────────────────────────

function InstallModal({ app, domains, onClose, onDone }) {
  const [domain,      setDomain]      = useState(domains[0] ?? '');
  const [installPath, setInstallPath] = useState('/');
  const [siteTitle,   setSiteTitle]   = useState('My Site');
  const [adminUser,   setAdminUser]   = useState('admin');
  const [adminPass,   setAdminPass]   = useState(() => randPass(16));
  const [adminEmail,  setAdminEmail]  = useState('');
  const [dbName,      setDbName]      = useState(() => randIdent(app.id.slice(0,4)));
  const [dbUser,      setDbUser]      = useState(() => randIdent('db'));
  const [dbPass,      setDbPass]      = useState(() => randPass(24));

  const [phase,      setPhase]      = useState('form');  // form | progress | done | error
  const [messages,   setMessages]   = useState([]);
  const [jobId,      setJobId]      = useState(null);
  const [result,     setResult]     = useState(null);
  const [generated,  setGenerated]  = useState(null);
  const [err,        setErr]        = useState('');
  const pollRef = useRef(null);
  const logRef  = useRef(null);

  const stopPoll = () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [messages]);

  useEffect(() => () => stopPoll(), []);

  async function startInstall() {
    setPhase('progress');
    setMessages([`Starting ${app.name} installation…`]);
    try {
      const r = await api.post('/api/marketplace/install', {
        domain,
        app_id: app.id,
        install_path: installPath,
        site_title:  siteTitle,
        admin_user:  adminUser,
        admin_pass:  adminPass,
        admin_email: adminEmail || `admin@${domain}`,
        db_name:     dbName,
        db_user:     dbUser,
        db_pass:     dbPass,
      });
      const jid = r.data.job_id;
      setJobId(jid);
      setGenerated(r.data.generated ?? null);

      pollRef.current = setInterval(async () => {
        try {
          const s = await api.get(`/api/marketplace/install/status/${domain}/${jid}`);
          setMessages(s.data.messages ?? []);
          if (s.data.status === 'done') {
            stopPoll(); setPhase('done'); setResult(s.data.result);
          } else if (s.data.status === 'error') {
            stopPoll(); setPhase('error'); setErr(s.data.error ?? 'Installation failed');
          }
        } catch { /* keep polling */ }
      }, 2000);
    } catch (e) {
      setPhase('error');
      setErr(e.response?.data?.detail ?? 'Could not start installation');
    }
  }

  const needsDb = app.requires_db;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60" style={{ backdropFilter: 'blur(6px)' }} />
      <div className="relative bg-panel-800 border border-panel-600 rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto"
           onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div className="flex items-center gap-3 p-5 border-b border-panel-700">
          {APP_LOGOS[app.id]}
          <div>
            <h2 className="font-bold text-white text-lg">Install {app.name}</h2>
            <p className="text-xs text-gray-500">{app.version}</p>
          </div>
          <button onClick={onClose} className="ml-auto text-gray-500 hover:text-white text-xl leading-none">×</button>
        </div>

        <div className="p-5 space-y-5">

          {/* ── FORM phase ─────────────────────────────────────────────── */}
          {phase === 'form' && (<>
            <div className="space-y-1">
              <label className="text-xs text-gray-500">Domain</label>
              <select className="input w-full text-sm" value={domain} onChange={e => setDomain(e.target.value)}>
                {domains.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
            </div>

            <Field label="Install path (/ = domain root, or e.g. /blog)"
              value={installPath} onChange={setInstallPath}
              help="Leave as / to install at the domain root." />

            {(app.id === 'wordpress' || app.id === 'joomla' || app.id === 'drupal' || app.id === 'roundcube') && (
              <Field label="Site title" value={siteTitle} onChange={setSiteTitle} />
            )}

            {(app.id === 'wordpress') && (<>
              <Field label="Admin username" value={adminUser} onChange={setAdminUser} />
              <Field label="Admin password" value={adminPass} onChange={setAdminPass} type="password" mono />
              <Field label="Admin email" value={adminEmail} onChange={setAdminEmail}
                help="Leave blank to use admin@yourdomain" />
            </>)}

            {needsDb && (
              <div className="rounded-xl border border-panel-600 p-4 space-y-3">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Database (auto-configured)</p>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="DB name"     value={dbName} onChange={setDbName} mono />
                  <Field label="DB user"     value={dbUser} onChange={setDbUser} mono />
                </div>
                <Field label="DB password" value={dbPass} onChange={setDbPass} type="password" mono
                  help="A dedicated database user is created with access only to this database." />
              </div>
            )}

            <div className="flex gap-3 pt-1">
              <button onClick={startInstall}
                className="flex-1 bg-brand-600 hover:bg-brand-500 text-white font-semibold text-sm px-5 py-2.5 rounded-xl transition-colors">
                Install {app.name} →
              </button>
              <button onClick={onClose}
                className="px-5 py-2.5 rounded-xl bg-panel-700 border border-panel-600 text-gray-400 hover:text-white text-sm transition-colors">
                Cancel
              </button>
            </div>
          </>)}

          {/* ── PROGRESS phase ─────────────────────────────────────────── */}
          {phase === 'progress' && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-brand-400 animate-pulse" />
                <span className="text-sm text-gray-300">Installing {app.name}…</span>
              </div>
              <div ref={logRef}
                className="font-mono text-xs text-green-300 bg-black/60 rounded-xl p-3 h-56 overflow-y-auto space-y-0.5 border border-panel-700">
                {messages.map((m, i) => <div key={i}>{'> '}{m}</div>)}
              </div>
            </div>
          )}

          {/* ── DONE phase ──────────────────────────────────────────────── */}
          {phase === 'done' && (<>
            <div className="flex items-center gap-2 text-green-400 text-sm font-semibold">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>
              {app.name} installed successfully
            </div>

            {/* Credentials card */}
            <div className="rounded-xl border border-panel-600 bg-panel-700/40 divide-y divide-panel-600 text-sm">
              {result?.url && (
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-gray-500 text-xs w-28">Site URL</span>
                  <span className="font-mono text-brand-300 text-xs">{result.url}</span>
                  <CopyButton text={result.url} />
                </div>
              )}
              {result?.admin_url && (
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-gray-500 text-xs w-28">Admin URL</span>
                  <span className="font-mono text-brand-300 text-xs">{result.admin_url}</span>
                  <CopyButton text={result.admin_url} />
                </div>
              )}
              {result?.note && (
                <div className="flex items-start gap-2 px-4 py-3">
                  <span className="text-gray-500 text-xs w-28 shrink-0">Note</span>
                  <span className="font-mono text-yellow-300 text-xs">{result.note}</span>
                </div>
              )}
              {result?.admin_token && (
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-gray-500 text-xs w-28">Admin token</span>
                  <span className="font-mono text-yellow-300 text-xs truncate max-w-[180px]">{result.admin_token}</span>
                  <CopyButton text={result.admin_token} />
                </div>
              )}
              {adminUser && (
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-gray-500 text-xs w-28">Admin user</span>
                  <span className="font-mono text-white text-xs">{adminUser}</span>
                  <CopyButton text={adminUser} />
                </div>
              )}
              <div className="flex items-center justify-between px-4 py-3">
                <span className="text-gray-500 text-xs w-28">Admin pass</span>
                <span className="font-mono text-yellow-300 text-xs">{generated?.admin_pass ?? adminPass}</span>
                <CopyButton text={generated?.admin_pass ?? adminPass} />
              </div>
              {needsDb && (<>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-gray-500 text-xs w-28">DB name</span>
                  <span className="font-mono text-white text-xs">{generated?.db_name ?? dbName}</span>
                  <CopyButton text={generated?.db_name ?? dbName} />
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-gray-500 text-xs w-28">DB user</span>
                  <span className="font-mono text-white text-xs">{generated?.db_user ?? dbUser}</span>
                  <CopyButton text={generated?.db_user ?? dbUser} />
                </div>
                <div className="flex items-center justify-between px-4 py-3">
                  <span className="text-gray-500 text-xs w-28">DB password</span>
                  <span className="font-mono text-yellow-300 text-xs">{generated?.db_pass ?? dbPass}</span>
                  <CopyButton text={generated?.db_pass ?? dbPass} />
                </div>
              </>)}
            </div>

            <p className="text-xs text-orange-400">
              ⚠ Save these credentials now — passwords cannot be retrieved again.
            </p>

            <div className="flex gap-3">
              {result?.url && (
                <a href={result.url} target="_blank" rel="noreferrer"
                  className="flex-1 text-center bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium px-4 py-2.5 rounded-xl transition-colors">
                  Visit site →
                </a>
              )}
              <button onClick={onClose}
                className="px-5 py-2.5 rounded-xl bg-panel-700 border border-panel-600 text-gray-400 hover:text-white text-sm transition-colors">
                Close
              </button>
            </div>
          </>)}

          {/* ── ERROR phase ─────────────────────────────────────────────── */}
          {phase === 'error' && (<>
            <div className="text-red-400 text-sm flex items-center gap-2">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
              Installation failed
            </div>
            <div className="font-mono text-xs text-red-300 bg-black/60 rounded-xl p-3 border border-red-900/40">{err}</div>
            <button onClick={onClose}
              className="w-full py-2.5 rounded-xl bg-panel-700 border border-panel-600 text-gray-400 hover:text-white text-sm transition-colors">
              Close
            </button>
          </>)}

        </div>
      </div>
    </div>
  );
}

// ── App card ──────────────────────────────────────────────────────────────────

function AppCard({ app, onInstall }) {
  const catColor = {
    cms: 'blue', webmail: 'green', tools: 'purple',
    analytics: 'orange', collaboration: 'blue', developer: 'purple', utilities: 'green',
  };
  return (
    <div className={`rounded-2xl border bg-gradient-to-br p-4 flex flex-col gap-3 ${app.color}`}>
      <div className="flex items-start gap-3">
        {APP_LOGOS[app.id] ?? <div className="w-11 h-11 rounded-xl bg-panel-700" />}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-white text-sm">{app.name}</span>
            <Badge color={catColor[app.category]}>{app.category}</Badge>
            <span className="text-[10px] text-gray-500">{app.version}</span>
          </div>
          <div className="flex gap-2 mt-1">
            <span className="text-[10px] text-gray-600">💾 {app.disk}</span>
            <span className="text-[10px] text-gray-600">🐘 {app.language}</span>
          </div>
        </div>
      </div>
      <p className="text-xs text-gray-400 leading-relaxed flex-1">{app.description}</p>
      <button
        onClick={() => onInstall(app)}
        className="w-full bg-panel-700/80 hover:bg-panel-700 border border-panel-500 hover:border-panel-400 text-white text-xs font-medium py-2 rounded-xl transition-colors"
      >
        Install {app.name}
      </button>
    </div>
  );
}

// ── SFTP tab ──────────────────────────────────────────────────────────────────

function SftpTab({ domains }) {
  const [domain,     setDomain]     = useState(domains[0] ?? '');
  const [info,       setInfo]       = useState(null);  // existing config
  const [key,        setKey]        = useState('');    // private key (shown once)
  const [busy,       setBusy]       = useState(false);
  const [err,        setErr]        = useState('');
  const [client,     setClient]     = useState('filezilla');

  useEffect(() => {
    if (!domain) return;
    setInfo(null); setKey('');
    api.get(`/api/container/${domain}/sftp/info`)
      .then(r => r.data.configured ? setInfo(r.data) : setInfo(null))
      .catch(() => setInfo(null));
  }, [domain]);

  async function generate() {
    setBusy(true); setErr(''); setKey('');
    try {
      const r = await api.post(`/api/container/${domain}/sftp/create`);
      setKey(r.data.private_key);
      setInfo(r.data.info);
    } catch (e) {
      setErr(e.response?.data?.detail ?? 'Failed to generate SFTP credentials');
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    if (!confirm(`Revoke SFTP access for ${domain}? This cannot be undone.`)) return;
    await api.delete(`/api/container/${domain}/sftp/revoke`);
    setInfo(null); setKey('');
  }

  function downloadKey() {
    const blob = new Blob([key], { type: 'text/plain' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `sftp_${domain}_id_ed25519.pem`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const CLIENT_INSTRUCTIONS = {
    filezilla: {
      name: 'FileZilla',
      steps: info ? [
        `Open FileZilla → File → Site Manager → New Site`,
        `Protocol: SFTP – SSH File Transfer Protocol`,
        `Host: ${info.host}`,
        `Port: ${info.port}`,
        `Logon Type: Key file`,
        `User: ${info.user}`,
        `Key file: Browse to the downloaded .pem file`,
        `Click Connect`,
      ] : [],
    },
    winscp: {
      name: 'WinSCP',
      steps: info ? [
        `Open WinSCP → New Session`,
        `File protocol: SFTP`,
        `Host name: ${info.host}`,
        `Port number: ${info.port}`,
        `User name: ${info.user}`,
        `Advanced → SSH → Authentication → Private key file → select the downloaded .pem (WinSCP will convert it to .ppk)`,
        `Click Login`,
      ] : [],
    },
    cyberduck: {
      name: 'Cyberduck',
      steps: info ? [
        `Open Cyberduck → Open Connection`,
        `Protocol: SFTP (SSH File Transfer Protocol)`,
        `Server: ${info.host}`,
        `Port: ${info.port}`,
        `Username: ${info.user}`,
        `SSH Private Key: select the downloaded .pem file`,
        `Click Connect`,
      ] : [],
    },
    terminal: {
      name: 'Terminal (ssh/sftp)',
      steps: info ? [
        `Save the downloaded key: chmod 600 ~/Downloads/sftp_${domain}_id_ed25519.pem`,
        `Connect: sftp -i ~/Downloads/sftp_${domain}_id_ed25519.pem -P ${info.port} ${info.user}@${info.host}`,
        `Or use rsync: rsync -avz -e "ssh -i ~/Downloads/sftp_${domain}_id_ed25519.pem -p ${info.port}" ./local_dir/ ${info.user}@${info.host}:/`,
      ] : [],
    },
  };

  return (
    <div className="space-y-5">
      {/* Domain selector */}
      <div className="card flex items-center gap-4">
        <label className="text-sm text-gray-400 shrink-0">Domain</label>
        <select className="input flex-1" value={domain} onChange={e => setDomain(e.target.value)}>
          {domains.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
        {info && (
          <button onClick={revoke} className="text-xs text-red-400 hover:text-red-300 px-3 py-1.5 rounded-lg border border-red-900/40 hover:border-red-700 transition-colors">
            Revoke access
          </button>
        )}
      </div>

      {err && <div className="card border-red-800 text-red-400 text-sm">{err}</div>}

      {/* Connection info bar */}
      {info && (
        <div className="card space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">SFTP Connection Details</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Host',     value: info.host },
              { label: 'Port',     value: info.port },
              { label: 'User',     value: info.user },
              { label: 'Protocol', value: 'SFTP / SSH (Ed25519 key)' },
            ].map(({ label, value }) => (
              <div key={label} className="bg-panel-700/40 rounded-xl p-3">
                <p className="text-[10px] text-gray-500 mb-0.5">{label}</p>
                <div className="flex items-center gap-1">
                  <span className="font-mono text-xs text-white truncate">{value}</span>
                  <CopyButton text={value} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Generate / rotate keys */}
      {!key && (
        <div className="card space-y-3">
          <h3 className="text-sm font-semibold text-white">
            {info ? 'Rotate SFTP Keys' : 'Set up SFTP Access'}
          </h3>
          <p className="text-xs text-gray-500">
            {info
              ? 'Generating new keys will invalidate the previous private key immediately.'
              : 'Creates an SFTP-only user locked to the webroot. Authentication uses an Ed25519 key pair — no password login allowed.'}
          </p>
          <button onClick={generate} disabled={busy || !domain}
            className="bg-brand-600 hover:bg-brand-500 text-white text-sm font-medium px-5 py-2.5 rounded-xl transition-colors disabled:opacity-50">
            {busy ? 'Generating…' : info ? 'Rotate keys' : 'Generate SFTP keys'}
          </button>
        </div>
      )}

      {/* Private key — shown once */}
      {key && (
        <div className="card border-yellow-800/40 space-y-3">
          <div className="flex items-center gap-2">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <span className="text-yellow-400 text-sm font-semibold">Download your private key now — it will not be shown again</span>
          </div>
          <pre className="font-mono text-xs text-green-300 bg-black/60 rounded-xl p-3 overflow-x-auto border border-panel-700 max-h-40">
            {key.slice(0, 200)}…
          </pre>
          <button onClick={downloadKey}
            className="bg-yellow-600 hover:bg-yellow-500 text-black font-semibold text-sm px-5 py-2.5 rounded-xl transition-colors">
            ⬇ Download sftp_{domain}_id_ed25519.pem
          </button>
        </div>
      )}

      {/* Client instructions */}
      {info && (
        <div className="card space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">Connect with your SFTP client</p>
          <div className="flex gap-1 flex-wrap">
            {Object.entries(CLIENT_INSTRUCTIONS).map(([id, { name }]) => (
              <button key={id} onClick={() => setClient(id)}
                className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                  client === id
                    ? 'bg-brand-600/30 border-brand-600 text-brand-300'
                    : 'bg-panel-700/50 border-panel-600 text-gray-400 hover:text-white'
                }`}>
                {name}
              </button>
            ))}
          </div>
          <ol className="space-y-2">
            {CLIENT_INSTRUCTIONS[client].steps.map((s, i) => (
              <li key={i} className="flex gap-3 text-xs text-gray-300">
                <span className="text-brand-400 font-bold w-4 shrink-0">{i + 1}.</span>
                <span className="font-mono">{s}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const TABS = ['CMS', 'Framework', 'Webmail', 'Analytics', 'Collaboration', 'Developer', 'Utilities', 'Tools', 'SFTP'];
const CAT_MAP = {
  CMS: 'cms', Framework: 'framework', Webmail: 'webmail', Analytics: 'analytics',
  Collaboration: 'collaboration', Developer: 'developer',
  Utilities: 'utilities', Tools: 'tools',
};

export default function MarketplacePage() {
  const [tab,        setTab]        = useState('CMS');
  const [catalog,    setCatalog]    = useState({});
  const [domains,    setDomains]    = useState([]);
  const [installing, setInstalling] = useState(null);  // app being installed

  useEffect(() => {
    api.get('/api/marketplace/apps').then(r => setCatalog(r.data ?? {})).catch(() => {});
    api.get('/api/domains').then(r => {
      const d = (r.data?.domains ?? r.data ?? []).map(x => x.name ?? x.domain ?? x).filter(Boolean);
      setDomains(d);
    }).catch(() => {});
  }, []);

  const apps = Object.values(catalog).filter(a => a.category === CAT_MAP[tab]);

  return (
    <div className="space-y-5">
      {/* Page header */}
      <h1 className="text-xl font-bold text-white flex items-center gap-2">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#60a5fa" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
          <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
          <line x1="12" y1="22.08" x2="12" y2="12"/>
        </svg>
        Marketplace
      </h1>

      {/* Tab bar */}
      <div className="flex gap-1 bg-panel-800 border border-panel-600 rounded-xl p-1 w-fit flex-wrap">
        {TABS.map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-1.5 rounded-lg text-sm transition-colors ${
              tab === t
                ? 'bg-brand-600/30 text-brand-300 font-medium'
                : 'text-gray-400 hover:text-white hover:bg-panel-700'
            }`}>
            {t}
          </button>
        ))}
      </div>

      {/* SFTP tab */}
      {tab === 'SFTP' && (
        domains.length === 0
          ? <div className="card text-gray-500 text-sm text-center py-10">Create a domain first to set up SFTP access.</div>
          : <SftpTab domains={domains} />
      )}

      {/* App grid */}
      {tab !== 'SFTP' && (
        domains.length === 0
          ? (
            <div className="panel p-10 text-center space-y-3">
              <svg className="mx-auto mb-2 text-ink-muted" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>
              </svg>
              <p className="text-ink-primary font-semibold text-[15px]">No domains set up yet</p>
              <p className="text-ink-muted text-[13px]">
                You need to create a domain before installing apps from the Marketplace.
              </p>
              <a href="/domains" className="btn-primary inline-flex items-center gap-1.5 text-sm mt-2 px-5 py-2">
                Go to Domains
              </a>
            </div>
          )
          : apps.length === 0
            ? <div className="panel text-ink-muted text-sm text-center py-10">Loading…</div>
            : <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {apps.map(app => (
                  <AppCard key={app.id} app={app} onInstall={setInstalling} />
                ))}
              </div>
      )}

      {/* Install modal */}
      {installing && (
        <InstallModal
          app={installing}
          domains={domains}
          onClose={() => setInstalling(null)}
          onDone={() => setInstalling(null)}
        />
      )}
    </div>
  );
}
