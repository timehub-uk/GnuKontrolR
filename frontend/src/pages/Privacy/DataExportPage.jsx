import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Download, Trash2, FileJson, FileSpreadsheet,
  Loader, CheckCircle, AlertTriangle, AlertCircle,
} from 'lucide-react';
import api from '../../utils/api';

export default function DataExportPage() {
  const navigate = useNavigate();
  const [exporting, setExporting] = useState(null); // 'json' | 'csv' | null
  const [erasing, setErasing] = useState(false);
  const [confirmErasure, setConfirmErasure] = useState('');
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  const doExport = async (fmt) => {
    setExporting(fmt);
    setError(null);
    setMessage(null);
    try {
      const path = fmt === 'csv' ? '/api/compliance/export/csv' : '/api/compliance/export';
      const res = await api.get(path, {
        responseType: 'blob',
      });
      const blob = new Blob([res.data], {
        type: fmt === 'json' ? 'application/json' : 'text/csv',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `my-data.${fmt}`;
      a.click();
      URL.revokeObjectURL(url);
      setMessage(`Your data has been exported as ${fmt.toUpperCase()}.`);
    } catch (err) {
      setError(err.response?.data?.detail || 'Export failed. Please try again.');
    } finally {
      setExporting(null);
    }
  };

  const requestErasure = async () => {
    if (confirmErasure !== 'DELETE') {
      setError('Please type DELETE to confirm.');
      return;
    }
    setErasing(true);
    setError(null);
    setMessage(null);
    try {
      const res = await api.post('/api/compliance/erasure');
      setMessage(res.data.message || 'Erasure requested. Your account will be deleted in 7 days unless cancelled.');
      setConfirmErasure('');
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to request erasure.');
    } finally {
      setErasing(false);
    }
  };

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
          <Download className="w-5 h-5 text-brand" />
        </div>
        <div>
          <h1 className="text-xl font-semibold text-ink-primary">Data &amp; Privacy</h1>
          <p className="text-sm text-ink-muted">Export your data or request account deletion</p>
        </div>
      </div>

      {/* Status Messages */}
      {message && (
        <div className="flex items-center gap-2 px-4 py-3 bg-ok/10 border border-ok/20 rounded-lg">
          <CheckCircle size={18} className="text-ok shrink-0" />
          <span className="text-sm text-ok">{message}</span>
        </div>
      )}
      {error && (
        <div className="flex items-center gap-2 px-4 py-3 bg-error/10 border border-error/20 rounded-lg">
          <AlertCircle size={18} className="text-error shrink-0" />
          <span className="text-sm text-error">{error}</span>
        </div>
      )}

      {/* Data Export Section */}
      <div className="bg-panel-card border border-panel-subtle rounded-xl p-6 space-y-4">
        <h2 className="text-lg font-semibold text-ink-primary">Export Your Data</h2>
        <p className="text-sm text-ink-secondary">
          Download all personal data we hold about you in a portable format. This includes your
          profile information, account settings, and consent records. Choose your preferred format:
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
          <button
            onClick={() => doExport('json')}
            disabled={exporting !== null}
            className="flex items-center gap-3 px-4 py-4 rounded-lg border border-panel-subtle bg-panel-surface
                       hover:bg-panel-hover transition-colors disabled:opacity-50"
          >
            <div className="w-10 h-10 rounded-lg bg-amber-500/10 flex items-center justify-center">
              <FileJson className="w-5 h-5 text-amber-400" />
            </div>
            <div className="text-left">
              <div className="text-sm font-medium text-ink-primary">JSON Format</div>
              <div className="text-xs text-ink-muted">Machine-readable, structured data</div>
            </div>
            {exporting === 'json' && <Loader size={18} className="text-brand animate-spin ml-auto" />}
          </button>
          <button
            onClick={() => doExport('csv')}
            disabled={exporting !== null}
            className="flex items-center gap-3 px-4 py-4 rounded-lg border border-panel-subtle bg-panel-surface
                       hover:bg-panel-hover transition-colors disabled:opacity-50"
          >
            <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
              <FileSpreadsheet className="w-5 h-5 text-green-400" />
            </div>
            <div className="text-left">
              <div className="text-sm font-medium text-ink-primary">CSV Format</div>
              <div className="text-xs text-ink-muted">Spreadsheet-compatible export</div>
            </div>
            {exporting === 'csv' && <Loader size={18} className="text-brand animate-spin ml-auto" />}
          </button>
        </div>
      </div>

      {/* Right to Erasure Section */}
      <div className="bg-panel-card border border-red-900/30 rounded-xl p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-error/10 flex items-center justify-center">
            <Trash2 className="w-5 h-5 text-error" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-ink-primary">Right to Erasure</h2>
            <p className="text-sm text-ink-muted">Request deletion of your account and personal data</p>
          </div>
        </div>

        <div className="flex items-start gap-2 px-3 py-2.5 bg-amber-500/10 border border-amber-500/20 rounded-lg">
          <AlertTriangle size={16} className="text-amber-400 shrink-0 mt-0.5" />
          <p className="text-xs text-amber-300">
            This action will permanently delete your account and all associated data after a 7-day
            grace period. During this time, you may cancel the deletion by logging in and confirming
            your intent to keep the account. This action cannot be undone.
          </p>
        </div>

        <div className="space-y-3">
          <label className="block text-sm text-ink-primary">
            Type <span className="font-mono text-brand">DELETE</span> to confirm:
          </label>
          <input
            type="text"
            value={confirmErasure}
            onChange={(e) => setConfirmErasure(e.target.value)}
            placeholder="Type DELETE to confirm"
            className="w-full px-3 py-2 rounded-lg bg-panel-surface border border-panel-subtle
                       text-ink-primary placeholder-ink-muted text-sm
                       focus:outline-none focus:ring-2 focus:ring-error/50 focus:border-error/50"
          />
          <button
            onClick={requestErasure}
            disabled={erasing || confirmErasure !== 'DELETE'}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium
                       bg-error hover:bg-error/80 text-white transition-colors
                       disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {erasing ? (
              <><Loader size={16} className="animate-spin" /> Processing…</>
            ) : (
              <><Trash2 size={16} /> Request Account Deletion</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
