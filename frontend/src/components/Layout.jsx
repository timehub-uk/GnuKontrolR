import { useState, useEffect, useRef, useCallback } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  LayoutDashboard, Globe, Users, Container, Server,
  FolderOpen, Database, Mail, ShieldCheck, ScrollText,
  HardDrive, Terminal, Settings, LogOut,
  Package, Eye, Activity, Shield, ChevronRight, ChevronLeft, Cpu,
  LayoutGrid, PanelLeftClose, PanelLeftOpen, BrainCircuit, Stethoscope, Bell, Network, Bot,
} from 'lucide-react';
import AiPanel from './AiPanel';
import CommandPalette from './CommandPalette';
import api from '../utils/api';

// ── Brand logo SVG ────────────────────────────────────────────────────────────
function BrandIcon({ size = 26 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ flexShrink: 0 }}>
      <defs>
        <linearGradient id="bl" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
          <stop stopColor="#6366f1"/><stop offset="1" stopColor="#8b5cf6"/>
        </linearGradient>
      </defs>
      <rect width="28" height="28" rx="7" fill="url(#bl)"/>
      <rect x="6" y="8" width="16" height="4" rx="1.5" fill="white" fillOpacity="0.9"/>
      <rect x="6" y="14" width="16" height="4" rx="1.5" fill="white" fillOpacity="0.55"/>
      <circle cx="19" cy="10" r="1.5" fill="#4ade80"/>
      <circle cx="19" cy="16" r="1.5" fill="white" fillOpacity="0.35"/>
      <rect x="6" y="20" width="9" height="2" rx="1" fill="white" fillOpacity="0.25"/>
    </svg>
  );
}

// ── Navigation groups ─────────────────────────────────────────────────────────
const NAV_GROUPS = [
  {
    label: 'Core',
    items: [
      { to: '/menu',     icon: LayoutGrid,      label: 'Main Menu'  },
      { to: '/',         icon: LayoutDashboard, label: 'Dashboard', end: true },
      { to: '/domains',  icon: Globe,           label: 'Domains'    },
      { to: '/docker',   icon: Container,       label: 'Containers' },
    ],
  },
  {
    label: 'Services',
    items: [
      { to: '/services',    icon: Server,       label: 'Master Services', adminOnly: true },
      { to: '/diagnostic',  icon: Stethoscope, label: 'Diagnostic',       adminOnly: true },
      { to: '/marketplace', icon: Package,      label: 'Marketplace' },
    ],
  },
  {
    label: 'Hosting',
    items: [
      { to: '/dns',       icon: Globe,       label: 'DNS'       },
      { to: '/files',     icon: FolderOpen,  label: 'Files'     },
      { to: '/databases', icon: Database,    label: 'Databases' },
      { to: '/email',     icon: Mail,        label: 'Email'     },
      { to: '/ssl',       icon: ShieldCheck, label: 'SSL / TLS' },
      { to: '/backups',   icon: HardDrive,   label: 'Backups'   },
      { to: '/logs',      icon: ScrollText,  label: 'Logs'      },
      { to: '/terminal',  icon: Terminal,    label: 'Terminal'  },
    ],
  },
  {
    label: 'Security',
    items: [
      { to: '/security',      icon: Shield,   label: 'Security'      },
      { to: '/activity-log',  icon: Activity, label: 'Activity Log'  },
      { to: '/admin-content', icon: Eye,      label: 'Content Viewer', adminOnly: true },
    ],
  },
  {
    label: 'Admin',
    items: [
      { to: '/notifications', icon: Bell,     label: 'Notifications', adminOnly: true },
      { to: '/users',         icon: Users,    label: 'Users',         adminOnly: true },
      { to: '/settings',      icon: Settings, label: 'Settings'       },
    ],
  },
];

const ROUTE_LABELS = {
  '/': 'Dashboard', '/menu': 'Main Menu', '/domains': 'Domains',
  '/docker': 'Containers', '/services': 'Master Services', '/marketplace': 'Marketplace',
  '/dns': 'DNS', '/files': 'Files', '/databases': 'Databases', '/email': 'Email',
  '/ssl': 'SSL / TLS', '/backups': 'Backups', '/logs': 'Logs', '/terminal': 'Terminal',
  '/security': 'Security', '/activity-log': 'Activity Log', '/admin-content': 'Content Viewer',
  '/users': 'Users', '/settings': 'Settings', '/ai-admin': 'AI Admin',
  '/diagnostic': 'Diagnostic', '/notifications': 'Notifications',
  '/networking': 'Networking', '/ai-containers': 'AI Containers',
};

// ── NavItem — full or icon-only ───────────────────────────────────────────────
function NavItem({ to, icon: Icon, label, end, collapsed, badge }) {
  return (
    <div className="relative group/tip">
      <NavLink
        to={to}
        end={end}
        className={({ isActive }) =>
          `flex items-center gap-2.5 rounded-md text-[13px] font-medium
           transition-colors duration-150 border-l-2
           ${collapsed ? 'px-2 py-2 justify-center ml-0' : 'px-2.5 py-1.5 ml-[-2px]'}
           ${isActive
             ? 'border-brand text-brand-light bg-brand/10'
             : 'border-transparent text-ink-muted hover:text-ink-secondary hover:bg-panel-elevated'
           }`
        }
      >
        {({ isActive }) => (
          <>
            <div className="relative flex-shrink-0">
              <Icon size={15} className={isActive ? 'text-brand' : ''} />
              {badge > 0 && (
                <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-ok shadow-[0_0_6px_rgba(74,222,128,0.8)] animate-pulse" />
              )}
            </div>
            {!collapsed && <span className="truncate flex-1">{label}</span>}
            {!collapsed && badge > 0 && (
              <span className="text-[10px] font-bold bg-ok/20 text-ok px-1.5 py-0.5 rounded-full leading-none">
                {badge > 99 ? '99+' : badge}
              </span>
            )}
          </>
        )}
      </NavLink>
      {/* Tooltip when collapsed */}
      {collapsed && (
        <div className="
          pointer-events-none absolute left-full top-1/2 -translate-y-1/2 ml-2 z-50
          bg-panel-card border border-panel-subtle text-ink-primary text-xs
          rounded-lg px-2.5 py-1.5 whitespace-nowrap shadow-xl
          opacity-0 group-hover/tip:opacity-100 transition-opacity duration-150
        ">
          {label}{badge > 0 ? ` (${badge})` : ''}
          <div className="absolute right-full top-1/2 -translate-y-1/2 border-4 border-transparent border-r-panel-subtle" />
        </div>
      )}
    </div>
  );
}

// ── Layout ────────────────────────────────────────────────────────────────────
export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate   = useNavigate();
  const location   = useLocation();
  const [collapsed, setCollapsed]       = useState(false);
  const [unreadCount, setUnreadCount]   = useState(0);
  const historyDepth = useRef(0);

  // Track navigation depth so we know when there's somewhere to go back to
  useEffect(() => {
    historyDepth.current += 1;
  }, [location.pathname]);

  // Poll unread notification count every 30 s (admin only)
  const isAdmin = ['superadmin', 'admin'].includes(user?.role);
  const fetchUnread = useCallback(async () => {
    if (!isAdmin) return;
    try {
      const { data } = await api.get('/api/notifications/unread-count');
      setUnreadCount(data.count ?? 0);
    } catch { /* non-fatal */ }
  }, [isAdmin]);

  useEffect(() => {
    fetchUnread();
    const timer = setInterval(fetchUnread, 30_000);
    return () => clearInterval(timer);
  }, [fetchUnread]);

  // Reset unread count when navigating to notifications page
  useEffect(() => {
    if (location.pathname === '/notifications') setUnreadCount(0);
  }, [location.pathname]);

  const canGoBack  = historyDepth.current > 1;
  const breadcrumb = ROUTE_LABELS[location.pathname] ?? 'GnuKontrolR';
  const initial    = (user?.username?.[0] ?? '?').toUpperCase();

  const roleColors = {
    superadmin: 'bg-brand/15 text-brand-light border-brand/25',
    admin:      'bg-violet/15 text-violet-light border-violet/25',
    reseller:   'bg-warn/15 text-warn-light border-warn/25',
    user:       'bg-panel-subtle text-ink-muted border-panel-subtle',
  };
  const roleColor = roleColors[user?.role] ?? roleColors.user;

  return (
    <div className="flex min-h-screen bg-panel-base">

      {/* ── Sidebar ────────────────────────────────────────────────────────── */}
      <aside
        className="flex-shrink-0 flex flex-col bg-panel-surface border-r border-panel-subtle transition-all duration-200 sticky top-0 h-screen overflow-y-auto"
        style={{ width: collapsed ? 52 : 220 }}
      >
        {/* Brand + collapse toggle */}
        <div className={`flex items-center border-b border-panel-subtle h-12 px-3 flex-shrink-0 ${collapsed ? 'justify-center' : 'gap-2.5'}`}>
          <BrandIcon size={26} />
          {!collapsed && (
            <span className="font-bold text-[13px] text-ink-primary tracking-tight flex-1 truncate">GnuKontrolR</span>
          )}
          <button
            onClick={() => setCollapsed(c => !c)}
            className={`text-ink-muted hover:text-ink-secondary transition-colors flex-shrink-0 ${collapsed ? 'mt-0' : 'ml-auto'}`}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
          </button>
        </div>

        {/* Nav */}
        <nav className={`flex-1 py-3 overflow-y-auto overflow-x-hidden space-y-0.5 ${collapsed ? 'px-1.5' : 'px-3'}`}>
          {NAV_GROUPS.map(group => {
            const visible = group.items.filter(i => !i.adminOnly || isAdmin);
            if (!visible.length) return null;
            return (
              <div key={group.label}>
                {!collapsed ? (
                  <p className="px-2.5 pt-3 pb-1.5 text-[10px] font-semibold uppercase tracking-widest text-ink-faint select-none">
                    {group.label}
                  </p>
                ) : (
                  <div className="my-2 border-t border-panel-subtle mx-1" />
                )}
                {visible.map(item => (
                  <NavItem
                    key={item.to}
                    to={item.to}
                    icon={item.icon}
                    label={item.label}
                    end={item.end}
                    collapsed={collapsed}
                    badge={item.to === '/notifications' ? unreadCount : 0}
                  />
                ))}
              </div>
            );
          })}
        </nav>

        {/* User footer */}
        <div className={`border-t border-panel-subtle py-3 ${collapsed ? 'px-1.5' : 'px-3'}`}>
          {!collapsed ? (
            <div className="flex items-center gap-2.5 mb-2 px-1">
              <div
                className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold text-white"
                style={{ background: 'linear-gradient(135deg,#6366f1,#8b5cf6)', boxShadow: '0 0 10px rgba(99,102,241,0.3)' }}
              >
                {initial}
              </div>
              <div className="min-w-0">
                <div className="text-[12px] font-semibold text-ink-primary truncate">{user?.username}</div>
                <div className="text-[10px] text-ink-muted flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-brand flex-shrink-0" />
                  {user?.role}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex justify-center mb-2">
              <div
                className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold text-white"
                style={{ background: 'linear-gradient(135deg,#6366f1,#8b5cf6)' }}
                title={user?.username}
              >
                {initial}
              </div>
            </div>
          )}

          <div className="relative group/so">
            <button
              onClick={() => { logout(); navigate('/login'); }}
              className={`w-full flex items-center gap-2 rounded-md text-[12px] text-ink-muted
                          hover:text-bad-light hover:bg-bad/10 transition-colors duration-150
                          ${collapsed ? 'justify-center px-1.5 py-2' : 'px-2.5 py-1.5'}`}
              title="Sign out"
            >
              <LogOut size={13} />
              {!collapsed && 'Sign out'}
            </button>
            {collapsed && (
              <div className="pointer-events-none absolute left-full top-1/2 -translate-y-1/2 ml-2 z-50
                              bg-panel-card border border-panel-subtle text-ink-primary text-xs
                              rounded-lg px-2.5 py-1.5 whitespace-nowrap shadow-xl
                              opacity-0 group-hover/so:opacity-100 transition-opacity duration-150">
                Sign out
                <div className="absolute right-full top-1/2 -translate-y-1/2 border-4 border-transparent border-r-panel-subtle" />
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* ── Main ───────────────────────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0">

        {/* Topbar */}
        <header className="h-12 bg-panel-surface border-b border-panel-border px-5 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-1.5 text-[13px]">
            {canGoBack && (
              <button
                onClick={() => navigate(-1)}
                className="text-ink-faint hover:text-ink-primary transition-colors p-0.5 -ml-1 mr-0.5"
                title="Go back"
                aria-label="Go back"
              >
                <ChevronLeft size={15} />
              </button>
            )}
            <button
              onClick={() => navigate('/')}
              className="flex items-center gap-1.5 text-ink-faint hover:text-ink-primary transition-colors"
              title="Dashboard"
            >
              <Cpu size={12} className="text-brand flex-shrink-0" />
              <span>GnuKontrolR</span>
            </button>
            <ChevronRight size={12} className="text-panel-subtle" />
            <span className="text-ink-primary font-medium">{breadcrumb}</span>
          </div>
          <div className="flex items-center gap-3">
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold border capitalize ${roleColor}`}>
              {user?.role}
            </span>
            <span className="text-[11px] text-ink-muted hidden md:block truncate max-w-[200px]">{user?.email}</span>
          </div>
        </header>

        {/* Content */}
        <div className="flex-1 p-6">
          {children}
        </div>
      </main>

      <AiPanel />
      <CommandPalette />
    </div>
  );
}
