import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, ClipboardList, Send, Loader, CheckCircle,
  XCircle, FileText, Eye, Download, Trash2, Ban, Lock,
} from 'lucide-react';
import api from '../../utils/api';
import { toast } from 'sonner';

const DSAR_TYPES = [
  { value: 'access', label: 'Access My Data', icon: Eye, desc: 'Request a copy of all personal data we hold about you' },
  { value: 'erasure', label: 'Right to Erasure', icon: Trash2, desc: 'Request deletion of your personal data' },
  { value: 'portability', label: 'Data Portability', icon: Download, desc: 'Receive your data in a portable format' },
  { value: 'rectification', label: 'Rectification', icon: FileText, desc: 'Correct inaccurate or incomplete data' },
  { value: 'restrict', label: 'Restrict Processing', icon: Ban, desc: 'Limit how we process your data' },
  { value: 'object', label: 'Object to Processing', icon: Lock, desc: 'Object to data processing based on legitimate interests' },
];

export default function DataSubjectRequestPage() {
  const navigate = useNavigate();
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    request_type: 'access',
    description: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const loadRequests = async () => {
    try {
      const res = await api.get('/api/compliance/dsar');
      setRequests(res.data.requests || []);
    } catch {
      // Empty
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadRequests(); }, []);

  const submitRequest = async (e) => {
    e.preventDefault();
    if (!formData.description.trim()) {
      setError('Please describe your request.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.post('/api/compliance/dsar', formData);
      toast.success('Your request has been submitted.');
      setShowForm(false);
      setFormData({ request_type: 'access', description: '' });
      loadRequests();
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to submit request.');
    } finally {
      setSubmitting(false);
    }
  };

  const statusColor = (status) => {
    switch (status) {
      case 'completed': return 'text-ok bg-ok/10';
      case 'in_progress': return 'text-brand bg-brand/10';
      case 'pending': return 'text-amber-400 bg-amber-400/10';
      case 'rejected': return 'text-error bg-error/10';
      default: return 'text-ink-muted bg-panel-surface';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader className="w-6 h-6 text-brand animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="p-2 rounded-lg hover:bg-panel-hover text-ink-muted hover:text-ink-primary transition-colors"
        >
          <ArrowLeft size={20} />
        </button>
        <div className="w-10 h-10 rounded-xl bg-brand/10 flex items-center justify-center">
          <ClipboardList className="w-5 h-5 text-brand" />
        </div>
        <div className="flex-1">
          <h1 className="text-xl font-semibold text-ink-primary">Data Subject Access Request</h1>
          <p className="text-sm text-ink-muted">Exercise your data protection rights</p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                     bg-brand hover:bg-brand-hover text-white transition-colors"
        >
          <Send size={16} />
          New Request
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 px-4 py-3 bg-error/10 border border-error/20 rounded-lg">
          <XCircle size={18} className="text-error shrink-0" />
          <span className="text-sm text-error">{error}</span>
        </div>
      )}

      {/* New Request Form */}
      {showForm && (
        <form onSubmit={submitRequest} className="bg-panel-card border border-panel-subtle rounded-xl p-5 space-y-4">
          <h2 className="text-sm font-semibold text-ink-primary">Submit a Data Subject Request</h2>

          <div>
            <label className="block text-xs text-ink-muted mb-1">Request Type</label>
            <select
              value={formData.request_type}
              onChange={(e) => setFormData({ ...formData, request_type: e.target.value })}
              className="w-full px-3 py-2 rounded-lg bg-panel-surface border border-panel-subtle
                         text-ink-primary text-sm focus:outline-none focus:ring-2 focus:ring-brand/50"
            >
              {DSAR_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            <p className="text-xs text-ink-muted mt-1">
              {DSAR_TYPES.find((t) => t.value === formData.request_type)?.desc}
            </p>
          </div>

          <div>
            <label className="block text-xs text-ink-muted mb-1">Description</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Please describe your request in detail…"
              rows={4}
              className="w-full px-3 py-2 rounded-lg bg-panel-surface border border-panel-subtle
                         text-ink-primary placeholder-ink-muted text-sm resize-none
                         focus:outline-none focus:ring-2 focus:ring-brand/50"
            />
          </div>

          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={() => { setShowForm(false); setError(null); }}
              className="px-4 py-2 rounded-lg text-sm font-medium border border-panel-subtle
                         text-ink-muted hover:text-ink-primary hover:bg-panel-hover"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                         bg-brand hover:bg-brand-hover text-white transition-colors disabled:opacity-50"
            >
              {submitting ? (
                <><Loader size={16} className="animate-spin" /> Submitting…</>
              ) : (
                <><Send size={16} /> Submit Request</>
              )}
            </button>
          </div>
        </form>
      )}

      {/* Existing Requests */}
      {requests.length === 0 ? (
        <div className="bg-panel-card border border-panel-subtle rounded-xl p-8 text-center">
          <ClipboardList className="w-12 h-12 text-ink-muted mx-auto mb-3" />
          <h2 className="text-lg font-semibold text-ink-primary mb-1">No Requests Yet</h2>
          <p className="text-sm text-ink-muted">
            Submit a data subject access request to exercise your privacy rights.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {requests.map((req) => {
            const TypeIcon = DSAR_TYPES.find((t) => t.value === req.request_type)?.icon || FileText;
            return (
              <div
                key={req.id}
                className="bg-panel-card border border-panel-subtle rounded-xl p-4 space-y-2"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-brand/10 flex items-center justify-center">
                      <TypeIcon size={16} className="text-brand" />
                    </div>
                    <div>
                      <span className="text-sm font-medium text-ink-primary capitalize">
                        {req.request_type.replace('_', ' ')}
                      </span>
                      <span
                        className={`ml-2 inline-flex px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wider ${statusColor(req.status)}`}
                      >
                        {req.status.replace('_', ' ')}
                      </span>
                    </div>
                  </div>
                  <span className="text-xs text-ink-muted">
                    {new Date(req.created_at).toLocaleDateString()}
                  </span>
                </div>
                {req.description && (
                  <p className="text-xs text-ink-secondary pl-12">{req.description}</p>
                )}
                {req.response && (
                  <div className="ml-12 px-3 py-2 bg-panel-surface rounded-lg border border-panel-subtle">
                    <p className="text-xs text-ink-muted">
                      <span className="font-medium text-ink-primary">Response:</span> {req.response}
                    </p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
