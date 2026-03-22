import { Mail, Plus } from 'lucide-react';
export default function EmailPage() {
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
            <tr><td colSpan={5} className="text-center py-8 text-gray-500">No email accounts yet</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
