import { useState, useEffect, useMemo } from 'react';
import { createColumnHelper } from '@tanstack/react-table';
import { toast } from 'sonner';
import api from '../utils/api';
import { fmtDate } from '../utils/dates';
import DataTable from '../components/DataTable';
import { Users, Trash2, RefreshCw } from 'lucide-react';

const ROLE_BADGE = {
  superadmin: 'bg-bad/15 text-bad-light border border-bad/25',
  admin:      'bg-brand/15 text-brand-light border border-brand/25',
  reseller:   'bg-warn/15 text-warn-light border border-warn/25',
  user:       'bg-ok/15 text-ok-light border border-ok/25',
};

const col = createColumnHelper();

export default function UsersPage() {
  const [users,    setUsers]    = useState([]);
  const [loading,  setLoading]  = useState(true);
  const [deleting, setDeleting] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/api/users/');
      setUsers(data);
    } catch {
      toast.error('Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const suspend = async (id, current) => {
    try {
      await api.patch(`/api/users/${id}`, { is_suspended: !current });
      toast.success(current ? 'User unsuspended' : 'User suspended');
      load();
    } catch {
      toast.error('Failed to update user');
    }
  };

  const confirmDelete = async id => {
    try {
      await api.delete(`/api/users/${id}`);
      toast.success('User deleted');
      setDeleting(null);
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Delete failed');
    }
  };

  const columns = useMemo(() => [
    col.accessor('username', {
      header: 'Username',
      cell: i => <span className="font-medium text-ink-primary">{i.getValue()}</span>,
    }),
    col.accessor('email', {
      header: 'Email',
      cell: i => <span className="text-ink-secondary">{i.getValue()}</span>,
    }),
    col.accessor('role', {
      header: 'Role',
      cell: i => (
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${ROLE_BADGE[i.getValue()] ?? 'bg-panel-elevated text-ink-muted border border-panel-border'}`}>
          {i.getValue()}
        </span>
      ),
    }),
    col.accessor('max_domains', {
      header: 'Domains',
      cell: i => <span className="text-ink-muted">{i.getValue()}</span>,
    }),
    col.accessor('is_suspended', {
      header: 'Status',
      cell: i => (
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${i.getValue() ? 'bg-bad/15 text-bad-light border border-bad/25' : 'bg-ok/15 text-ok-light border border-ok/25'}`}>
          {i.getValue() ? 'Suspended' : 'Active'}
        </span>
      ),
    }),
    col.accessor('created_at', {
      header: 'Joined',
      cell: i => <span className="text-ink-muted text-xs">{fmtDate(i.getValue())}</span>,
    }),
    col.display({
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <button
            onClick={() => suspend(row.original.id, row.original.is_suspended)}
            className="text-xs text-warn-light hover:text-warn transition-colors"
          >
            {row.original.is_suspended ? 'Unsuspend' : 'Suspend'}
          </button>
          <button
            onClick={() => setDeleting(row.original.id)}
            className="text-ink-muted hover:text-bad transition-colors p-1 rounded"
          >
            <Trash2 size={13} />
          </button>
        </div>
      ),
    }),
  ], []);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-ink-primary flex items-center gap-2">
          <Users size={20} /> Users
        </h1>
        <button onClick={load} disabled={loading} className="btn-ghost">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {deleting && (
        <div className="card border-bad/30 bg-bad/5">
          <p className="text-sm text-ink-primary mb-3">Delete this user? This cannot be undone.</p>
          <div className="flex gap-2">
            <button onClick={() => confirmDelete(deleting)} className="btn-primary bg-bad hover:bg-bad/80 border-bad/50 text-xs px-3 py-1.5">Delete</button>
            <button onClick={() => setDeleting(null)} className="btn-ghost text-xs px-3 py-1.5">Cancel</button>
          </div>
        </div>
      )}

      <DataTable columns={columns} data={users} loading={loading} emptyMessage="No users found" />
    </div>
  );
}
