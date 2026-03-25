import { useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Command } from 'cmdk';
import { motion, AnimatePresence } from 'framer-motion';
import { usePanelStore } from '../utils/store';
import { useAuth } from '../context/AuthContext';
import {
  LayoutDashboard, Globe, Users, Container, Server, FolderOpen,
  Database, Mail, ShieldCheck, ScrollText, HardDrive, Terminal,
  Settings, Package, Eye, Activity, Shield, LayoutGrid,
  BrainCircuit, Stethoscope, ChevronRight,
} from 'lucide-react';

const ALL_ITEMS = [
  { group: 'Navigation', label: 'Dashboard',       path: '/',              icon: LayoutDashboard },
  { group: 'Navigation', label: 'Main Menu',        path: '/menu',          icon: LayoutGrid },
  { group: 'Navigation', label: 'Domains',          path: '/domains',       icon: Globe },
  { group: 'Navigation', label: 'Containers',       path: '/docker',        icon: Container },
  { group: 'Navigation', label: 'Master Services',  path: '/services',      icon: Server,       adminOnly: true },
  { group: 'Navigation', label: 'Diagnostic',       path: '/diagnostic',    icon: Stethoscope,  adminOnly: true },
  { group: 'Navigation', label: 'Marketplace',      path: '/marketplace',   icon: Package },
  { group: 'Navigation', label: 'DNS',              path: '/dns',           icon: Globe },
  { group: 'Navigation', label: 'Files',            path: '/files',         icon: FolderOpen },
  { group: 'Navigation', label: 'Databases',        path: '/databases',     icon: Database },
  { group: 'Navigation', label: 'Email',            path: '/email',         icon: Mail },
  { group: 'Navigation', label: 'SSL / TLS',        path: '/ssl',           icon: ShieldCheck },
  { group: 'Navigation', label: 'Backups',          path: '/backups',       icon: HardDrive },
  { group: 'Navigation', label: 'Logs',             path: '/logs',          icon: ScrollText },
  { group: 'Navigation', label: 'Terminal',         path: '/terminal',      icon: Terminal,     adminOnly: true },
  { group: 'Navigation', label: 'Security',         path: '/security',      icon: Shield },
  { group: 'Navigation', label: 'Activity Log',     path: '/activity-log',  icon: Activity },
  { group: 'Navigation', label: 'Content Viewer',   path: '/admin-content', icon: Eye,          adminOnly: true },
  { group: 'Navigation', label: 'AI Admin',         path: '/ai-admin',      icon: BrainCircuit, adminOnly: true },
  { group: 'Navigation', label: 'Users',            path: '/users',         icon: Users,        adminOnly: true },
  { group: 'Navigation', label: 'Settings',         path: '/settings',      icon: Settings },
];

export default function CommandPalette() {
  const open            = usePanelStore(s => s.commandPaletteOpen);
  const setOpen         = usePanelStore(s => s.setCommandPaletteOpen);
  const navigate        = useNavigate();
  const { user }        = useAuth();
  const isAdmin         = user?.role === 'admin' || user?.role === 'superadmin';

  const items = ALL_ITEMS.filter(item => !item.adminOnly || isAdmin);

  // Keyboard shortcut
  useEffect(() => {
    const handler = e => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [setOpen]);

  const handleSelect = useCallback((path) => {
    navigate(path);
    setOpen(false);
  }, [navigate, setOpen]);

  const groups = [...new Set(items.map(i => i.group))];

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />

          {/* Palette */}
          <motion.div
            key="palette"
            initial={{ opacity: 0, scale: 0.96, y: -12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -12 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            className="fixed left-1/2 top-[18%] z-50 w-full max-w-md -translate-x-1/2"
          >
            <Command
              className="rounded-2xl border border-panel-subtle bg-panel-card shadow-2xl overflow-hidden"
              onKeyDown={e => { if (e.key === 'Escape') setOpen(false); }}
            >
              <div className="flex items-center gap-2 px-4 py-3 border-b border-panel-border">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-ink-muted flex-shrink-0">
                  <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
                </svg>
                <Command.Input
                  placeholder="Search pages and actions…"
                  className="flex-1 bg-transparent text-sm text-ink-primary placeholder:text-ink-muted outline-none"
                />
                <kbd className="text-[10px] text-ink-muted bg-panel-elevated border border-panel-border rounded px-1.5 py-0.5">ESC</kbd>
              </div>

              <Command.List className="max-h-80 overflow-y-auto p-2">
                <Command.Empty className="py-6 text-center text-sm text-ink-muted">
                  No results found
                </Command.Empty>

                {groups.map(group => {
                  const groupItems = items.filter(i => i.group === group);
                  return (
                    <Command.Group
                      key={group}
                      heading={group}
                      className="[&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-semibold [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider [&_[cmdk-group-heading]]:text-ink-muted [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5"
                    >
                      {groupItems.map(item => (
                        <Command.Item
                          key={item.path}
                          value={item.label}
                          onSelect={() => handleSelect(item.path)}
                          className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-ink-secondary cursor-pointer select-none
                            data-[selected=true]:bg-brand/15 data-[selected=true]:text-ink-primary
                            hover:bg-panel-elevated transition-colors"
                        >
                          <item.icon size={15} className="text-ink-muted flex-shrink-0" />
                          <span className="flex-1">{item.label}</span>
                          <ChevronRight size={12} className="text-ink-muted/40" />
                        </Command.Item>
                      ))}
                    </Command.Group>
                  );
                })}
              </Command.List>

              <div className="border-t border-panel-border px-4 py-2 flex items-center justify-between">
                <div className="flex items-center gap-3 text-[11px] text-ink-muted">
                  <span><kbd className="bg-panel-elevated border border-panel-border rounded px-1 py-0.5">↑↓</kbd> navigate</span>
                  <span><kbd className="bg-panel-elevated border border-panel-border rounded px-1 py-0.5">↵</kbd> open</span>
                </div>
                <span className="text-[11px] text-ink-muted">
                  <kbd className="bg-panel-elevated border border-panel-border rounded px-1 py-0.5">Ctrl K</kbd> to open
                </span>
              </div>
            </Command>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
