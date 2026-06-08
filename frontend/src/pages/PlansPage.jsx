import { useState, useEffect, useCallback } from 'react';
import { toast } from 'sonner';
import api from '../utils/api';
import {
  Package, Plus, Pencil, Trash2, RefreshCw, X, Check, GripVertical,
  DollarSign, HardDrive, Globe, Database, Mail, Cpu, Shield, Server,
} from 'lucide-react';

export default function PlansPage() {
  const [plans,    setPlans]   = useState([]);
  const [loading,  setLoading] = useState(true);
  const [editor,   setEditor]  = useState(null); // null | 'new' | plan id
  const [deleting, setDeleting] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/plans/');
      setPlans(data);
    } catch {
      toast.error('Failed to load plans');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const save = async (form) => {
    try {
      if (editor === 'new') {
        await api.post('/api/plans/', form);
        toast.success('Plan created');
      } else {
        await api.patch(`/api/plans/${editor}`, form);
        toast.success('Plan updated');
      }
      setEditor(null);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Save failed');
    }
  };

  const confirmDelete = async () => {
    try {
      await api.delete(`/api/plans/${deleting}`);
      toast.success('Plan deleted');
      setDeleting(null);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Delete failed');
    }
  };

  const editPlan = plans.find(p => p.id === editor);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-ink-primary flex items-center gap-2">
          <Package size={20} /> Hosting Plans
        </h1>
        <div className="flex gap-2">
          <button onClick={load} disabled={loading} className="btn-ghost">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
          <button onClick={() => setEditor('new')} className="btn-primary text-xs px-3 py-1.5 flex items-center gap-1.5">
            <Plus size={14} /> New Plan
          </button>
        </div>
      </div>

      {deleting && (
        <div className="card border-bad/30 bg-bad/5">
          <p className="text-sm text-ink-primary mb-3">Delete this plan? Users assigned to it will retain their current resource limits.</p>
          <div className="flex gap-2">
            <button onClick={confirmDelete} className="btn-primary bg-bad hover:bg-bad/80 border-bad/50 text-xs px-3 py-1.5">Delete</button>
            <button onClick={() => setDeleting(null)} className="btn-ghost text-xs px-3 py-1.5">Cancel</button>
          </div>
        </div>
      )}

      {editor && (
        <PlanForm
          plan={editPlan}
          onSave={save}
          onCancel={() => setEditor(null)}
        />
      )}

      {loading ? (
        <div className="text-center text-ink-muted py-12 text-sm">Loading...</div>
      ) : plans.length === 0 ? (
        <div className="text-center text-ink-muted py-12 text-sm">No plans yet. Create your first hosting plan.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {plans.map(plan => (
            <div key={plan.id} className={`card relative ${!plan.is_active ? 'opacity-50' : ''}`}>
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-semibold text-ink-primary">{plan.name}</h3>
                  {plan.description && (
                    <p className="text-xs text-ink-muted mt-0.5">{plan.description}</p>
                  )}
                </div>
                <div className="flex gap-1">
                  <button onClick={() => { setEditor(plan.id); }} className="text-ink-muted hover:text-brand transition-colors p-1 rounded">
                    <Pencil size={13} />
                  </button>
                  <button onClick={() => setDeleting(plan.id)} className="text-ink-muted hover:text-bad transition-colors p-1 rounded">
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>

              <div className="flex items-baseline gap-1 mb-3">
                <span className="text-2xl font-bold text-ink-primary">${plan.price_monthly}</span>
                <span className="text-xs text-ink-muted">/mo</span>
                {plan.price_yearly > 0 && (
                  <span className="text-xs text-ink-muted ml-2">${plan.price_yearly}/yr</span>
                )}
              </div>

              <div className="space-y-1.5 text-xs">
                <Row icon={<HardDrive size={12} />} label="Disk" value={plan.disk_quota_mb >= 1024 ? `${plan.disk_quota_mb / 1024} GB` : `${plan.disk_quota_mb} MB`} />
                <Row icon={<Globe size={12} />} label="Domains" value={String(plan.max_domains)} />
                <Row icon={<Database size={12} />} label="Databases" value={String(plan.max_databases)} />
                <Row icon={<Mail size={12} />} label="Email accounts" value={String(plan.max_emails)} />
                <Row icon={<Cpu size={12} />} label="Container" value={`${plan.container_memory_mb} MB / ${plan.container_cpus} CPU`} />
                <Row icon={<Server size={12} />} label="Bandwidth" value={plan.bw_quota_mb >= 1024 ? `${plan.bw_quota_mb / 1024} GB` : `${plan.bw_quota_mb} MB`} />
              </div>

              <div className="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-panel-border">
                <FeatureBadge enabled={plan.ssl_enabled} label="SSL" />
                <FeatureBadge enabled={plan.ssh_enabled} label="SSH" />
                <FeatureBadge enabled={plan.dns_management} label="DNS" />
                <FeatureBadge enabled={plan.email_hosting} label="Email" />
              </div>

              {!plan.is_active && (
                <div className="absolute top-2 right-2 text-xs px-2 py-0.5 rounded-full bg-warn/15 text-warn-light border border-warn/25">
                  Inactive
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Row({ icon, label, value }) {
  return (
    <div className="flex items-center gap-2 text-ink-secondary">
      <span className="text-ink-muted flex-shrink-0">{icon}</span>
      <span className="flex-1">{label}</span>
      <span className="text-ink-primary font-medium">{value}</span>
    </div>
  );
}

function FeatureBadge({ enabled, label }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full flex items-center gap-1 ${
      enabled ? 'bg-ok/15 text-ok-light border border-ok/25' : 'bg-panel-elevated text-ink-muted border border-panel-border'
    }`}>
      {enabled ? <Check size={10} /> : <X size={10} />}
      {label}
    </span>
  );
}

function PlanForm({ plan, onSave, onCancel }) {
  const [form, setForm] = useState(() => ({
    name: plan?.name || '',
    description: plan?.description || '',
    price_monthly: plan?.price_monthly ?? 0,
    price_yearly: plan?.price_yearly ?? 0,
    disk_quota_mb: plan?.disk_quota_mb ?? 5120,
    bw_quota_mb: plan?.bw_quota_mb ?? 51200,
    max_domains: plan?.max_domains ?? 10,
    max_databases: plan?.max_databases ?? 5,
    max_emails: plan?.max_emails ?? 20,
    container_memory_mb: plan?.container_memory_mb ?? 1024,
    container_cpus: plan?.container_cpus ?? 0.5,
    ssl_enabled: plan?.ssl_enabled ?? true,
    ssh_enabled: plan?.ssh_enabled ?? true,
    dns_management: plan?.dns_management ?? true,
    email_hosting: plan?.email_hosting ?? true,
    is_active: plan?.is_active ?? true,
    sort_order: plan?.sort_order ?? 0,
  }));

  const set = (field, val) => setForm(f => ({ ...f, [field]: val }));
  const toggle = field => set(field, !form[field]);

  const handleSubmit = e => {
    e.preventDefault();
    onSave(form);
  };

  return (
    <form onSubmit={handleSubmit} className="card space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink-primary">{plan ? 'Edit Plan' : 'New Plan'}</h2>
        <button type="button" onClick={onCancel} className="text-ink-muted hover:text-ink-primary transition-colors">
          <X size={16} />
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Field label="Plan name" value={form.name} onChange={v => set('name', v)} required />
        <div className="md:col-span-2">
          <label className="block text-xs text-ink-muted mb-1">Description</label>
          <input className="input text-xs" value={form.description} onChange={e => set('description', e.target.value)} />
        </div>
        <Field label="Monthly price ($)" type="number" value={form.price_monthly} onChange={v => set('price_monthly', parseFloat(v) || 0)} step="0.01" />
        <Field label="Yearly price ($)" type="number" value={form.price_yearly} onChange={v => set('price_yearly', parseFloat(v) || 0)} step="0.01" />
        <Field label="Disk quota (MB)" type="number" value={form.disk_quota_mb} onChange={v => set('disk_quota_mb', parseInt(v) || 0)} />
        <Field label="Bandwidth (MB)" type="number" value={form.bw_quota_mb} onChange={v => set('bw_quota_mb', parseInt(v) || 0)} />
        <Field label="Max domains" type="number" value={form.max_domains} onChange={v => set('max_domains', parseInt(v) || 0)} />
        <Field label="Max databases" type="number" value={form.max_databases} onChange={v => set('max_databases', parseInt(v) || 0)} />
        <Field label="Max email accounts" type="number" value={form.max_emails} onChange={v => set('max_emails', parseInt(v) || 0)} />
        <Field label="Container memory (MB)" type="number" value={form.container_memory_mb} onChange={v => set('container_memory_mb', parseInt(v) || 256)} />
        <Field label="Container CPUs" type="number" value={form.container_cpus} onChange={v => set('container_cpus', parseFloat(v) || 0.1)} step="0.1" />
        <Field label="Sort order" type="number" value={form.sort_order} onChange={v => set('sort_order', parseInt(v) || 0)} />
      </div>

      <div className="flex flex-wrap gap-3">
        <Toggle label="SSL certificates" enabled={form.ssl_enabled} onToggle={() => toggle('ssl_enabled')} />
        <Toggle label="SSH/SFTP access" enabled={form.ssh_enabled} onToggle={() => toggle('ssh_enabled')} />
        <Toggle label="DNS management" enabled={form.dns_management} onToggle={() => toggle('dns_management')} />
        <Toggle label="Email hosting" enabled={form.email_hosting} onToggle={() => toggle('email_hosting')} />
        <Toggle label="Active" enabled={form.is_active} onToggle={() => toggle('is_active')} />
      </div>

      <div className="flex gap-2 pt-2">
        <button type="submit" className="btn-primary text-xs px-4 py-1.5">{plan ? 'Update' : 'Create'}</button>
        <button type="button" onClick={onCancel} className="btn-ghost text-xs px-3 py-1.5">Cancel</button>
      </div>
    </form>
  );
}

function Field({ label, value, onChange, type = 'text', step, required }) {
  return (
    <div>
      <label className="block text-xs text-ink-muted mb-1">{label}</label>
      <input
        className="input text-xs"
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        step={step}
        required={required}
      />
    </div>
  );
}

function Toggle({ label, enabled, onToggle }) {
  return (
    <button type="button" onClick={onToggle} className={`text-xs px-3 py-1.5 rounded-full flex items-center gap-1.5 transition-colors ${
      enabled ? 'bg-ok/15 text-ok-light border border-ok/25' : 'bg-panel-elevated text-ink-muted border border-panel-border'
    }`}>
      {enabled ? <Check size={12} /> : <X size={12} />}
      {label}
    </button>
  );
}
