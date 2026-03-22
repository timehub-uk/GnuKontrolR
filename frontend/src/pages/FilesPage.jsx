import { useState } from 'react';
import { FolderOpen, File, Folder, ArrowLeft, Upload, Plus, Trash2 } from 'lucide-react';

export default function FilesPage() {
  const [path, setPath] = useState('/public_html');
  const [files] = useState([
    { name: 'public_html', type: 'dir', size: '—', modified: '2024-01-01' },
    { name: 'logs',        type: 'dir', size: '—', modified: '2024-01-01' },
    { name: 'index.php',   type: 'file', size: '2.1 KB', modified: '2024-01-05' },
    { name: '.htaccess',   type: 'file', size: '142 B',  modified: '2024-01-01' },
  ]);

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-white flex items-center gap-2"><FolderOpen size={20} />File Manager</h1>

      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        <button className="btn-ghost flex items-center gap-1.5"><ArrowLeft size={13} /> Back</button>
        <div className="input flex-1 max-w-lg font-mono text-xs">{path}</div>
        <button className="btn-primary flex items-center gap-2"><Upload size={13} /> Upload</button>
        <button className="btn-ghost flex items-center gap-2"><Plus size={13} /> New</button>
      </div>

      <div className="card p-0 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-panel-700 text-gray-400 text-xs uppercase">
            <tr>{['Name','Type','Size','Modified','Actions'].map(h =>
              <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-panel-700">
            {files.map(f => (
              <tr key={f.name} className="hover:bg-panel-700/50 cursor-pointer">
                <td className="px-4 py-3 flex items-center gap-2 text-white">
                  {f.type === 'dir' ? <Folder size={15} className="text-yellow-400" /> : <File size={15} className="text-blue-400" />}
                  {f.name}
                </td>
                <td className="px-4 py-3 text-gray-400 capitalize">{f.type}</td>
                <td className="px-4 py-3 text-gray-400">{f.size}</td>
                <td className="px-4 py-3 text-gray-500">{f.modified}</td>
                <td className="px-4 py-3"><button className="text-gray-500 hover:text-red-400"><Trash2 size={13} /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
