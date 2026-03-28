/**
 * MenuPage — Plesk-style icon grid home screen.
 *
 * Features:
 *  - Custom SVG icons for every item
 *  - 5s hover  → brief tooltip description
 *  - 10s hover → animated full-info card with blurred backdrop (Continue / Close)
 *  - Category gradient tiles, Quick Links bar
 */
import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

// ── Custom SVG icons ──────────────────────────────────────────────────────────

const I = (d, extra = '') =>
  ({ size = 18, className = '' }) => (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
      strokeLinejoin="round" className={className} {...(extra ? { style: {} } : {})}>
      {d}
    </svg>
  );

export const IconGlobe = I(<>
  <circle cx="12" cy="12" r="10"/>
  <path d="M2 12h20"/>
  <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
</>);

export const IconNetwork = I(<>
  <circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/>
  <path d="M12 7v4M12 11 5.5 17M12 11l6.5 6"/>
</>);

export const IconFolder = I(<>
  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
</>);

export const IconDatabase = I(<>
  <ellipse cx="12" cy="5" rx="9" ry="3"/>
  <path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/>
  <path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"/>
</>);

export const IconMail = I(<>
  <rect x="2" y="4" width="20" height="16" rx="2"/>
  <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
</>);

export const IconLock = I(<>
  <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
  <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
</>);

export const IconContainer = I(<>
  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
  <polyline points="3.29 7 12 12 20.71 7"/>
  <line x1="12" y1="22" x2="12" y2="12"/>
</>);

export const IconServer = I(<>
  <rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>
  <rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>
  <line x1="6" y1="6" x2="6.01" y2="6"/>
  <line x1="6" y1="18" x2="6.01" y2="18"/>
</>);

export const IconPackage = I(<>
  <line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/>
  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
  <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
  <line x1="12" y1="22.08" x2="12" y2="12"/>
</>);

export const IconTerminal = I(<>
  <polyline points="4 17 10 11 4 5"/>
  <line x1="12" y1="19" x2="20" y2="19"/>
</>);

export const IconLogs = I(<>
  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
  <polyline points="14 2 14 8 20 8"/>
  <line x1="16" y1="13" x2="8" y2="13"/>
  <line x1="16" y1="17" x2="8" y2="17"/>
  <polyline points="10 9 9 9 8 9"/>
</>);

export const IconBackup = I(<>
  <polyline points="23 4 23 10 17 10"/>
  <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
  <polyline points="12 7 12 12 15 15"/>
</>);

export const IconShield = I(<>
  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
</>);

export const IconActivity = I(<>
  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
</>);

export const IconEye = I(<>
  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
  <circle cx="12" cy="12" r="3"/>
</>);

export const IconUsers = I(<>
  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
  <circle cx="9" cy="7" r="4"/>
  <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
  <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
</>);

export const IconSettings = I(<>
  <circle cx="12" cy="12" r="3"/>
  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
</>);

export const IconDashboard = I(<>
  <rect x="3" y="3" width="7" height="7" rx="1"/>
  <rect x="14" y="3" width="7" height="7" rx="1"/>
  <rect x="3" y="14" width="7" height="7" rx="1"/>
  <rect x="14" y="14" width="7" height="7" rx="1"/>
</>);

export const IconGrid = I(<>
  <rect x="3" y="3" width="4" height="4" rx="0.5"/>
  <rect x="10" y="3" width="4" height="4" rx="0.5"/>
  <rect x="17" y="3" width="4" height="4" rx="0.5"/>
  <rect x="3" y="10" width="4" height="4" rx="0.5"/>
  <rect x="10" y="10" width="4" height="4" rx="0.5"/>
  <rect x="17" y="10" width="4" height="4" rx="0.5"/>
  <rect x="3" y="17" width="4" height="4" rx="0.5"/>
  <rect x="10" y="17" width="4" height="4" rx="0.5"/>
  <rect x="17" y="17" width="4" height="4" rx="0.5"/>
</>);

export const IconCpu = I(<>
  <rect x="4" y="4" width="16" height="16" rx="2"/>
  <rect x="9" y="9" width="6" height="6"/>
  <line x1="9" y1="1" x2="9" y2="4"/>
  <line x1="15" y1="1" x2="15" y2="4"/>
  <line x1="9" y1="20" x2="9" y2="23"/>
  <line x1="15" y1="20" x2="15" y2="23"/>
  <line x1="20" y1="9" x2="23" y2="9"/>
  <line x1="20" y1="14" x2="23" y2="14"/>
  <line x1="1" y1="9" x2="4" y2="9"/>
  <line x1="1" y1="14" x2="4" y2="14"/>
</>);

export const IconBrain = I(<>
  <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z"/>
  <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z"/>
</>);

// ── Menu definition (with description + details for info cards) ───────────────

const MENU = [
  {
    category: 'Hosting',
    color: 'from-blue-600/20 to-blue-800/10 border-blue-700/40',
    accent: 'text-blue-400',
    icon: IconGlobe,
    items: [
      {
        to: '/domains', icon: IconGlobe, label: 'Domains',
        description: 'Manage domain names and virtual hosts.',
        details: 'Add, remove and configure domain names hosted on this panel. Set up server aliases, redirects, and virtual host configurations. Each domain runs in its own isolated Docker container.',
      },
      {
        to: '/dns', icon: IconNetwork, label: 'DNS',
        description: 'Edit DNS zones and records.',
        details: 'Full DNS zone editor powered by PowerDNS. Create and manage A, AAAA, CNAME, MX, TXT and SRV records. Propagation status and TTL controls included.',
      },
      {
        to: '/files', icon: IconFolder, label: 'Files',
        description: 'Browse, upload and manage website files.',
        details: 'Web-based file manager for your hosting directories. Upload files, create folders, edit text files, set permissions, and extract/create archives — all without leaving the browser.',
      },
      {
        to: '/databases', icon: IconDatabase, label: 'Databases',
        description: 'Create and manage MySQL databases.',
        details: 'Provision MySQL databases and user accounts, run queries via the built-in SQL editor, import/export dumps, and monitor table sizes and performance metrics.',
      },
      {
        to: '/email', icon: IconMail, label: 'Email',
        description: 'Set up mailboxes and forwarders.',
        details: 'Create email accounts, aliases and catch-all addresses for your domains. Configure spam filters, DKIM signing, and DMARC policies to protect your sender reputation.',
      },
      {
        to: '/ssl', icon: IconLock, label: 'SSL / TLS',
        description: 'Install and auto-renew SSL certificates.',
        details: 'Issue and install SSL/TLS certificates for your domains. Supports Let\'s Encrypt auto-renewal, manual certificate upload, and per-domain HTTPS redirect enforcement.',
      },
    ],
  },
  {
    category: 'Infrastructure',
    color: 'from-purple-600/20 to-purple-800/10 border-purple-700/40',
    accent: 'text-purple-400',
    icon: IconContainer,
    items: [
      {
        to: '/networking', icon: IconNetwork, label: 'Networking',
        description: 'IP blocking, firewall, country geo-blocking.',
        details: 'Manage IP ban lists, per-domain country blocking with flag-based country selector, firewall rules, and the full API endpoint reference. Master IPs (Docker bridge + server external) are always whitelisted.',
        adminOnly: true,
      },
      {
        to: '/ai-admin', icon: IconBrain, label: 'AI Admin',
        description: 'Configure AI providers and LLM settings.',
        details: 'Set up and manage AI provider API keys (Anthropic, OpenAI, Ollama, OpenCode). Configure default models, enable or disable the AI assistant panel-wide, and review AI usage per user.',
        adminOnly: true,
      },
      {
        to: '/ai-containers', icon: IconCpu, label: 'AI Containers',
        description: 'Manage dedicated per-user AI containers.',
        details: 'View, stop, and remove the isolated Docker containers provisioned per user for AI tool sessions. Containers are named ai-{tool}-{user}-{id} and created automatically on first AI session.',
        adminOnly: true,
      },
      {
        to: '/docker', icon: IconContainer, label: 'Containers',
        description: 'Manage Docker containers per domain.',
        details: 'Each domain runs in a fully isolated Docker container with its own file system, ports and resources. Create, start, stop and inspect containers, view real-time logs, and manage port assignments.',
      },
      {
        to: '/services', icon: IconServer, label: 'Master Services',
        description: 'Control panel-wide system services.',
        details: 'Start, stop and restart core services that power the control panel — web server, database, mail relay, and DNS daemon. View service status, resource usage and recent error logs.',
        adminOnly: true,
      },
      {
        to: '/marketplace', icon: IconPackage, label: 'Marketplace',
        description: 'One-click app and plugin installer.',
        details: 'Install popular web applications with a single click — WordPress, Joomla, Drupal, Magento and more. Each install is automatically configured for your domain and secured out of the box.',
      },
      {
        to: '/terminal', icon: IconTerminal, label: 'Terminal',
        description: 'SSH terminal access in the browser.',
        details: 'Full in-browser SSH terminal connected to your hosting container. Run shell commands, use editors like nano or vim, manage cron jobs, and debug issues without needing a local SSH client.',
      },
      {
        to: '/logs', icon: IconLogs, label: 'Logs',
        description: 'View web server and application logs.',
        details: 'Real-time access to Nginx access and error logs, PHP error logs, and application logs for all your domains. Filter by severity, search for specific entries, and download log archives.',
      },
      {
        to: '/backups', icon: IconBackup, label: 'Backups',
        description: 'Snapshot and restore configurations.',
        details: 'Three-deep rolling backups for every config change — Nginx, PHP, environment variables and SSL certificates. Restore any previous snapshot in one click. Full site backups also available.',
      },
    ],
  },
  {
    category: 'Security',
    color: 'from-green-600/20 to-green-800/10 border-green-700/40',
    accent: 'text-green-400',
    icon: IconShield,
    items: [
      {
        to: '/security', icon: IconShield, label: 'Security Audit',
        description: 'Scan domains for security issues.',
        details: 'Automated security advisor that checks each domain for common vulnerabilities: missing security headers, weak TLS configuration, exposed sensitive files, outdated software, and more. Provides a scored report with fix suggestions.',
      },
      {
        to: '/ssl', icon: IconLock, label: 'SSL / TLS',
        description: 'Certificate expiry and validity status.',
        details: 'Overview of SSL certificate status across all your domains — expiry dates, issuer, key strength, and any configuration issues. Renew or replace certificates directly from this view.',
      },
      {
        to: '/activity-log', icon: IconActivity, label: 'Activity Log',
        description: 'Your private request and event history.',
        details: 'A rolling log of all API requests made under your account — method, endpoint, status code, duration, and event ID. Failed requests include plain-English explanations and suggested fixes.',
      },
      {
        to: '/admin-content', icon: IconEye, label: 'Content Viewer',
        description: 'Review hosted content across domains.',
        details: 'Admin tool to inspect the content served by any hosted domain — HTML source, headers, and file listings. Used for abuse investigation and compliance review.',
        adminOnly: true,
      },
    ],
  },
  {
    category: 'Account',
    color: 'from-orange-600/20 to-orange-800/10 border-orange-700/40',
    accent: 'text-orange-400',
    icon: IconUsers,
    adminOnly: true,
    items: [
      {
        to: '/users', icon: IconUsers, label: 'Users',
        description: 'Manage panel user accounts and roles.',
        details: 'Create and manage user accounts for the control panel. Assign roles (superadmin, admin, user), reset passwords, lock accounts, and review per-user activity logs.',
        adminOnly: true,
      },
      {
        to: '/settings', icon: IconSettings, label: 'Settings',
        description: 'Configure panel preferences.',
        details: 'Adjust control panel settings including display preferences, notification rules, API keys, webhook endpoints, and security policies like 2FA enforcement and session timeouts.',
      },
    ],
  },
];

// ── Info card (portal-style, rendered at body level via state lift) ────────────

function InfoCard({ item, accent, onContinue, onClose, visible }) {
  const Icon = item.icon;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className={`absolute inset-0 bg-black/60 transition-opacity duration-300 ${visible ? 'opacity-100' : 'opacity-0'}`}
           style={{ backdropFilter: visible ? 'blur(6px)' : 'none' }} />

      {/* Card */}
      <div
        className={`relative bg-panel-800 border border-panel-600 rounded-2xl p-6
                    max-w-sm w-full shadow-2xl transition-all duration-300 ease-out
                    ${visible ? 'opacity-100 scale-100 translate-y-0' : 'opacity-0 scale-95 translate-y-6'}`}
        onClick={e => e.stopPropagation()}
      >
        {/* Icon + title */}
        <div className="flex items-start gap-4 mb-4">
          <div className="w-14 h-14 rounded-2xl bg-panel-700 border border-panel-600 flex items-center justify-center flex-shrink-0">
            <Icon size={26} className={accent} />
          </div>
          <div className="pt-1">
            <h3 className="font-bold text-white text-lg leading-tight">{item.label}</h3>
            <p className={`text-xs font-medium mt-0.5 ${accent}`}>{item.description}</p>
          </div>
        </div>

        {/* Details */}
        <p className="text-sm text-gray-300 leading-relaxed mb-6">{item.details}</p>

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={onContinue}
            className="flex-1 bg-brand-600 hover:bg-brand-500 text-white font-medium text-sm px-4 py-2.5 rounded-xl transition-colors"
          >
            Open {item.label} →
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2.5 rounded-xl bg-panel-700 border border-panel-600 text-gray-400 hover:text-white hover:border-panel-500 text-sm transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ── SubItem tile with delayed tooltip + card ───────────────────────────────────

function SubItem({ to, icon: Icon, label, description, details, accent, onShowCard }) {
  const navigate   = useNavigate();
  const [tip, setTip] = useState(false);
  const timers     = useRef([]);

  const clear = () => { timers.current.forEach(clearTimeout); timers.current = []; };

  const enter = useCallback(() => {
    clear();
    timers.current.push(setTimeout(() => setTip(true),  5000));
    timers.current.push(setTimeout(() => {
      setTip(false);
      onShowCard({ to, icon: Icon, label, description, details });
    }, 10000));
  }, [to, label, description, details, onShowCard]);  // eslint-disable-line

  const leave = useCallback(() => { clear(); setTip(false); }, []);

  useEffect(() => () => clear(), []);

  return (
    <div className="relative group" onMouseEnter={enter} onMouseLeave={leave}>
      <button
        onClick={() => navigate(to)}
        className="w-full flex flex-col items-center gap-2 p-3 rounded-xl hover:bg-white/5 active:scale-95 transition-all"
      >
        {/* Icon with inside-out pulse on hover */}
        <div className="relative w-10 h-10 flex items-center justify-center">
          {/* Pulse rings — scale outward from centre on hover */}
          <span className="absolute inset-0 rounded-xl opacity-0 group-hover:opacity-100 group-hover:animate-[ping_1s_ease-out_infinite] bg-current" style={{ color: 'var(--color-brand, #6366f1)', opacity: 0 }} />
          <span className="absolute inset-0 rounded-xl opacity-0 group-hover:opacity-40 group-hover:animate-[ping_1s_ease-out_0.3s_infinite] bg-current" style={{ color: 'var(--color-brand, #6366f1)' }} />
          <div className="relative w-10 h-10 rounded-xl bg-panel-700/60 border border-panel-600 flex items-center justify-center group-hover:border-panel-500 group-hover:bg-panel-600/80 transition-all duration-200 z-10">
            <Icon size={18} className={`${accent} opacity-80 group-hover:opacity-100 transition-opacity`} />
          </div>
        </div>
        <span className="text-xs text-gray-400 group-hover:text-gray-200 text-center leading-tight transition-colors">
          {label}
        </span>
      </button>

      {/* 5-second brief tooltip */}
      {tip && (
        <div className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-40 animate-fade-in">
          <div className="bg-panel-700 border border-panel-500 text-white text-xs rounded-lg px-3 py-2 shadow-xl max-w-[180px] text-center leading-snug whitespace-normal">
            {description}
          </div>
          {/* Arrow */}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-panel-700" />
        </div>
      )}
    </div>
  );
}

// ── Category card ─────────────────────────────────────────────────────────────

function CategoryCard({ category, color, accent, icon: CatIcon, items, isAdmin, onShowCard }) {
  const visible = items.filter(i => !i.adminOnly || isAdmin);
  if (!visible.length) return null;

  return (
    <div className={`rounded-2xl border bg-gradient-to-br p-4 space-y-3 ${color}`}>
      <div className="flex items-center gap-2">
        <CatIcon size={15} className={accent} />
        <h2 className={`text-sm font-semibold ${accent}`}>{category}</h2>
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-3 lg:grid-cols-4 gap-1">
        {visible.map(item => (
          <SubItem key={item.to} {...item} accent={accent} onShowCard={onShowCard} />
        ))}
      </div>
    </div>
  );
}

// ── Quick links bar ───────────────────────────────────────────────────────────

function QuickLinks({ isAdmin }) {
  const navigate = useNavigate();
  const links = [
    { to: '/',           icon: IconDashboard, label: 'Dashboard' },
    { to: '/domains',    icon: IconGlobe,     label: 'Domains'   },
    { to: '/security',   icon: IconShield,    label: 'Security'  },
    { to: '/terminal',   icon: IconTerminal,  label: 'Terminal'  },
    ...(isAdmin ? [{ to: '/users', icon: IconUsers, label: 'Users' }] : []),
    { to: '/settings',   icon: IconSettings,  label: 'Settings'  },
  ];
  return (
    <div className="flex flex-wrap gap-2">
      {links.map(({ to, icon: Icon, label }) => (
        <button
          key={to}
          onClick={() => navigate(to)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-panel-700/50 border border-panel-600 text-xs text-gray-400 hover:text-white hover:bg-panel-700 hover:border-panel-500 transition-all"
        >
          <Icon size={12} /> {label}
        </button>
      ))}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MenuPage() {
  const { user }  = useAuth();
  const navigate  = useNavigate();
  const isAdmin   = ['superadmin', 'admin'].includes(user?.role);

  // Info-card state lifted here so it renders above all content
  const [cardItem,    setCardItem]    = useState(null);
  const [cardVisible, setCardVisible] = useState(false);

  const showCard = useCallback((item) => {
    setCardItem(item);
    // Tiny delay so CSS transition has something to animate from
    requestAnimationFrame(() => requestAnimationFrame(() => setCardVisible(true)));
  }, []);

  const closeCard = useCallback(() => {
    setCardVisible(false);
    setTimeout(() => setCardItem(null), 300);
  }, []);

  const continueToPage = useCallback(() => {
    const to = cardItem?.to;
    closeCard();
    if (to) setTimeout(() => navigate(to), 300);
  }, [cardItem, closeCard, navigate]);

  return (
    <div className="space-y-6 max-w-4xl">

      {/* Welcome header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 bg-brand-600/20 border border-brand-600/40 rounded-xl flex items-center justify-center">
          <IconCpu size={18} className="text-brand-400" />
        </div>
        <div>
          <h1 className="text-lg font-bold text-white">
            Welcome, {user?.username}
          </h1>
          <p className="text-xs text-gray-500 capitalize">{user?.role} · GnuKontrolR Control Panel</p>
        </div>
      </div>

      {/* Quick links */}
      <QuickLinks isAdmin={isAdmin} />

      {/* Hint */}
      <p className="text-xs text-gray-600 italic">
        Hover over any icon for 5 s to see a description, or hold for 10 s to open a full info card.
      </p>

      {/* Category icon grids */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {MENU.filter(g => !g.adminOnly || isAdmin).map(group => (
          <CategoryCard
            key={group.category}
            {...group}
            isAdmin={isAdmin}
            onShowCard={showCard}
          />
        ))}
      </div>

      {/* Info card (portal-like, rendered last so it's on top of everything) */}
      {cardItem && (
        <InfoCard
          item={cardItem}
          accent={
            MENU.find(g => g.items.some(i => i.to === cardItem.to))?.accent ?? 'text-brand-400'
          }
          visible={cardVisible}
          onContinue={continueToPage}
          onClose={closeCard}
        />
      )}
    </div>
  );
}
