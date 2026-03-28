/**
 * DomainAccessRules — per-domain IP and country blocking panel.
 *
 * Used from DomainsPage (per-domain accordion) and NetworkingPage.
 * Standard users can only manage their own domains.
 * Master IPs (Docker bridge + server external IP) are always shown as
 * permanently whitelisted and cannot be blocked.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  Shield, Globe, Plus, X, RefreshCw, Ban, Flag,
  AlertTriangle, CheckCircle2, Search, ChevronDown, ChevronUp,
} from 'lucide-react';
import api from '../utils/api';
import { toast } from '../utils/toast';

// ── Small helpers ─────────────────────────────────────────────────────────────
function Badge({ children, color = 'brand' }) {
  const map = {
    brand:  'bg-brand/10 text-brand border-brand/25',
    ok:     'bg-ok/10 text-ok border-ok/25',
    bad:    'bg-bad/10 text-bad-light border-bad/25',
    warn:   'bg-warn/10 text-warn-light border-warn/25',
    muted:  'bg-panel-elevated text-ink-muted border-panel-subtle',
  };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded-full border font-semibold ${map[color] ?? map.brand}`}>
      {children}
    </span>
  );
}

// ── Country flag image ─────────────────────────────────────────────────────────
function FlagImg({ code, name }) {
  const [err, setErr] = useState(false);
  if (err) return <span className="text-[11px] text-ink-faint">{code}</span>;
  return (
    <img
      src={`/api/geo/flag/${code.toLowerCase()}`}
      alt={name}
      title={name}
      className="w-6 h-4 object-cover rounded-sm border border-panel-subtle flex-shrink-0"
      onError={() => setErr(true)}
    />
  );
}

// ── Whitelist notice ──────────────────────────────────────────────────────────
function MasterWhitelistRow({ cidrs }) {
  return (
    <div className="flex flex-wrap gap-1.5 p-3 bg-ok/5 border border-ok/20 rounded-xl">
      <div className="flex items-center gap-1.5 w-full mb-1">
        <CheckCircle2 size={12} className="text-ok" />
        <span className="text-[11px] font-semibold text-ok">Always whitelisted (cannot be blocked)</span>
      </div>
      {cidrs.map(c => (
        <span key={c} className="text-[10px] font-mono bg-ok/10 text-ok px-2 py-0.5 rounded-full border border-ok/20">
          {c}
        </span>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function DomainAccessRules({ domainId, domainName }) {
  const [data,         setData]         = useState(null);   // {ip_rules, country_blocks, countries, master_whitelist}
  const [loading,      setLoading]      = useState(true);
  const [saving,       setSaving]       = useState(false);

  // Add IP rule dialog
  const [showAddIP,    setShowAddIP]    = useState(false);
  const [newIP,        setNewIP]        = useState('');
  const [newReason,    setNewReason]    = useState('');

  // Country search
  const [ccSearch,     setCcSearch]     = useState('');
  const [ccExpanded,   setCcExpanded]   = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: d } = await api.get(`/api/domains/${domainId}/access-rules`);
      setData(d);
    } catch {
      toast.error('Failed to load access rules');
    } finally {
      setLoading(false);
    }
  }, [domainId]);

  useEffect(() => { load(); }, [load]);

  const addIPRule = async () => {
    if (!newIP.trim()) return;
    setSaving(true);
    try {
      await api.post(`/api/domains/${domainId}/access-rules/ip`, {
        ip_cidr: newIP.trim(),
        reason:  newReason.trim(),
      });
      toast.success(`Blocked ${newIP.trim()}`);
      setNewIP('');
      setNewReason('');
      setShowAddIP(false);
      await load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Invalid IP or CIDR');
    } finally {
      setSaving(false);
    }
  };

  const removeIPRule = async (id, cidr) => {
    try {
      await api.delete(`/api/domains/${domainId}/access-rules/ip/${id}`);
      toast.success(`Removed block for ${cidr}`);
      setData(prev => ({ ...prev, ip_rules: prev.ip_rules.filter(r => r.id !== id) }));
    } catch {
      toast.error('Failed to remove rule');
    }
  };

  const toggleCountry = async (code, name, currentActive) => {
    setSaving(true);
    try {
      await api.patch(`/api/domains/${domainId}/access-rules/country/${code}`, {
        active: !currentActive,
      });
      toast.success(!currentActive ? `Blocked ${name}` : `Unblocked ${name}`);
      setData(prev => {
        const existing = prev.country_blocks.find(cb => cb.country_code === code);
        if (existing) {
          return {
            ...prev,
            country_blocks: prev.country_blocks.map(cb =>
              cb.country_code === code ? { ...cb, active: !currentActive } : cb
            ),
          };
        }
        return {
          ...prev,
          country_blocks: [
            ...prev.country_blocks,
            { id: Date.now(), country_code: code, country_name: name, active: true },
          ],
        };
      });
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to update country block');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-5 h-5 border-2 border-brand border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!data) return null;

  const blockedCodes = new Set(data.country_blocks.filter(cb => cb.active).map(cb => cb.country_code));
  const filteredCountries = (data.countries ?? []).filter(c =>
    !ccSearch || c.name.toLowerCase().includes(ccSearch.toLowerCase()) || c.code.toLowerCase().includes(ccSearch.toLowerCase())
  );
  // Show blocked-first, then rest (limited when not expanded)
  const sortedCountries = [
    ...filteredCountries.filter(c => blockedCodes.has(c.code)),
    ...filteredCountries.filter(c => !blockedCodes.has(c.code)),
  ];
  const visibleCountries = ccExpanded || ccSearch ? sortedCountries : sortedCountries.slice(0, 12);

  return (
    <div className="space-y-4">
      {/* Master whitelist notice */}
      {data.master_whitelist?.length > 0 && (
        <MasterWhitelistRow cidrs={data.master_whitelist} />
      )}

      {/* ── IP / CIDR Rules ── */}
      <div className="bg-panel-card border border-panel-subtle rounded-2xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-panel-subtle bg-panel-elevated/40">
          <div className="flex items-center gap-2">
            <Ban size={13} className="text-bad-light" />
            <span className="text-[13px] font-semibold text-ink-primary">
              Blocked IPs / CIDRs
            </span>
            <Badge color="bad">{data.ip_rules.filter(r => r.active).length}</Badge>
          </div>
          <button
            onClick={() => setShowAddIP(true)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-bad/10 hover:bg-bad/20 text-bad-light text-[11px] transition-colors"
          >
            <Plus size={11} /> Block IP
          </button>
        </div>

        <div className="p-4">
          {data.ip_rules.length === 0 ? (
            <div className="flex flex-col items-center py-6 gap-1.5 text-ink-muted">
              <Shield size={20} className="text-ok" />
              <span className="text-[12px]">No IP blocks — all IPs allowed</span>
            </div>
          ) : (
            <div className="space-y-1.5">
              {data.ip_rules.map(rule => (
                <div
                  key={rule.id}
                  className={`flex items-center justify-between px-3 py-2 rounded-lg border ${
                    rule.active
                      ? 'bg-bad/5 border-bad/15'
                      : 'bg-panel-elevated/30 border-panel-subtle opacity-50'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    <span className="font-mono text-[12px] text-bad-light">{rule.ip_cidr}</span>
                    {rule.reason && (
                      <span className="text-[11px] text-ink-faint truncate max-w-[200px]">{rule.reason}</span>
                    )}
                  </div>
                  <button
                    onClick={() => removeIPRule(rule.id, rule.ip_cidr)}
                    className="p-1 rounded text-ink-faint hover:text-ok hover:bg-ok/10 transition-colors"
                    title="Remove block"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Add IP dialog (inline) */}
          {showAddIP && (
            <div className="mt-3 p-3 bg-panel-elevated/60 border border-panel-subtle rounded-xl space-y-2.5">
              <input
                autoFocus
                value={newIP}
                onChange={e => setNewIP(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addIPRule()}
                placeholder="IP or CIDR, e.g. 1.2.3.4 or 10.0.0.0/8"
                className="w-full bg-panel-card border border-panel-subtle rounded-lg px-3 py-1.5 text-[12px] text-ink-primary font-mono focus:outline-none focus:border-bad/50"
              />
              <input
                value={newReason}
                onChange={e => setNewReason(e.target.value)}
                placeholder="Reason (optional)"
                className="w-full bg-panel-card border border-panel-subtle rounded-lg px-3 py-1.5 text-[12px] text-ink-primary focus:outline-none focus:border-panel-elevated"
              />
              <div className="flex gap-2">
                <button
                  onClick={addIPRule}
                  disabled={saving || !newIP.trim()}
                  className="flex-1 py-1.5 rounded-lg bg-bad/15 hover:bg-bad/25 text-bad-light text-[11px] font-semibold transition-colors disabled:opacity-50"
                >
                  Block
                </button>
                <button
                  onClick={() => { setShowAddIP(false); setNewIP(''); setNewReason(''); }}
                  className="px-3 py-1.5 rounded-lg bg-panel-elevated hover:bg-panel-elevated/80 text-ink-muted text-[11px] transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Country Blocking ── */}
      <div className="bg-panel-card border border-panel-subtle rounded-2xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-panel-subtle bg-panel-elevated/40">
          <div className="flex items-center gap-2">
            <Globe size={13} className="text-brand" />
            <span className="text-[13px] font-semibold text-ink-primary">Country Blocking</span>
            <Badge color={blockedCodes.size > 0 ? 'bad' : 'muted'}>{blockedCodes.size} blocked</Badge>
          </div>
          <div className="flex items-center gap-1.5">
            {saving && <div className="w-3 h-3 border border-brand border-t-transparent rounded-full animate-spin" />}
            <button onClick={load} className="p-1.5 rounded-lg text-ink-faint hover:text-ink-primary hover:bg-panel-elevated transition-colors" title="Refresh">
              <RefreshCw size={12} />
            </button>
          </div>
        </div>

        <div className="p-4 space-y-3">
          {/* Search */}
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-muted" />
            <input
              value={ccSearch}
              onChange={e => { setCcSearch(e.target.value); setCcExpanded(true); }}
              placeholder="Search country…"
              className="w-full bg-panel-elevated border border-panel-subtle rounded-lg pl-7 pr-3 py-1.5 text-[12px] text-ink-primary focus:outline-none focus:border-brand"
            />
            {ccSearch && (
              <button onClick={() => setCcSearch('')} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-faint">
                <X size={11} />
              </button>
            )}
          </div>

          {/* Country grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-1.5">
            {visibleCountries.map(c => {
              const isBlocked = blockedCodes.has(c.code);
              return (
                <button
                  key={c.code}
                  onClick={() => toggleCountry(c.code, c.name, isBlocked)}
                  disabled={saving}
                  className={`flex items-center gap-2 px-2.5 py-2 rounded-lg border text-left transition-colors disabled:opacity-60 ${
                    isBlocked
                      ? 'bg-bad/8 border-bad/20 text-bad-light hover:bg-bad/15'
                      : 'bg-panel-elevated/30 border-panel-subtle text-ink-secondary hover:bg-panel-elevated/60 hover:text-ink-primary'
                  }`}
                >
                  <FlagImg code={c.code} name={c.name} />
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] font-medium truncate">{c.name}</div>
                    <div className="text-[9px] text-ink-faint">{c.code}</div>
                  </div>
                  {isBlocked && <Ban size={10} className="flex-shrink-0 text-bad-light" />}
                </button>
              );
            })}
          </div>

          {/* Expand / collapse */}
          {!ccSearch && sortedCountries.length > 12 && (
            <button
              onClick={() => setCcExpanded(e => !e)}
              className="w-full flex items-center justify-center gap-1.5 py-1.5 text-[11px] text-ink-muted hover:text-ink-secondary transition-colors"
            >
              {ccExpanded ? <><ChevronUp size={12} /> Show less</> : <><ChevronDown size={12} /> Show all {sortedCountries.length} countries</>}
            </button>
          )}
        </div>
      </div>

      {/* Active country block list */}
      {blockedCodes.size > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {data.country_blocks.filter(cb => cb.active).map(cb => (
            <div
              key={cb.country_code}
              className="flex items-center gap-1.5 px-2.5 py-1 bg-bad/8 border border-bad/15 rounded-full"
            >
              <FlagImg code={cb.country_code} name={cb.country_name} />
              <span className="text-[11px] text-bad-light font-medium">{cb.country_name}</span>
              <button
                onClick={() => toggleCountry(cb.country_code, cb.country_name, true)}
                className="text-ink-faint hover:text-ok ml-0.5"
                title="Unblock"
              >
                <X size={10} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
