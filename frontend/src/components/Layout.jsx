import { useState } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  LayoutDashboard, Globe, Users, Container, Server,
  FolderOpen, Database, Mail, ShieldCheck, ScrollText,
  HardDrive, Terminal, Settings, LogOut, Menu, X,
  Package, Eye, Activity, Shield, ChevronRight, Cpu, LayoutGrid,
} from 'lucide-react';

// ── Navigation definition — grouped with section headers ─────────────────────
const NAV_GROUPS = [
  {
    label: 'Core',
    items: [
      { to: '/menu',     icon: LayoutGrid,      label: 'Main Menu'  },
      { to: '/',         icon: LayoutDashboard, label: 'Dashboard'  },
      { to: '/domains',  icon: Globe,           label: 'Domains'    },
      { to: '/docker',   icon: Container,       label: 'Containers' },
    ],
  },
  {
    label: 'Services',
    items: [
      { to: '/services',    icon: Server,  label: 'Master Services', adminOnly: true },
      { to: '/marketplace', icon: Package, label: 'Marketplace' },
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
      { to: '/security',      icon: Shield,   label: 'Security'        },
      { to: '/activity-log',  icon: Activity, label: 'Activity Log'    },
      { to: '/admin-content', icon: Eye,      label: 'Content Viewer', adminOnly: true },
    ],
  },
  {
    label: 'Admin',
    items: [
      { to: '/users',    icon: Users,    label: 'Users',    adminOnly: true },
      { to: '/settings', icon: Settings, label: 'Settings' },
    ],
  },
];

// Breadcrumb label map
const ROUTE_LABELS = {
  '/':             'Dashboard',
  '/menu':         'Main Menu',
  '/domains':      'Domains',
  '/docker':       'Containers',
  '/services':     'Master Services',
  '/marketplace':  'Marketplace',
  '/dns':          'DNS',
  '/files':        'Files',
  '/databases':    'Databases',
  '/email':        'Email',
  '/ssl':          'SSL / TLS',
  '/backups':      'Backups',
  '/logs':         'Logs',
  '/terminal':     'Terminal',
  '/security':     'Security',
  '/activity-log': 'Activity Log',
  '/admin-content':'Content Viewer',
  '/users':        'Users',
  '/settings':     'Settings',
};

// ── NavItem — single link with tooltip when sidebar is collapsed ──────────────

function NavItem({ to, icon: Icon, label, isOpen, end }) {
  return (
    <div className="relative group/nav">
      <NavLink
        to={to}
        end={end}
        className={({ isActive }) =>
          `flex items-center gap-3 px-3 py-2 mx-1 rounded-lg text-sm transition-colors ${
            isActive
              ? 'bg-brand-600/20 text-brand-300'
              : 'text-gray-400 hover:text-white hover:bg-panel-700/70'
          }`
        }
      >
        {({ isActive }) => (
          <>
            <Icon size={15} className={`flex-shrink-0 ${isActive ? 'text-brand-400' : ''}`} />
            {isOpen && <span className="truncate">{label}</span>}
          </>
        )}
      </NavLink>

      {/* Tooltip when collapsed */}
      {!isOpen && (
        <div className="
          pointer-events-none absolute left-full top-1/2 -translate-y-1/2 ml-2
          bg-panel-700 border border-panel-500 text-white text-xs rounded-lg
          px-2.5 py-1.5 whitespace-nowrap shadow-xl z-50
          opacity-0 group-hover/nav:opacity-100 transition-opacity duration-150
        ">
          {label}
          <div className="absolute right-full top-1/2 -translate-y-1/2 border-4 border-transparent border-r-panel-700" />
        </div>
      )}
    </div>
  );
}

// ── Main Layout ───────────────────────────────────────────────────────────────

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate  = useNavigate();
  const location  = useLocation();
  const [open, setOpen] = useState(true);

  const isAdmin = ['superadmin', 'admin'].includes(user?.role);

  const breadcrumb = ROUTE_LABELS[location.pathname] ?? 'GnuKontrolR';

  return (
    <div className="flex min-h-screen bg-panel-900">

      {/* ── Sidebar ─────────────────────────────────────────────────────────── */}
      <aside className={`
        flex flex-col bg-panel-800 border-r border-panel-600
        transition-all duration-200 flex-shrink-0
        ${open ? 'w-52' : 'w-[52px]'}
      `}>

        {/* Brand */}
        <div className="flex items-center gap-2.5 px-3 py-3.5 border-b border-panel-600">
          <div className="w-7 h-7 bg-brand-600 rounded-lg flex items-center justify-center flex-shrink-0">
            <Cpu size={13} className="text-white" />
          </div>
          {open && (
            <span className="font-bold text-white text-sm tracking-wide truncate">
              GnuKontrolR
            </span>
          )}
          <button
            onClick={() => setOpen(o => !o)}
            className="ml-auto text-gray-500 hover:text-white transition-colors flex-shrink-0"
            title={open ? 'Collapse' : 'Expand'}
          >
            {open ? <X size={14} /> : <Menu size={14} />}
          </button>
        </div>

        {/* Nav groups */}
        <nav className="flex-1 py-2 overflow-y-auto overflow-x-hidden space-y-0.5">
          {NAV_GROUPS.map(group => {
            const visible = group.items.filter(i => !i.adminOnly || isAdmin);
            if (!visible.length) return null;
            return (
              <div key={group.label}>
                {/* Section label — only shown when expanded */}
                {open && (
                  <p className="px-4 pt-3 pb-1 text-xs font-semibold uppercase tracking-widest text-gray-600 select-none">
                    {group.label}
                  </p>
                )}
                {/* Divider when collapsed */}
                {!open && <div className="mx-3 my-2 border-t border-panel-700" />}

                {visible.map(item => (
                  <NavItem
                    key={item.to}
                    to={item.to}
                    icon={item.icon}
                    label={item.label}
                    isOpen={open}
                    end={item.to === '/'}
                  />
                ))}
              </div>
            );
          })}
        </nav>

        {/* User footer */}
        <div className="border-t border-panel-600 p-2 space-y-1">
          {open ? (
            <div className="px-2 pb-1">
              <div className="text-xs font-medium text-white truncate">{user?.username}</div>
              <div className="text-xs text-gray-500 capitalize">{user?.role}</div>
            </div>
          ) : (
            <div className="flex justify-center py-1">
              <div className="w-6 h-6 rounded-full bg-brand-600/40 flex items-center justify-center">
                <span className="text-xs font-bold text-brand-300">
                  {user?.username?.[0]?.toUpperCase() ?? '?'}
                </span>
              </div>
            </div>
          )}
          <div className="relative group/signout">
            <button
              onClick={() => { logout(); navigate('/login'); }}
              className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-gray-500 hover:text-red-400 hover:bg-red-900/10 text-xs transition-colors ${!open ? 'justify-center' : ''}`}
            >
              <LogOut size={13} />
              {open && 'Sign out'}
            </button>
            {!open && (
              <div className="pointer-events-none absolute left-full top-1/2 -translate-y-1/2 ml-2 bg-panel-700 border border-panel-500 text-white text-xs rounded-lg px-2.5 py-1.5 whitespace-nowrap shadow-xl z-50 opacity-0 group-hover/signout:opacity-100 transition-opacity">
                Sign out
                <div className="absolute right-full top-1/2 -translate-y-1/2 border-4 border-transparent border-r-panel-700" />
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* ── Main content ────────────────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Top bar */}
        <header className="bg-panel-800 border-b border-panel-600 px-5 py-2.5 flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-1.5 text-sm text-gray-500">
            <Cpu size={12} className="text-brand-400" />
            <span className="text-gray-600">GnuKontrolR</span>
            <ChevronRight size={12} />
            <span className="text-gray-300 font-medium">{breadcrumb}</span>
          </div>
          <div className="flex items-center gap-3">
            <span className={`text-xs px-2.5 py-1 rounded-full font-medium capitalize ${
              user?.role === 'superadmin' ? 'bg-brand-600/25 text-brand-300' :
              user?.role === 'admin'      ? 'bg-blue-600/25 text-blue-300' :
              'bg-panel-600 text-gray-400'
            }`}>
              {user?.role}
            </span>
            <span className="text-xs text-gray-600 hidden md:block">{user?.email}</span>
          </div>
        </header>

        {/* Page content */}
        <div className="flex-1 overflow-auto p-5">
          {children}
        </div>
      </main>
    </div>
  );
}
