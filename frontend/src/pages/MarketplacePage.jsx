import { useState, useEffect } from 'react';
import { Package, Play, Square, Download, CheckCircle, AlertCircle, Loader } from 'lucide-react';
import api from '../utils/api';

const CATEGORY_LABELS = {
  web_server:       '🌐 Web Servers',
  runtime:          '⚙️ Runtimes',
  php_framework:    '🐘 PHP Frameworks',
  python_framework: '🐍 Python Frameworks',
  database:         '🗄️ Databases',
  tool:             '🔧 Tools',
};

export default function MarketplacePage() {
  const [domains, setDomains]     = useState([]);
  const [domain, setDomain]       = useState('');
  const [catalogue, setCatalogue] = useState({});
  const [installed, setInstalled] = useState({});
  const [loading, setLoading]     = useState(false);
  const [actionId, setActionId]   = useState(null);
  const [message, setMessage]     = useState(null);

  useEffect(() => {
    api.get('/api/domains').then(r => {
      const d = (r.data || []).map(x => x.name || x.domain || x);
      setDomains(d);
      if (d.length) setDomain(d[0]);
    }).catch(() => {});
    api.get('/api/services/catalogue').then(r => setCatalogue(r.data || {}));
  }, []);

  useEffect(() => {
    if (!domain) return;
    setLoading(true);
    api.get(`/api/services/${domain}`)
      .then(r => setInstalled(r.data.services || {}))
      .catch(() => setInstalled({}))
      .finally(() => setLoading(false));
  }, [domain]);

  async function doAction(serviceId, action) {
    const key = serviceId + action;
    setActionId(key);
    setMessage(null);
    try {
      const r = await api.post(`/api/services/${domain}/${serviceId}`, { action });
      setMessage({ type: 'ok', text: r.data.message || r.data.output || `${action} successful` });
      const fresh = await api.get(`/api/services/${domain}`);
      setInstalled(fresh.data.services || {});
    } catch (e) {
      setMessage({ type: 'err', text: e.response?.data?.detail || 'Action failed' });
    } finally {
      setActionId(null);
    }
  }

  const grouped = Object.entries(catalogue).reduce((acc, [id, info]) => {
    const cat = info.category || 'tool';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push({ id, ...info });
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-white flex items-center gap-2">
        <Package size={20} /> Services Marketplace
      </h1>

      <div className="card flex items-center gap-4">
        <label className="text-sm text-gray-400 shrink-0">Domain</label>
        <select className="input flex-1" value={domain} onChange={e => setDomain(e.target.value)}>
          {domains.length === 0 && <option value="">— no domains yet —</option>}
          {domains.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
        {loading && <Loader size={16} className="animate-spin text-brand-400" />}
      </div>

      {message && (
        <div className={`card flex items-center gap-2 text-sm ${
          message.type === 'ok' ? 'text-green-400 border-green-800' : 'text-red-400 border-red-800'
        }`}>
          {message.type === 'ok' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
          {message.text}
        </div>
      )}

      {Object.entries(grouped).map(([cat, items]) => (
        <div key={cat} className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400 border-b border-panel-600 pb-1">
            {CATEGORY_LABELS[cat] || cat}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {items.map(svc => {
              const isRunning  = installed[svc.id] === true;
              const alwaysOn   = svc.always_installed;
              const busy       = actionId?.startsWith(svc.id);
              const hasInstall = !!svc.install_cmd;

              return (
                <div key={svc.id} className="card flex flex-col gap-3 hover:border-panel-500 transition-colors">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-xl">{svc.icon}</span>
                      <span className="font-semibold text-white text-sm">{svc.name}</span>
                    </div>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      alwaysOn  ? 'bg-blue-900/40 text-blue-300'
                      : isRunning ? 'bg-green-900/40 text-green-400'
                      : 'bg-panel-700 text-gray-500'
                    }`}>
                      {alwaysOn ? 'Built-in' : isRunning ? 'Running' : 'Stopped'}
                    </span>
                  </div>

                  <p className="text-xs text-gray-400 leading-relaxed flex-1">{svc.description}</p>

                  {svc.incompatible?.length > 0 && (
                    <p className="text-xs text-yellow-600">
                      ⚠ Incompatible with: {svc.incompatible.join(', ')}
                    </p>
                  )}

                  {!alwaysOn && (
                    <div className="flex gap-2 mt-auto pt-1">
                      {hasInstall && !isRunning && (
                        <button
                          className="btn-ghost text-xs flex items-center gap-1"
                          disabled={!!busy}
                          onClick={() => doAction(svc.id, 'install')}
                        >
                          {busy && actionId === svc.id + 'install'
                            ? <Loader size={12} className="animate-spin" />
                            : <Download size={12} />}
                          Install
                        </button>
                      )}
                      {!isRunning ? (
                        <button
                          className="btn-primary text-xs flex items-center gap-1"
                          disabled={!!busy}
                          onClick={() => doAction(svc.id, 'enable')}
                        >
                          {busy ? <Loader size={12} className="animate-spin" /> : <Play size={12} />}
                          Enable
                        </button>
                      ) : (
                        <button
                          className="btn-ghost text-xs flex items-center gap-1 text-red-400"
                          disabled={!!busy}
                          onClick={() => doAction(svc.id, 'disable')}
                        >
                          {busy ? <Loader size={12} className="animate-spin" /> : <Square size={12} />}
                          Disable
                        </button>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {!domain && (
        <div className="card text-center py-12 text-gray-500">
          Create a domain first to manage its services.
        </div>
      )}
    </div>
  );
}
