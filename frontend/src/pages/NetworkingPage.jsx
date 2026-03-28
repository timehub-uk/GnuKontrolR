import { useState, useEffect, useCallback } from 'react';
import {
  Network, Globe, Shield, Ban, RefreshCw, Plus, X, Wifi,
  ArrowUp, ArrowDown, Server, AlertTriangle, CheckCircle2, Flame,
  BookOpen, Code2, Lock, Tag, ChevronRight, ShieldOff,
} from 'lucide-react';
import api from '../utils/api';
import { toast } from '../utils/toast';
import DomainAccessRules from '../components/DomainAccessRules';

// ── Tabs ──────────────────────────────────────────────────────────────────────
const TABS = [
  { id: 'overview',    label: 'Overview',      icon: Network   },
  { id: 'domain-acl',  label: 'Domain Rules',  icon: ShieldOff },
  { id: 'api',         label: 'API Reference', icon: BookOpen  },
];

// ── Section card ──────────────────────────────────────────────────────────────
function Card({ icon: Icon, title, children, action }) {
  return (
    <div className="bg-panel-card border border-panel-subtle rounded-2xl overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-panel-subtle bg-panel-elevated/40">
        <div className="flex items-center gap-2">
          <Icon size={14} className="text-brand" />
          <span className="text-[13px] font-semibold text-ink-primary">{title}</span>
        </div>
        {action}
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

// ── IP row ────────────────────────────────────────────────────────────────────
function IpRow({ label, value, badge, badgeColor = 'text-ink-secondary' }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-panel-subtle last:border-0">
      <span className="text-[12px] text-ink-muted">{label}</span>
      <div className="flex items-center gap-2">
        {badge && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${badgeColor}`}>{badge}</span>
        )}
        <span className="text-[12px] font-mono font-medium text-ink-primary">{value || '—'}</span>
      </div>
    </div>
  );
}

// ── IP Ban Table ──────────────────────────────────────────────────────────────
function IpBanTable({ bans, onUnban }) {
  if (!bans.length) {
    return (
      <div className="flex flex-col items-center py-8 gap-2 text-ink-muted">
        <CheckCircle2 size={22} className="text-ok" />
        <span className="text-[12px]">No banned IPs</span>
      </div>
    );
  }
  return (
    <table className="w-full text-[12px]">
      <thead>
        <tr className="border-b border-panel-subtle">
          <th className="text-left px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-ink-faint">IP</th>
          <th className="text-left px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-ink-faint hidden sm:table-cell">Reason</th>
          <th className="text-left px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-ink-faint hidden md:table-cell">Added</th>
          <th className="px-2 py-1.5 w-8" />
        </tr>
      </thead>
      <tbody>
        {bans.map((b, i) => (
          <tr key={b.ip} className={`border-b border-panel-subtle last:border-0 ${i % 2 === 0 ? 'bg-panel-elevated/20' : ''}`}>
            <td className="px-2 py-2 font-mono text-bad-light">{b.ip}</td>
            <td className="px-2 py-2 text-ink-muted hidden sm:table-cell">{b.reason || '—'}</td>
            <td className="px-2 py-2 text-ink-faint hidden md:table-cell">
              {b.created_at ? new Date(b.created_at).toLocaleDateString() : '—'}
            </td>
            <td className="px-2 py-2">
              <button
                onClick={() => onUnban(b.ip)}
                className="p-1 rounded text-ink-faint hover:text-ok-light hover:bg-ok/10 transition-colors"
                title="Unban"
              >
                <X size={12} />
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Firewall Rule Row ─────────────────────────────────────────────────────────
function FirewallRow({ rule, onDelete, idx }) {
  return (
    <tr className={`border-b border-panel-subtle last:border-0 ${idx % 2 === 0 ? 'bg-panel-elevated/20' : ''}`}>
      <td className="px-3 py-2">
        <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-semibold border ${
          rule.action === 'allow'
            ? 'bg-ok/10 text-ok border-ok/25'
            : 'bg-bad/10 text-bad-light border-bad/25'
        }`}>{rule.action?.toUpperCase()}</span>
      </td>
      <td className="px-3 py-2 font-mono text-[12px] text-ink-primary">{rule.ip || 'any'}</td>
      <td className="px-3 py-2 text-[12px] text-ink-muted">{rule.port || 'any'}</td>
      <td className="px-3 py-2 text-[12px] text-ink-faint hidden sm:table-cell">{rule.protocol || 'any'}</td>
      <td className="px-3 py-2 text-[11px] text-ink-faint hidden md:table-cell">{rule.comment || '—'}</td>
      <td className="px-3 py-2">
        <button
          onClick={() => onDelete(rule.id)}
          className="p-1 rounded text-ink-faint hover:text-bad-light hover:bg-bad/10 transition-colors"
          title="Delete rule"
        >
          <X size={12} />
        </button>
      </td>
    </tr>
  );
}

// ── Add IP Ban dialog ─────────────────────────────────────────────────────────
function AddBanDialog({ onAdd, onClose }) {
  const [ip, setIp]         = useState('');
  const [reason, setReason] = useState('');
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-panel-card border border-panel-subtle rounded-2xl shadow-2xl w-full max-w-sm p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Ban size={16} className="text-bad-light" />
          <h3 className="text-[14px] font-semibold text-ink-primary">Ban IP Address</h3>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-[11px] text-ink-muted block mb-1">IP Address / CIDR</label>
            <input
              value={ip}
              onChange={e => setIp(e.target.value)}
              placeholder="e.g. 1.2.3.4 or 10.0.0.0/24"
              className="w-full bg-panel-elevated border border-panel-subtle rounded-lg px-3 py-2 text-[13px] text-ink-primary focus:outline-none focus:border-brand"
              autoFocus
            />
          </div>
          <div>
            <label className="text-[11px] text-ink-muted block mb-1">Reason (optional)</label>
            <input
              value={reason}
              onChange={e => setReason(e.target.value)}
              placeholder="Spam, brute force, etc."
              className="w-full bg-panel-elevated border border-panel-subtle rounded-lg px-3 py-2 text-[13px] text-ink-primary focus:outline-none focus:border-brand"
            />
          </div>
        </div>
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-3 py-1.5 rounded-lg bg-panel-elevated hover:bg-panel-subtle text-ink-secondary text-[12px] transition-colors">Cancel</button>
          <button
            onClick={() => { if (ip.trim()) { onAdd(ip.trim(), reason); onClose(); }}}
            disabled={!ip.trim()}
            className="px-3 py-1.5 rounded-lg bg-bad/80 hover:bg-bad text-white text-[12px] transition-colors disabled:opacity-40"
          >Ban IP</button>
        </div>
      </div>
    </div>
  );
}

// ── Add Firewall Rule dialog ──────────────────────────────────────────────────
function AddRuleDialog({ onAdd, onClose }) {
  const [form, setForm] = useState({ action: 'deny', ip: '', port: '', protocol: 'tcp', comment: '' });
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}
      onClick={e => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-panel-card border border-panel-subtle rounded-2xl shadow-2xl w-full max-w-sm p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Flame size={16} className="text-brand" />
          <h3 className="text-[14px] font-semibold text-ink-primary">Add Firewall Rule</h3>
        </div>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[11px] text-ink-muted block mb-1">Action</label>
              <select value={form.action} onChange={set('action')} className="w-full bg-panel-elevated border border-panel-subtle rounded-lg px-2 py-2 text-[12px] text-ink-primary focus:outline-none focus:border-brand">
                <option value="allow">Allow</option>
                <option value="deny">Deny</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] text-ink-muted block mb-1">Protocol</label>
              <select value={form.protocol} onChange={set('protocol')} className="w-full bg-panel-elevated border border-panel-subtle rounded-lg px-2 py-2 text-[12px] text-ink-primary focus:outline-none focus:border-brand">
                <option value="tcp">TCP</option>
                <option value="udp">UDP</option>
                <option value="both">Both</option>
              </select>
            </div>
          </div>
          {[
            { k: 'ip',      label: 'Source IP / CIDR (blank = any)', placeholder: '192.168.0.0/24' },
            { k: 'port',    label: 'Port (blank = any)',              placeholder: '80, 443, 22-25'  },
            { k: 'comment', label: 'Comment (optional)',              placeholder: 'Block port scan'  },
          ].map(({ k, label, placeholder }) => (
            <div key={k}>
              <label className="text-[11px] text-ink-muted block mb-1">{label}</label>
              <input
                value={form[k]} onChange={set(k)} placeholder={placeholder}
                className="w-full bg-panel-elevated border border-panel-subtle rounded-lg px-3 py-2 text-[12px] text-ink-primary focus:outline-none focus:border-brand"
              />
            </div>
          ))}
        </div>
        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="px-3 py-1.5 rounded-lg bg-panel-elevated hover:bg-panel-subtle text-ink-secondary text-[12px] transition-colors">Cancel</button>
          <button
            onClick={() => { onAdd(form); onClose(); }}
            className="px-3 py-1.5 rounded-lg bg-brand hover:bg-brand/80 text-white text-[12px] transition-colors"
          >Add Rule</button>
        </div>
      </div>
    </div>
  );
}

// ── API Reference data ────────────────────────────────────────────────────────
const METHOD_STYLE = {
  GET:    'bg-ok/10 text-ok border-ok/25',
  POST:   'bg-brand/10 text-brand-light border-brand/25',
  PATCH:  'bg-warn/10 text-warn-light border-warn/25',
  PUT:    'bg-warn/10 text-warn-light border-warn/25',
  DELETE: 'bg-bad/10 text-bad-light border-bad/25',
  WS:     'bg-violet/10 text-violet-light border-violet/25',
};

const API_GROUPS = [
  {
    tag: 'Auth', prefix: '/api/auth', endpoints: [
      { method: 'POST',   path: '/token',     desc: 'Login — returns access + refresh JWT' },
      { method: 'POST',   path: '/register',  desc: 'Create new user account' },
      { method: 'GET',    path: '/me',        desc: 'Current authenticated user info' },
    ],
  },
  {
    tag: 'Users', prefix: '/api/users', endpoints: [
      { method: 'GET',    path: '/',           desc: 'List all users (admin+)' },
      { method: 'GET',    path: '/{user_id}',  desc: 'Get user details' },
      { method: 'PATCH',  path: '/{user_id}',  desc: 'Update user (role, quotas, password)' },
      { method: 'DELETE', path: '/{user_id}',  desc: 'Delete user' },
    ],
  },
  {
    tag: 'Domains', prefix: '/api/domains', endpoints: [
      { method: 'GET',    path: '/',                    desc: 'List domains (own or all for admin)' },
      { method: 'POST',   path: '/',                    desc: 'Create domain + provision DNS' },
      { method: 'PATCH',  path: '/{domain_id}',         desc: 'Update domain (PHP version, SSL, etc.)' },
      { method: 'DELETE', path: '/{domain_id}',         desc: 'Delete domain + deprovision DNS' },
      { method: 'POST',   path: '/{domain_id}/reset-dns', desc: 'Wipe and rebuild DNS zone from scratch' },
      { method: 'POST',   path: '/{domain_id}/set-master', desc: 'Set as master/panel domain (superadmin)' },
    ],
  },
  {
    tag: 'Docker / Containers', prefix: '/api/docker', endpoints: [
      { method: 'GET',    path: '/containers',                        desc: 'List all containers on webpanel_net' },
      { method: 'GET',    path: '/containers/{domain}',               desc: 'Container details' },
      { method: 'POST',   path: '/containers/{domain}/create',        desc: 'Create site container for domain' },
      { method: 'DELETE', path: '/containers/{domain}',               desc: 'Stop + remove container' },
      { method: 'POST',   path: '/containers/{domain}/action',        desc: 'start / stop / restart / pause' },
      { method: 'GET',    path: '/containers/{domain}/logs',          desc: 'Tail container logs' },
      { method: 'GET',    path: '/containers/{domain}/stats',         desc: 'CPU/memory live stats' },
      { method: 'GET',    path: '/containers/{domain}/ports',         desc: 'Port assignments' },
      { method: 'GET',    path: '/containers/{domain}/ssh-info',      desc: 'SSH connection commands' },
      { method: 'POST',   path: '/containers/{domain}/inject-panel-key', desc: 'Inject panel SSH key' },
      { method: 'POST',   path: '/containers/{domain}/webuser-ssh-key',  desc: 'Set customer SSH key' },
      { method: 'POST',   path: '/containers/{domain}/admin-ssh-key',    desc: 'Inject admin SSH key' },
      { method: 'DELETE', path: '/containers/{domain}/admin-ssh-key',    desc: 'Revoke admin SSH key' },
      { method: 'GET',    path: '/php-versions',                     desc: 'List built PHP image versions' },
      { method: 'POST',   path: '/php-versions/check-updates',       desc: 'Check for new PHP versions' },
      { method: 'POST',   path: '/php-versions/build',               desc: 'Build a specific PHP version' },
      { method: 'GET',    path: '/stats',                            desc: 'Docker daemon resource stats' },
    ],
  },
  {
    tag: 'Container Proxy', prefix: '/api/container', endpoints: [
      { method: 'GET',    path: '/{domain}/health',               desc: 'Container health check' },
      { method: 'GET',    path: '/{domain}/info',                 desc: 'Disk + service status' },
      { method: 'GET',    path: '/{domain}/services',             desc: 'List supervisord programs' },
      { method: 'POST',   path: '/{domain}/services/{program}',   desc: 'start/stop/restart service' },
      { method: 'GET',    path: '/{domain}/files',                desc: 'Browse webroot files' },
      { method: 'POST',   path: '/{domain}/exec',                 desc: 'Run whitelisted command (admin)' },
      { method: 'GET',    path: '/{domain}/backups/{area}',       desc: 'List config backups' },
      { method: 'POST',   path: '/{domain}/restore/{area}',       desc: 'Restore config snapshot (admin)' },
      { method: 'POST',   path: '/{domain}/sftp/create',          desc: 'Create/reset SFTP user' },
      { method: 'GET',    path: '/{domain}/sftp/info',            desc: 'SFTP connection info' },
      { method: 'DELETE', path: '/{domain}/sftp/revoke',          desc: 'Revoke SFTP access (admin)' },
      { method: 'POST',   path: '/{domain}/secure/ssl',           desc: 'Upload SSL cert + key (admin)' },
      { method: 'GET',    path: '/{domain}/site-backup/list',     desc: 'List full site backups' },
      { method: 'POST',   path: '/{domain}/site-backup/create',   desc: 'Create full site backup' },
      { method: 'DELETE', path: '/{domain}/site-backup/{fn}',     desc: 'Delete backup file (admin)' },
      { method: 'GET',    path: '/{domain}/site-backup/download/{fn}', desc: 'Stream backup download' },
    ],
  },
  {
    tag: 'Server / Infrastructure', prefix: '/api/server', endpoints: [
      { method: 'GET',    path: '/stats',                   desc: 'CPU, memory, disk, network stats' },
      { method: 'GET',    path: '/services',                desc: 'Docker service container states' },
      { method: 'POST',   path: '/services/{svc}/{action}', desc: 'start/stop/restart a master service' },
      { method: 'GET',    path: '/diagnostic',              desc: 'Full system diagnostic + TCP checks' },
      { method: 'WS',     path: '/ws/stats',               desc: 'Live stats stream (2s interval, auth required)' },
    ],
  },
  {
    tag: 'DNS', prefix: '/api/dns', endpoints: [
      { method: 'GET',    path: '/zones',               desc: 'List all DNS zones' },
      { method: 'GET',    path: '/zones/{zone}',        desc: 'Zone details + records' },
      { method: 'POST',   path: '/zones',               desc: 'Create DNS zone' },
      { method: 'POST',   path: '/zones/{zone}/records', desc: 'Add/replace DNS record' },
      { method: 'DELETE', path: '/zones/{zone}/records', desc: 'Delete DNS record' },
      { method: 'PATCH',  path: '/zones/{zone}/kind',   desc: 'Switch zone kind (Native/Master/Slave)' },
      { method: 'POST',   path: '/zones/{zone}/ensure', desc: 'Create zone if not exists' },
      { method: 'GET',    path: '/lookup/{domain}',     desc: 'External DNS lookup via 8.8.8.8' },
      { method: 'GET',    path: '/sync',                desc: 'Last DNS sync result' },
      { method: 'POST',   path: '/sync',                desc: 'Trigger manual DNS sync (superadmin)' },
      { method: 'GET',    path: '/ns-sync',             desc: 'NS IP sync status (superadmin)' },
      { method: 'POST',   path: '/ns-sync',             desc: 'Force NS IP sync (superadmin)' },
      { method: 'POST',   path: '/dkim/{domain}/rotate', desc: 'Rotate DKIM key for domain (superadmin)' },
    ],
  },
  {
    tag: 'Security', prefix: '/api/security', endpoints: [
      { method: 'GET',    path: '/check/{domain}',     desc: 'SSL/headers/port security scan' },
      { method: 'POST',   path: '/fix/{domain}',       desc: 'Auto-fix a security issue' },
      { method: 'GET',    path: '/threats',            desc: 'CISA Known Exploited Vulnerabilities feed' },
      { method: 'DELETE', path: '/threats/cache',      desc: 'Bust the threat intel cache' },
      { method: 'GET',    path: '/suggest/domains',    desc: 'Domains with security issues' },
      { method: 'GET',    path: '/ip-bans',            desc: 'List banned IPs' },
      { method: 'POST',   path: '/ip-bans',            desc: 'Ban an IP or CIDR' },
      { method: 'DELETE', path: '/ip-bans/{ip}',       desc: 'Remove IP ban' },
      { method: 'GET',    path: '/firewall',           desc: 'List firewall rules' },
      { method: 'POST',   path: '/firewall',           desc: 'Add firewall rule' },
      { method: 'DELETE', path: '/firewall/{id}',      desc: 'Delete firewall rule' },
      { method: 'WS',     path: '/ws/{domain}',        desc: 'Live security check stream' },
    ],
  },
  {
    tag: 'Marketplace', prefix: '/api/marketplace', endpoints: [
      { method: 'GET',    path: '/apps',                            desc: 'Full app catalogue' },
      { method: 'GET',    path: '/my-installs',                     desc: 'User installed apps' },
      { method: 'GET',    path: '/installed/{domain}',              desc: 'Apps installed on domain' },
      { method: 'POST',   path: '/install',                         desc: 'Install app to domain' },
      { method: 'GET',    path: '/install/status/{domain}/{job_id}', desc: 'Installation job status' },
      { method: 'DELETE', path: '/installed/{domain}/{app_id}',     desc: 'Remove installed app' },
      { method: 'POST',   path: '/installed/{domain}/{app_id}/repair', desc: 'Repair install' },
      { method: 'POST',   path: '/installed/{domain}/{app_id}/reset',  desc: 'Reset install' },
      { method: 'GET',    path: '/templates',                       desc: 'Site templates' },
      { method: 'POST',   path: '/templates/apply',                 desc: 'Apply template' },
      { method: 'GET',    path: '/cache',                           desc: 'App cache status' },
      { method: 'POST',   path: '/cache/refresh',                   desc: 'Refresh all cached apps' },
      { method: 'POST',   path: '/cache/refresh/{app_id}',          desc: 'Refresh one cached app' },
      { method: 'DELETE', path: '/cache/{app_id}',                  desc: 'Purge cached app' },
    ],
  },
  {
    tag: 'AI Assistant', prefix: '/api/ai', endpoints: [
      { method: 'GET',    path: '/providers',              desc: 'List configured AI providers' },
      { method: 'POST',   path: '/providers',              desc: 'Add/update AI provider key' },
      { method: 'DELETE', path: '/providers/{name}',       desc: 'Remove AI provider' },
      { method: 'POST',   path: '/start/{domain}',         desc: 'Start AI session for domain' },
      { method: 'DELETE', path: '/stop/{domain}',          desc: 'Stop AI session' },
      { method: 'WS',     path: '/ws/{domain}/{agent_id}', desc: 'AI chat WebSocket relay' },
      { method: 'GET',    path: '/admin/sessions',         desc: 'All active AI sessions (admin)' },
      { method: 'GET',    path: '/admin/settings',         desc: 'Global AI settings (admin)' },
      { method: 'PATCH',  path: '/admin/settings',         desc: 'Update AI settings (admin)' },
    ],
  },
  {
    tag: 'Notifications', prefix: '/api/notifications', endpoints: [
      { method: 'GET',    path: '/unread-count', desc: 'Unread notification count (badge)' },
      { method: 'GET',    path: '/',             desc: 'List 200 most recent notifications' },
      { method: 'POST',   path: '/{id}/read',    desc: 'Mark notification as read' },
      { method: 'POST',   path: '/read-all',     desc: 'Mark all notifications read' },
      { method: 'DELETE', path: '/{id}',         desc: 'Delete single notification' },
      { method: 'DELETE', path: '/',             desc: 'Clear all notifications' },
    ],
  },
  {
    tag: 'Logs / Terminal', prefix: '/api', endpoints: [
      { method: 'GET',    path: '/logs/sources',     desc: 'Available log sources' },
      { method: 'GET',    path: '/logs/{source}',    desc: 'Read log lines (tail + search)' },
      { method: 'GET',    path: '/logs/{source}/download', desc: 'Download log file' },
      { method: 'WS',     path: '/terminal/ws',     desc: 'PTY WebSocket terminal' },
      { method: 'GET',    path: '/log/me',           desc: 'My request audit log' },
      { method: 'DELETE', path: '/log/me',           desc: 'Clear my audit log' },
      { method: 'GET',    path: '/log/user/{id}',    desc: 'User audit log (admin)' },
    ],
  },
  {
    tag: 'Admin', prefix: '/api', endpoints: [
      { method: 'GET',    path: '/services/catalogue',           desc: 'Master service catalogue' },
      { method: 'GET',    path: '/services/{domain}',            desc: 'Per-domain service status' },
      { method: 'POST',   path: '/services/{domain}/{svc_id}',   desc: 'Install service to domain' },
      { method: 'POST',   path: '/admin/content/pin/set',        desc: 'Set content viewer PIN' },
      { method: 'POST',   path: '/admin/content/pin/verify',     desc: 'Verify PIN, get content token' },
      { method: 'GET',    path: '/admin/content/domains',        desc: 'Browse customer domains' },
      { method: 'GET',    path: '/admin/content/domains/{d}/files', desc: 'Browse domain files' },
      { method: 'GET',    path: '/admin/content/domains/{d}/read',  desc: 'Read domain file (text, ≤512KB)' },
      { method: 'GET',    path: '/localdns/hosts',               desc: 'Local DNS hosts file content' },
      { method: 'POST',   path: '/localdns/sync',                desc: 'Sync local DNS hosts from DB' },
      { method: 'GET',    path: '/localdns/setup',               desc: 'Local DNS setup instructions' },
    ],
  },
];

// ── API Reference component ───────────────────────────────────────────────────
function ApiReference() {
  const [search, setSearch]     = useState('');
  const [expanded, setExpanded] = useState(null);

  const filtered = API_GROUPS.map(g => ({
    ...g,
    endpoints: g.endpoints.filter(ep =>
      !search || ep.path.toLowerCase().includes(search.toLowerCase()) ||
      ep.desc.toLowerCase().includes(search.toLowerCase()) ||
      g.tag.toLowerCase().includes(search.toLowerCase())
    ),
  })).filter(g => g.endpoints.length > 0);

  return (
    <div className="space-y-4">
      {/* Search */}
      <div className="relative">
        <Code2 size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Filter endpoints, paths, descriptions…"
          className="w-full bg-panel-elevated border border-panel-subtle rounded-xl pl-8 pr-3 py-2 text-[12px] text-ink-primary focus:outline-none focus:border-brand"
        />
        {search && (
          <button onClick={() => setSearch('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-faint hover:text-ink-muted">
            <X size={12} />
          </button>
        )}
      </div>

      {/* Groups */}
      {filtered.map(group => (
        <div key={group.tag} className="bg-panel-card border border-panel-subtle rounded-xl overflow-hidden">
          <button
            className="w-full flex items-center justify-between px-4 py-3 text-left border-b border-panel-subtle bg-panel-elevated/40 hover:bg-panel-elevated/60 transition-colors"
            onClick={() => setExpanded(expanded === group.tag ? null : group.tag)}
          >
            <div className="flex items-center gap-2">
              <Tag size={12} className="text-brand" />
              <span className="text-[12px] font-semibold text-ink-primary">{group.tag}</span>
              <span className="text-[10px] text-ink-faint font-mono">{group.prefix}</span>
              <span className="text-[10px] bg-brand/10 text-brand px-1.5 py-0.5 rounded-full">{group.endpoints.length}</span>
            </div>
            <ChevronRight size={13} className={`text-ink-faint transition-transform ${expanded === group.tag ? 'rotate-90' : ''}`} />
          </button>

          {(expanded === group.tag || !!search) && (
            <div className="divide-y divide-panel-subtle/50">
              {group.endpoints.map((ep, i) => (
                <div
                  key={i}
                  className={`flex items-start gap-3 px-4 py-2.5 ${i % 2 === 0 ? 'bg-panel-elevated/10' : ''}`}
                >
                  <span className={`flex-shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded border mt-0.5 ${METHOD_STYLE[ep.method] ?? METHOD_STYLE.GET}`}>
                    {ep.method}
                  </span>
                  <div className="flex-1 min-w-0">
                    <code className="text-[12px] font-mono text-ink-secondary">
                      {group.prefix}{ep.path}
                    </code>
                    <p className="text-[11px] text-ink-faint mt-0.5">{ep.desc}</p>
                  </div>
                  {ep.method === 'WS' && (
                    <Lock size={11} className="text-ink-faint flex-shrink-0 mt-1" title="Requires auth token" />
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}

      {filtered.length === 0 && (
        <div className="flex flex-col items-center py-12 text-ink-muted gap-2">
          <Code2 size={24} />
          <span className="text-[13px]">No endpoints match "{search}"</span>
        </div>
      )}
    </div>
  );
}

// ── Domain selector (for Domain Rules tab) ────────────────────────────────────
function DomainRulesTab() {
  const [domains,     setDomains]     = useState([]);
  const [selected,    setSelected]    = useState(null);
  const [loadingList, setLoadingList] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get('/api/domains/');
        setDomains(Array.isArray(data) ? data : data.domains ?? []);
      } catch {
        // non-fatal
      } finally {
        setLoadingList(false);
      }
    })();
  }, []);

  if (loadingList) return (
    <div className="flex items-center justify-center py-12">
      <div className="w-5 h-5 border-2 border-brand border-t-transparent rounded-full animate-spin" />
    </div>
  );

  return (
    <div className="space-y-4">
      {/* Domain picker */}
      <div className="bg-panel-card border border-panel-subtle rounded-2xl p-4">
        <p className="text-[12px] text-ink-muted mb-3">
          Select a domain to manage its IP and country access rules.
          Rules apply at the Traefik layer — your master server IPs are always whitelisted.
        </p>
        <div className="flex flex-wrap gap-2">
          {domains.length === 0 && (
            <span className="text-[12px] text-ink-faint">No domains found</span>
          )}
          {domains.map(d => (
            <button
              key={d.id}
              onClick={() => setSelected(d)}
              className={`px-3 py-1.5 rounded-lg text-[12px] font-medium border transition-colors ${
                selected?.id === d.id
                  ? 'bg-brand/15 text-brand border-brand/30'
                  : 'bg-panel-elevated text-ink-secondary border-panel-subtle hover:border-brand/30'
              }`}
            >
              {d.name}
            </button>
          ))}
        </div>
      </div>

      {selected && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <ShieldOff size={14} className="text-brand" />
            <span className="text-[13px] font-semibold text-ink-primary">
              Access Rules — <span className="text-brand font-mono">{selected.name}</span>
            </span>
          </div>
          <DomainAccessRules domainId={selected.id} domainName={selected.name} />
        </div>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function NetworkingPage() {
  const [tab,          setTab]          = useState('overview');
  const [netInfo,      setNetInfo]      = useState(null);
  const [bans,         setBans]         = useState([]);
  const [rules,        setRules]        = useState([]);
  const [loading,      setLoading]      = useState(true);
  const [showAddBan,   setShowAddBan]   = useState(false);
  const [showAddRule,  setShowAddRule]  = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, bansRes, rulesRes] = await Promise.all([
        api.get('/api/server/stats'),
        api.get('/api/security/ip-bans').catch(() => ({ data: [] })),
        api.get('/api/security/firewall').catch(() => ({ data: [] })),
      ]);
      setNetInfo(statsRes.data);
      setBans(Array.isArray(bansRes.data) ? bansRes.data : []);
      setRules(Array.isArray(rulesRes.data) ? rulesRes.data : []);
    } catch {
      toast.error('Failed to load network info');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const addBan = async (ip, reason) => {
    try {
      await api.post('/api/security/ip-bans', { ip, reason });
      toast.success(`Banned ${ip}`);
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to ban IP');
    }
  };

  const unban = async (ip) => {
    try {
      await api.delete(`/api/security/ip-bans/${encodeURIComponent(ip)}`);
      toast.success(`Unbanned ${ip}`);
      setBans(prev => prev.filter(b => b.ip !== ip));
    } catch {
      toast.error('Failed to unban IP');
    }
  };

  const addRule = async (form) => {
    try {
      await api.post('/api/security/firewall', form);
      toast.success('Firewall rule added');
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to add rule');
    }
  };

  const deleteRule = async (id) => {
    try {
      await api.delete(`/api/security/firewall/${id}`);
      toast.success('Rule removed');
      setRules(prev => prev.filter(r => r.id !== id));
    } catch {
      toast.error('Failed to delete rule');
    }
  };

  const external = netInfo?.external_ip ?? '—';
  const internals = netInfo?.internal_ips ?? [];
  const netIf = netInfo?.net_interfaces ?? {};

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-brand/15 flex items-center justify-center">
            <Network size={18} className="text-brand" />
          </div>
          <div>
            <h1 className="text-[17px] font-bold text-ink-primary">Networking</h1>
            <p className="text-[11px] text-ink-muted">IP info · Firewall · IP Ban · API Reference</p>
          </div>
        </div>
        <button
          onClick={load}
          className="p-2 rounded-lg text-ink-muted hover:text-ink-primary hover:bg-panel-elevated transition-colors"
          title="Refresh"
        >
          <RefreshCw size={14} />
        </button>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 bg-panel-elevated/40 rounded-xl p-1 w-fit border border-panel-subtle">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-medium transition-colors ${
              tab === t.id
                ? 'bg-panel-card text-ink-primary shadow-sm border border-panel-subtle'
                : 'text-ink-muted hover:text-ink-secondary'
            }`}
          >
            <t.icon size={12} />
            {t.label}
          </button>
        ))}
      </div>

      {/* Overview tab */}
      {tab === 'overview' && (
        <>
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <div className="w-6 h-6 border-2 border-brand border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <>
              {/* IP Info */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <Card icon={Globe} title="IP Addresses">
                  <IpRow
                    label="External / Public IP"
                    value={external}
                    badge="Public"
                    badgeColor="bg-ok/10 text-ok border-ok/25"
                  />
                  {internals.map(ip => (
                    <IpRow key={ip} label="Internal" value={ip}
                      badge="LAN" badgeColor="bg-brand/10 text-brand border-brand/25" />
                  ))}
                </Card>

                <Card icon={Wifi} title="Network Interfaces">
                  {Object.entries(netIf).length > 0 ? (
                    <div className="space-y-2">
                      {Object.entries(netIf).slice(0, 6).map(([iface, n]) => (
                        <div key={iface} className="flex items-center justify-between bg-panel-elevated/50 rounded-lg px-3 py-2">
                          <span className="text-[12px] font-mono text-ink-secondary">{iface}</span>
                          <div className="flex items-center gap-3 text-[11px] text-ink-muted">
                            <span className="flex items-center gap-0.5"><ArrowUp size={10} className="text-ok" />{n.sent_mb}MB</span>
                            <span className="flex items-center gap-0.5"><ArrowDown size={10} className="text-brand" />{n.recv_mb}MB</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="flex flex-col items-center py-6 gap-2 text-ink-muted">
                      <Wifi size={20} />
                      <span className="text-[12px]">No interface data available</span>
                    </div>
                  )}
                </Card>
              </div>

              {/* IP Ban */}
              <Card
                icon={Ban}
                title={`IP Ban List (${bans.length})`}
                action={
                  <button
                    onClick={() => setShowAddBan(true)}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-bad/10 hover:bg-bad/20 text-bad-light text-[11px] transition-colors"
                  >
                    <Plus size={11} /> Ban IP
                  </button>
                }
              >
                <IpBanTable bans={bans} onUnban={unban} />
              </Card>

              {/* Firewall Rules */}
              <Card
                icon={Flame}
                title={`Firewall Rules (${rules.length})`}
                action={
                  <button
                    onClick={() => setShowAddRule(true)}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-brand/10 hover:bg-brand/20 text-brand text-[11px] transition-colors"
                  >
                    <Plus size={11} /> Add Rule
                  </button>
                }
              >
                {rules.length === 0 ? (
                  <div className="flex flex-col items-center py-8 gap-2 text-ink-muted">
                    <Shield size={22} className="text-ok" />
                    <span className="text-[12px]">No custom firewall rules</span>
                    <span className="text-[11px] text-ink-faint">Default policy applies</span>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-[12px]">
                      <thead>
                        <tr className="border-b border-panel-subtle">
                          <th className="text-left px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-ink-faint">Action</th>
                          <th className="text-left px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-ink-faint">Source IP</th>
                          <th className="text-left px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-ink-faint">Port</th>
                          <th className="text-left px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-ink-faint hidden sm:table-cell">Proto</th>
                          <th className="text-left px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-ink-faint hidden md:table-cell">Comment</th>
                          <th className="px-3 py-2 w-8" />
                        </tr>
                      </thead>
                      <tbody>
                        {rules.map((r, i) => (
                          <FirewallRow key={r.id} rule={r} onDelete={deleteRule} idx={i} />
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            </>
          )}
        </>
      )}

      {/* Domain Rules tab */}
      {tab === 'domain-acl' && <DomainRulesTab />}

      {/* API Reference tab */}
      {tab === 'api' && <ApiReference />}

      {/* Dialogs */}
      {showAddBan  && <AddBanDialog  onAdd={addBan}  onClose={() => setShowAddBan(false)}  />}
      {showAddRule && <AddRuleDialog onAdd={addRule} onClose={() => setShowAddRule(false)} />}
    </div>
  );
}
