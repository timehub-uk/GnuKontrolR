/**
 * WebSocket helper — wraps native WS with auto-reconnect.
 */
export function createWS(path, onMessage, onClose) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url   = `${proto}://${location.host}${path}`;
  let ws, timer;

  function connect() {
    ws = new WebSocket(url);
    ws.onmessage = e => onMessage(JSON.parse(e.data));
    ws.onclose   = () => {
      if (onClose) onClose();
      timer = setTimeout(connect, 4000);
    };
    ws.onerror = () => ws.close();
  }

  connect();
  return {
    close() { clearTimeout(timer); ws && ws.close(); },
    send(data) { ws && ws.readyState === 1 && ws.send(JSON.stringify(data)); },
  };
}
