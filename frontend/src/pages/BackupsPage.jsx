import { useState, useEffect } from 'react';
import { HardDrive, History } from 'lucide-react';
import api from '../utils/api';
import ConfigBackupsPanel from '../components/ConfigBackupsPanel';

export default function BackupsPage() {
  const [domains,        setDomains]        = useState([]);
  const [selectedDomain, setSelectedDomain] = useState('');
  const [tab,            setTab]            = useState('config');  // config | fullsite

  useEffect(() => {
    api.get('/api/domains').then(r => {
      const list = r.data?.domains || r.data || [];
      setDomains(list);
      if (list.length && !selectedDomain) setSelectedDomain(list[0].name || list[0]);
    }).catch(() => {});
  }, []);

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-white flex items-center gap-2">
        <HardDrive size={20} /> Backups
      </h1>

      {/* Domain selector + tabs */}
      <div className="flex items-center gap-3 flex-wrap">
        <select
          value={selectedDomain}
          onChange={e => setSelectedDomain(e.target.value)}
          className="input w-56"
        >
          {domains.length === 0 && <option value="">No domains</option>}
          {domains.map(d => {
            const name = d.name || d;
            return <option key={name} value={name}>{name}</option>;
          })}
        </select>

        <div className="flex border border-panel-500 rounded-lg overflow-hidden">
          {[
            { id: 'config',   label: 'Config Snapshots', icon: History },
            { id: 'fullsite', label: 'Full Site',         icon: HardDrive },
          ].map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm transition-colors ${
                tab === id
                  ? 'bg-brand-600/30 text-brand-300'
                  : 'text-gray-400 hover:text-white hover:bg-panel-700'
              }`}
            >
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      {tab === 'config' && (
        <ConfigBackupsPanel domain={selectedDomain} />
      )}

      {tab === 'fullsite' && (
        <div className="card p-0 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-panel-700 text-gray-400 text-xs uppercase">
              <tr>
                {['Name', 'Domain', 'Size', 'Created', 'Type', 'Actions'].map(h => (
                  <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <td colSpan={6} className="text-center py-8 text-gray-500">
                  Full-site backup scheduler coming soon.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
