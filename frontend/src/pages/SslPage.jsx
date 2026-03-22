import { ShieldCheck, Plus } from 'lucide-react';
export default function SslPage() {
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-white flex items-center gap-2"><ShieldCheck size={20} />SSL / TLS</h1>
      <div className="card text-xs text-gray-400 bg-blue-900/10 border-blue-800">
        SSL certificates are issued via <strong className="text-blue-300">Traefik + Let's Encrypt</strong> automatically per domain. Manual upload also supported.
      </div>
      <div className="flex gap-3">
        <button className="btn-primary flex items-center gap-2"><Plus size={14} /> Request Let's Encrypt</button>
        <button className="btn-ghost">Upload Certificate</button>
      </div>
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-panel-700 text-gray-400 text-xs uppercase">
            <tr>{['Domain','Issuer','Expires','Auto-renew','Status','Actions'].map(h =>
              <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            <tr><td colSpan={6} className="text-center py-8 text-gray-500">No certificates yet</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
