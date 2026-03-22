import { HardDrive, Plus } from 'lucide-react';
export default function BackupsPage() {
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-white flex items-center gap-2"><HardDrive size={20} />Backups</h1>
      <div className="flex gap-3">
        <button className="btn-primary flex items-center gap-2"><Plus size={14} /> Create Backup</button>
        <button className="btn-ghost">Schedule</button>
      </div>
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-panel-700 text-gray-400 text-xs uppercase">
            <tr>{['Name','Domain','Size','Created','Type','Actions'].map(h =>
              <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            <tr><td colSpan={6} className="text-center py-8 text-gray-500">No backups yet</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
