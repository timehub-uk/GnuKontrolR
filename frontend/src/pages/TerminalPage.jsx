import { useEffect, useRef } from 'react';
import { Terminal } from 'lucide-react';

export default function TerminalPage() {
  const containerRef = useRef(null);

  useEffect(() => {
    let term, fitAddon, ws;
    (async () => {
      const { Terminal: XTerm } = await import('xterm');
      const { FitAddon }        = await import('xterm-addon-fit');
      await import('xterm/css/xterm.css');

      term     = new XTerm({ theme: { background: '#0a0f1e', foreground: '#e2e8f0', cursor: '#3b82f6' }, fontSize: 13, fontFamily: '"Cascadia Code", "Fira Code", monospace', cursorBlink: true });
      fitAddon = new FitAddon();
      term.loadAddon(fitAddon);
      term.open(containerRef.current);
      fitAddon.fit();

      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const token = localStorage.getItem('access_token') || '';
      ws = new WebSocket(`${proto}://${location.host}/api/terminal/ws?token=${encodeURIComponent(token)}`);
      ws.onopen    = () => term.writeln('\x1b[32mConnected to WebPanel Terminal\x1b[0m\r\n');
      ws.onmessage = e => term.write(e.data);
      ws.onclose   = () => term.writeln('\r\n\x1b[31mConnection closed\x1b[0m');
      term.onData(data => ws.readyState === 1 && ws.send(data));
      term.onResize(({ cols, rows }) => {
        if (ws.readyState === 1) ws.send(JSON.stringify({ type: 'resize', cols, rows }));
      });

      const resizeObs = new ResizeObserver(() => fitAddon.fit());
      resizeObs.observe(containerRef.current);
    })();
    return () => { term?.dispose(); ws?.close(); };
  }, []);

  return (
    <div className="space-y-4 h-full flex flex-col">
      <h1 className="text-xl font-bold text-ink-primary flex items-center gap-2"><Terminal size={20} />Web Terminal</h1>
      <div ref={containerRef} className="flex-1 rounded-xl overflow-hidden border border-panel-subtle min-h-96" />
    </div>
  );
}
