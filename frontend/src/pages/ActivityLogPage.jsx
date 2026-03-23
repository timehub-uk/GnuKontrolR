/**
 * ActivityLogPage — private per-user request log.
 * Shows every API call the current user made, with event ID, status,
 * plain-English error descriptions, and suggested fixes.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  ScrollText, RefreshCw, Trash2, CheckCircle,
  AlertCircle, AlertTriangle, Info, Clock, Hash,
} from 'lucide-react';
import api from '../utils/api';

// ── Human-readable status explanations ───────────────────────────────────────
const STATUS_INFO = {
  200: { label: 'OK',                    icon: CheckCircle,  color: 'text-green-400',  fix: null },
  201: { label: 'Created',               icon: CheckCircle,  color: 'text-green-400',  fix: null },
  204: { label: 'No content',            icon: CheckCircle,  color: 'text-green-400',  fix: null },
  400: {
    label: 'Bad request',
    icon: AlertTriangle, color: 'text-yellow-400',
    fix: 'The request was malformed or missing required fields. Check what you submitted and try again.',
  },
  401: {
    label: 'Not authenticated',
    icon: AlertCircle, color: 'text-red-400',
    fix: 'Your session expired. Sign out and sign back in.',
  },
  403: {
    label: 'Permission denied',
    icon: AlertCircle, color: 'text-red-400',
    fix: 'Your account does not have permission for this action. Contact your administrator.',
  },
  404: {
    label: 'Not found',
    icon: AlertTriangle, color: 'text-yellow-400',
    fix: 'The resource no longer exists or was never created. Refresh the page and try again.',
  },
  409: {
    label: 'Conflict',
    icon: AlertTriangle, color: 'text-yellow-400',
    fix: 'A resource with the same name already exists. Choose a different name.',
  },
  413: {
    label: 'Too large',
    icon: AlertTriangle, color: 'text-yellow-400',
    fix: 'The file or payload is too large. Try a smaller file (max 1 MB for config files).',
  },
  422: {
    label: 'Validation error',
    icon: AlertTriangle, color: 'text-yellow-400',
    fix: 'One or more fields failed validation. Review the form for highlighted errors.',
  },
  429: {
    label: 'Rate limited',
    icon: AlertTriangle, color: 'text-orange-400',
    fix: 'Too many requests in a short time. Wait a moment and try again.',
  },
  500: {
    label: 'Server error',
    icon: AlertCircle, color: 'text-red-400',
    fix: 'Something went wrong on the server. Note the Event ID and contact support.',
  },
  503: {
    label: 'Service unavailable',
    icon: AlertCircle, color: 'text-red-400',
    fix: 'The container or service is not reachable. Check the Containers page and ensure it is running.',
  },
  504: {
    label: 'Gateway timeout',
    icon: AlertCircle, color: 'text-red-400',
    fix: 'A container took too long to respond. It may be overloaded or stopped.',
  },
};

function statusInfo(code) {
  return STATUS_INFO[code] || {
    label: `HTTP ${code}`,
    icon: Info,
    color: code < 400 ? 'text-green-400' : code < 500 ? 'text-yellow-400' : 'text-red-400',
    fix: code >= 400 ? 'An unexpected error occurred. Note the Event ID and contact support.' : null,
  };
}

function MethodBadge({ method }) {
  const colors = {
    GET:    'bg-blue-900/30 text-blue-300',
    POST:   'bg-green-900/30 text-green-300',
    PUT:    'bg-yellow-900/30 text-yellow-300',
    PATCH:  'bg-orange-900/30 text-orange-300',
    DELETE: 'bg-red-900/30 text-red-300',
  };
  return (
    <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${colors[method] || 'bg-panel-600 text-gray-300'}`}>
      {method}
    </span>
  );
}

function LogRow({ entry }) {
  const [open, setOpen] = useState(false);
  const info = statusInfo(entry.status);
  const Icon = info.icon;
  const isError = entry.status >= 400;
  const ts = new Date(entry.timestamp);

  return (
    <div className={`border-b border-panel-700 last:border-0 ${isError ? 'bg-red-950/10' : ''}`}>
      <button
        onClick={() => isError && setOpen(o => !o)}
        className={`w-full flex items-center gap-3 px-4 py-2.5 text-left ${isError ? 'hover:bg-panel-700/30 cursor-pointer' : 'cursor-default'}`}
      >
        <Icon size={13} className={`flex-shrink-0 ${info.color}`} />
        <MethodBadge method={entry.method} />

        <span className="flex-1 text-xs font-mono text-gray-300 truncate">
          {entry.path}
        </span>

        <span className={`text-xs font-medium w-10 text-right flex-shrink-0 ${info.color}`}>
          {entry.status}
        </span>

        <span className="text-xs text-gray-600 w-14 text-right flex-shrink-0">
          {entry.duration_ms}ms
        </span>

        <span className="text-xs text-gray-600 w-36 text-right flex-shrink-0 hidden md:block">
          {ts.toLocaleString()}
        </span>

        <div className="flex items-center gap-1 text-gray-700 w-28 flex-shrink-0 hidden lg:flex">
          <Hash size={9} />
          <span className="text-xs font-mono truncate">{entry.event_id.slice(0, 8)}…</span>
        </div>
      </button>

      {/* Error detail + fix suggestion */}
      {open && isError && (
        <div className="px-4 pb-3 ml-6 space-y-2">
          <p className="text-xs font-medium text-gray-300">{info.label}</p>
          {info.fix && (
            <div className="flex items-start gap-2 bg-yellow-900/10 border border-yellow-800/40 rounded-lg px-3 py-2">
              <AlertTriangle size={12} className="text-yellow-500 mt-0.5 flex-shrink-0" />
              <p className="text-xs text-yellow-200">{info.fix}</p>
            </div>
          )}
          <div className="flex items-center gap-1.5">
            <Hash size={10} className="text-gray-600" />
            <span className="text-xs font-mono text-gray-500 select-all">{entry.event_id}</span>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ActivityLogPage() {
  const [entries,  setEntries]  = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [clearing, setClearing] = useState(false);
  const [error,    setError]    = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const { data } = await api.get('/api/log/me?limit=200');
      setEntries(data.entries || []);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Failed to load activity log');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const clearLog = async () => {
    setClearing(true);
    try {
      await api.delete('/api/log/me');
      setEntries([]);
    } finally {
      setClearing(false);
    }
  };

  const errorCount = entries.filter(e => e.status >= 400).length;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <ScrollText size={20} /> Activity Log
          </h1>
          {errorCount > 0 && (
            <span className="text-xs px-2 py-0.5 rounded bg-red-900/30 text-red-400">
              {errorCount} error{errorCount !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} disabled={loading} className="btn-ghost" title="Refresh">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
          <button
            onClick={clearLog}
            disabled={clearing || entries.length === 0}
            className="btn-ghost text-red-400 hover:text-red-300 flex items-center gap-1.5 text-xs"
          >
            <Trash2 size={13} /> Clear
          </button>
        </div>
      </div>

      <div className="card text-xs text-gray-400 bg-blue-900/10 border-blue-800">
        Your private request log — only you can see this. Each entry shows the
        API call made, its result, response time, and a unique Event ID. Click
        any error row for a plain-English explanation and a suggested fix.
        Last {entries.length} of up to 1 000 entries are kept.
      </div>

      {error && (
        <div className="card text-sm text-red-400 flex items-center gap-2">
          <AlertCircle size={14} /> {error}
        </div>
      )}

      <div className="card p-0 overflow-hidden">
        {/* Column headers */}
        <div className="flex items-center gap-3 px-4 py-2 bg-panel-700 text-xs text-gray-500 uppercase font-medium border-b border-panel-600">
          <span className="w-4" />
          <span className="w-14">Method</span>
          <span className="flex-1">Path</span>
          <span className="w-10 text-right">Status</span>
          <span className="w-14 text-right">Time</span>
          <span className="w-36 text-right hidden md:block">When</span>
          <span className="w-28 hidden lg:block">Event ID</span>
        </div>

        {loading ? (
          <div className="text-center py-10 text-gray-500 text-sm">
            <Clock size={18} className="mx-auto mb-2 opacity-40 animate-pulse" />
            Loading…
          </div>
        ) : entries.length === 0 ? (
          <div className="text-center py-10 text-gray-500 text-sm">
            No activity recorded yet.
          </div>
        ) : (
          entries.map(e => <LogRow key={e.event_id + e.timestamp} entry={e} />)
        )}
      </div>
    </div>
  );
}
