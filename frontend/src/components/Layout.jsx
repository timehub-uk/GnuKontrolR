import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  LayoutDashboard, Globe, Users, Container, Server,
  FolderOpen, Database, Mail, ShieldCheck, ScrollText,
  HardDrive, Terminal, Settings, LogOut, Menu, X, ChevronRight,
  Package, Eye, BarChart2,
} from 'lucide-react';

const NAV = [
  // ── Core ──────────────────────────────────────────────────────────────────
  { to: '/',              icon: LayoutDashboard, label: 'Dashboard'        },
  { to: '/domains',       icon: Globe,           label: 'Domains'          },
  { to: '/docker',        icon: Container,       label: 'Containers'       },
  // ── Services ──────────────────────────────────────────────────────────────
  { to: '/services',      icon: Server,          label: 'Master Services', adminOnly: true },
  { to: '/marketplace',   icon: Package,         label: 'Marketplace'      },
  // ── Hosting ───────────────────────────────────────────────────────────────
  { to: '/dns',           icon: Globe,           label: 'DNS'              },
  { to: '/files',         icon: FolderOpen,      label: 'Files'            },
  { to: '/databases',     icon: Database,        label: 'Databases'        },
  { to: '/email',         icon: Mail,            label: 'Email'            },
  { to: '/ssl',           icon: ShieldCheck,     label: 'SSL / TLS'        },
  { to: '/backups',       icon: HardDrive,       label: 'Backups'          },
  { to: '/logs',          icon: ScrollText,      label: 'Logs'             },
  { to: '/terminal',      icon: Terminal,        label: 'Terminal'         },
  // ── Admin ─────────────────────────────────────────────────────────────────
  { to: '/users',         icon: Users,           label: 'Users',           adminOnly: true },
  { to: '/admin-content', icon: Eye,             label: 'Content Viewer',  adminOnly: true },
  { to: '/settings',      icon: Settings,        label: 'Settings'         },
];

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(true);

  const handleLogout = () => { logout(); navigate('/login'); };
  const isAdmin = ['superadmin','admin'].includes(user?.role);

  return (
    <div className="flex min-h-screen bg-panel-900">
      {/* Sidebar */}
      <aside className={`flex flex-col bg-panel-800 border-r border-panel-600 transition-all duration-200 ${open ? 'w-56' : 'w-14'} flex-shrink-0`}>
        {/* Brand */}
        <div className="flex items-center gap-3 px-4 py-4 border-b border-panel-600">
          <div className="w-7 h-7 bg-brand-600 rounded-lg flex items-center justify-center flex-shrink-0">
            <Server size={14} className="text-white" />
          </div>
          {open && <span className="font-bold text-white text-sm tracking-wide">GnuKontrolR</span>}
          <button onClick={() => setOpen(o => !o)} className="ml-auto text-gray-400 hover:text-white">
            {open ? <X size={15} /> : <Menu size={15} />}
          </button>
        </div>

        {/* Nav links */}
        <nav className="flex-1 py-3 overflow-y-auto">
          {NAV.filter(n => !n.adminOnly || isAdmin).map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                  isActive
                    ? 'bg-brand-600/20 text-brand-400 border-r-2 border-brand-500'
                    : 'text-gray-400 hover:text-white hover:bg-panel-700'
                }`
              }
            >
              <Icon size={16} className="flex-shrink-0" />
              {open && <span>{label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* User footer */}
        <div className="border-t border-panel-600 p-3">
          {open && (
            <div className="mb-2">
              <div className="text-xs font-medium text-white truncate">{user?.username}</div>
              <div className="text-xs text-gray-500 capitalize">{user?.role}</div>
            </div>
          )}
          <button onClick={handleLogout} className="flex items-center gap-2 text-gray-400 hover:text-red-400 text-xs transition-colors">
            <LogOut size={14} />
            {open && 'Sign out'}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top bar */}
        <header className="bg-panel-800 border-b border-panel-600 px-6 py-3 flex items-center justify-between flex-shrink-0">
          <div className="text-sm text-gray-400">
            WebPanel <ChevronRight size={12} className="inline" />
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs bg-panel-700 text-gray-300 px-3 py-1 rounded-full capitalize">
              {user?.role}
            </span>
            <span className="text-xs text-gray-500">{user?.email}</span>
          </div>
        </header>

        <div className="flex-1 overflow-auto p-6">
          {children}
        </div>
      </main>
    </div>
  );
}
