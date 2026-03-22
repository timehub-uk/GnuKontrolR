import { useState, useEffect } from 'react';
import api from '../utils/api';
import { Users, Trash2, RefreshCw, UserPlus } from 'lucide-react';

const ROLE_COLOR = { superadmin: 'badge-red', admin: 'badge-yellow', reseller: 'badge-blue', user: 'badge-green' };

export default function UsersPage() {
  const [users, setUsers]     = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    const { data } = await api.get('/api/users/');
    setUsers(data);
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const suspend = async (id, current) => {
    await api.patch(`/api/users/${id}`, { is_suspended: !current });
    load();
  };

  const del = async id => {
    if (!confirm('Delete user?')) return;
    await api.delete(`/api/users/${id}`);
    load();
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2"><Users size={20} />Users</h1>
        <button onClick={load} className="btn-ghost"><RefreshCw size={14} /></button>
      </div>
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-panel-700 text-gray-400 text-xs uppercase">
            <tr>{['Username','Email','Role','Domains','Status','Joined','Actions'].map(h =>
              <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-panel-700">
            {loading ? <tr><td colSpan={7} className="text-center py-8 text-gray-500">Loading…</td></tr>
              : users.map(u => (
              <tr key={u.id} className="hover:bg-panel-700/50">
                <td className="px-4 py-3 font-medium text-white">{u.username}</td>
                <td className="px-4 py-3 text-gray-400">{u.email}</td>
                <td className="px-4 py-3"><span className={ROLE_COLOR[u.role] || 'badge-blue'}>{u.role}</span></td>
                <td className="px-4 py-3 text-gray-400">{u.max_domains}</td>
                <td className="px-4 py-3">
                  <span className={u.is_suspended ? 'badge-red' : 'badge-green'}>
                    {u.is_suspended ? 'Suspended' : 'Active'}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-500 text-xs">{new Date(u.created_at).toLocaleDateString()}</td>
                <td className="px-4 py-3 flex gap-2">
                  <button onClick={() => suspend(u.id, u.is_suspended)} className="text-xs text-yellow-400 hover:text-yellow-200">
                    {u.is_suspended ? 'Unsuspend' : 'Suspend'}
                  </button>
                  <button onClick={() => del(u.id)} className="text-gray-500 hover:text-red-400"><Trash2 size={13} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
