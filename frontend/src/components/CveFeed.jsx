/**
 * CveFeed — Live CVE threat intelligence feed from NVD/CVE.org.
 * Results cached 6 hours on the backend.
 */
import { useState, useEffect } from 'react';
import { Flame, Search, RefreshCw, Loader, ExternalLink, AlertTriangle, Shield } from 'lucide-react';
import api from '../utils/api';

const SEVERITY_STYLES = {
  CRITICAL: 'text-red-300 bg-red-900/25 border-red-700/50',
  HIGH:     'text-orange-300 bg-orange-900/25 border-orange-700/50',
  MEDIUM:   'text-yellow-300 bg-yellow-900/25 border-yellow-700/50',
  LOW:      'text-blue-300 bg-blue-900/25 border-blue-700/50',
};

const SCORE_COLOR = (s) => {
  if (!s) return 'text-gray-400';
  if (s >= 9.0) return 'text-red-400 font-bold';
  if (s >= 7.0) return 'text-orange-400 font-semibold';
  if (s >= 4.0) return 'text-yellow-400';
  return 'text-blue-400';
};

export default function CveFeed() {
  const [items,    setItems]    = useState([]);
  const [loading,  setLoading]  = useState(false);
  const [keyword,  setKeyword]  = useState('');
  const [severity, setSeverity] = useState('');
  const [error,    setError]    = useState('');
  const [cached,   setCached]   = useState(false);
  const [expanded, setExpanded] = useState(null);

  const load = async (kw = keyword, sev = severity) => {
    setLoading(true);
    setError('');
    try {
      const { data } = await api.get('/api/cve/recent', {
        params: { keyword: kw, severity: sev, limit: 25 },
      });
      setItems(data.items || []);
      setCached(data.cached);
    } catch (e) {
      setError(e?.response?.data?.detail || 'CVE feed unavailable');
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleSearch = (e) => {
    e.preventDefault();
    load(keyword, severity);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-xl bg-red-900/25 flex items-center justify-center">
          <Flame size={16} className="text-red-400" />
        </div>
        <div>
          <h2 className="text-[15px] font-bold text-white">CVE Threat Feed</h2>
          <p className="text-[11px] text-gray-400">
            Live vulnerability data from NVD / CVE.org
            {cached && <span className="ml-2 text-blue-400 opacity-70">(cached)</span>}
          </p>
        </div>
      </div>

      {/* Search bar */}
      <form onSubmit={handleSearch} className="flex gap-2 flex-wrap">
        <input
          value={keyword}
          onChange={e => setKeyword(e.target.value)}
          placeholder="Search CVEs (e.g. apache, wordpress, nginx)"
          className="input flex-1 min-w-48 text-sm"
        />
        <select
          value={severity}
          onChange={e => setSeverity(e.target.value)}
          className="input w-36 text-sm"
        >
          <option value="">All severity</option>
          <option value="CRITICAL">Critical</option>
          <option value="HIGH">High</option>
          <option value="MEDIUM">Medium</option>
          <option value="LOW">Low</option>
        </select>
        <button type="submit" disabled={loading} className="btn-primary flex items-center gap-1.5 px-4 py-1.5 text-sm">
          {loading ? <Loader size={13} className="animate-spin" /> : <Search size={13} />}
          Search
        </button>
        <button
          type="button"
          onClick={() => { setKeyword(''); setSeverity(''); load('', ''); }}
          disabled={loading}
          className="btn-ghost flex items-center gap-1 px-3 py-1.5 text-xs"
        >
          <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Reset
        </button>
      </form>

      {error && (
        <div className="flex items-center gap-2 text-red-400 bg-red-900/15 border border-red-800/30 rounded-xl px-4 py-2.5 text-sm">
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {!loading && items.length === 0 && !error && (
        <p className="text-sm text-gray-400 text-center py-6">No CVEs found.</p>
      )}

      <div className="space-y-2">
        {items.map(cve => {
          const sevStyle = SEVERITY_STYLES[cve.severity] || 'text-gray-400 bg-panel-800 border-panel-600';
          const isOpen = expanded === cve.id;
          return (
            <div
              key={cve.id}
              className={`border rounded-xl overflow-hidden transition-all ${
                isOpen ? 'bg-panel-800 border-panel-500' : 'bg-panel-900/60 border-panel-700 hover:border-panel-500'
              }`}
            >
              <button
                className="w-full text-left px-4 py-3 flex items-start gap-3"
                onClick={() => setExpanded(isOpen ? null : cve.id)}
              >
                {/* Score badge */}
                <div className="flex-shrink-0 w-12 text-center">
                  <span className={`text-[15px] ${SCORE_COLOR(cve.score)}`}>
                    {cve.score ?? '—'}
                  </span>
                </div>

                <div className="flex-1 min-w-0 space-y-0.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[12px] font-mono font-bold text-white">{cve.id}</span>
                    {cve.severity && (
                      <span className={`text-[9px] px-1.5 py-0.5 rounded border font-semibold uppercase ${sevStyle}`}>
                        {cve.severity}
                      </span>
                    )}
                    {cve.products?.length > 0 && cve.products.map((p, i) => (
                      <span key={i} className="text-[9px] px-1.5 py-0.5 rounded bg-panel-700 border border-panel-600 text-gray-400">
                        {p}
                      </span>
                    ))}
                  </div>
                  <p className="text-[11px] text-gray-300 line-clamp-2">{cve.description}</p>
                  <p className="text-[9px] text-gray-500">
                    Published: {cve.published ? new Date(cve.published).toLocaleDateString() : '—'}
                  </p>
                </div>
              </button>

              {isOpen && (
                <div className="px-4 pb-3 space-y-2 border-t border-panel-700/60">
                  <p className="text-[12px] text-gray-300 mt-2">{cve.description}</p>
                  <div className="flex gap-3 flex-wrap">
                    <a
                      href={cve.nvd_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-[11px] text-brand-400 hover:text-brand-300 transition-colors"
                    >
                      <ExternalLink size={10} /> NVD Details
                    </a>
                    <a
                      href={cve.cve_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-[11px] text-brand-400 hover:text-brand-300 transition-colors"
                    >
                      <ExternalLink size={10} /> CVE.org
                    </a>
                    {cve.references?.map((ref, i) => (
                      <a
                        key={i}
                        href={ref}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 text-[11px] text-gray-400 hover:text-gray-200 transition-colors truncate max-w-xs"
                      >
                        <ExternalLink size={9} /> Ref {i + 1}
                      </a>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
