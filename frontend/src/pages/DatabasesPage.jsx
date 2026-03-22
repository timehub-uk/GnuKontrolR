import { Database, Plus, Trash2 } from 'lucide-react';

export default function DatabasesPage() {
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-white flex items-center gap-2"><Database size={20} />Databases</h1>
      <div className="card text-xs text-gray-400 bg-blue-900/10 border-blue-800">
        Databases run on the <strong className="text-blue-300">MySQL master container</strong>. Each customer gets isolated databases with dedicated user credentials.
      </div>
      <div className="flex justify-end">
        <button className="btn-primary flex items-center gap-2"><Plus size={14} /> Create Database</button>
      </div>
      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-panel-700 text-gray-400 text-xs uppercase">
            <tr>{['Database','User','Size','Created','Actions'].map(h =>
              <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            <tr><td colSpan={5} className="text-center py-8 text-gray-500">No databases yet</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
