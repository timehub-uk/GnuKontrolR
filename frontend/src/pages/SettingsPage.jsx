import { Settings } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function SettingsPage() {
  const { user } = useAuth();
  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-xl font-bold text-white flex items-center gap-2"><Settings size={20} />Settings</h1>
      <div className="card space-y-4">
        <h2 className="text-sm font-semibold text-white">Account</h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div><span className="text-gray-400">Username</span><div className="text-white mt-1">{user?.username}</div></div>
          <div><span className="text-gray-400">Email</span><div className="text-white mt-1">{user?.email}</div></div>
          <div><span className="text-gray-400">Role</span><div className="text-white mt-1 capitalize">{user?.role}</div></div>
          <div><span className="text-gray-400">Disk Quota</span><div className="text-white mt-1">{user?.disk_quota_mb} MB</div></div>
        </div>
      </div>
      <div className="card space-y-4">
        <h2 className="text-sm font-semibold text-white">Change Password</h2>
        <input className="input" type="password" placeholder="Current password" />
        <input className="input" type="password" placeholder="New password" />
        <input className="input" type="password" placeholder="Confirm new password" />
        <button className="btn-primary">Update Password</button>
      </div>
    </div>
  );
}
