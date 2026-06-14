import { Mail, Plus, Loader, Trash2 } from 'lucide-react';
import { useState, useEffect } from 'react';
import api from '../utils/api';

export default function EmailPage() {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAccounts = async () => {
      try {
        const res = await api.get('/api/email-security/accounts');
        setAccounts(res.data.accounts || []);
      } catch (err) {
        // ignore
      } finally {
        setLoading(false);
      }
    };
    fetchAccounts();
  }, []);

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-white flex items-center gap-2"><Mail size={20} />Email Accounts</h1>
      <div className="card text-xs text-gray-400 bg-blue-900/10 border-blue-800">
        Mail handled by <strong className="text-blue-300">Postfix + Dovecot master containers</strong>. Accounts are isolated per domain.
      </div>
      <div className="flex justify-end">
        <button className="btn-primary flex items-center gap-2"><Plus size={14} /> Add Email Account</button>
      </div>
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-panel-700 text-gray-400 text-xs uppercase">
            <tr>{['Address','Quota','Used','Domain','Actions'].map(h =>
              <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5} className="text-center py-8 text-gray-500">
                  <div className="flex items-center justify-center gap-2">
                    <Loader size={16} className="animate-spin" /> Loading email accounts…
                  </div>
                </td>
              </tr>
            ) : accounts.length === 0 ? (
              <tr><td colSpan={5} className="text-center py-8 text-gray-500">No email accounts yet</td></tr>
            ) : (
              accounts.map(acc => (
                <tr key={acc.address} className="border-b border-panel-border hover:bg-panel-hover transition-colors">
                  <td className="px-4 py-3 text-white font-medium">{acc.address}</td>
                  <td className="px-4 py-3 text-gray-300">{acc.quota}</td>
                  <td className="px-4 py-3 text-gray-400">{acc.used}</td>
                  <td className="px-4 py-3 text-gray-300">{acc.domain}</td>
                  <td className="px-4 py-3">
                    <button className="text-red-400 hover:text-red-300 transition-colors p-1" title="Delete Account">
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
