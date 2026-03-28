/**
 * WebSocket helper — wraps native WS with:
 *   - Auto-reconnect with exponential back-off
 *   - Heartbeat ping/pong to detect silent disconnects
 *   - Message queue that drains once the socket re-opens
 */

const MIN_RETRY_MS   = 1_000;
const MAX_RETRY_MS   = 30_000;
const BACKOFF_MULT   = 1.8;
const HEARTBEAT_MS   = 20_000;   // send a ping every 20 s
const PING_TIMEOUT_MS = 5_000;   // close if no pong within 5 s

/**
 * @param {string}   path       — relative WS path, e.g. '/api/server/ws/stats'
 * @param {function} onMessage  — called with parsed JSON for each message
 * @param {function} [onClose]  — called each time the socket closes
 * @param {function} [onOpen]   — called each time the socket opens / re-opens
 */
export function createWS(path, onMessage, onClose, onOpen) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url   = `${proto}://${location.host}${path}`;

  let ws;
  let retryMs       = MIN_RETRY_MS;
  let retryTimer    = null;
  let heartbeatTimer = null;
  let pongTimer      = null;
  let queue          = [];      // messages buffered while disconnected
  let destroyed      = false;

  function resetHeartbeat() {
    clearTimeout(heartbeatTimer);
    clearTimeout(pongTimer);
    heartbeatTimer = setTimeout(() => {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
        pongTimer = setTimeout(() => {
          // Server didn't respond — treat as stale connection
          ws?.close();
        }, PING_TIMEOUT_MS);
      }
    }, HEARTBEAT_MS);
  }

  function connect() {
    if (destroyed) return;
    ws = new WebSocket(url);

    ws.onopen = () => {
      retryMs = MIN_RETRY_MS;
      resetHeartbeat();
      onOpen?.();
      // Drain queued messages
      const pending = queue;
      queue = [];
      pending.forEach(msg => ws.send(JSON.stringify(msg)));
    };

    ws.onmessage = e => {
      resetHeartbeat();
      try {
        const data = JSON.parse(e.data);
        // Silently swallow server pong responses
        if (data?.type === 'pong') return;
        onMessage(data);
      } catch { /* non-JSON frame, ignore */ }
    };

    ws.onclose = () => {
      clearTimeout(heartbeatTimer);
      clearTimeout(pongTimer);
      onClose?.();
      if (destroyed) return;
      retryTimer = setTimeout(() => {
        retryMs = Math.min(retryMs * BACKOFF_MULT, MAX_RETRY_MS);
        connect();
      }, retryMs);
    };

    ws.onerror = () => ws.close();
  }

  connect();

  return {
    /** Permanently destroy — will not reconnect. */
    close() {
      destroyed = true;
      clearTimeout(retryTimer);
      clearTimeout(heartbeatTimer);
      clearTimeout(pongTimer);
      ws?.close();
    },
    /**
     * Send a JSON message.  If the socket is not yet open the message is
     * queued and sent automatically once the connection is established.
     */
    send(data) {
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
      } else {
        queue.push(data);
      }
    },
  };
}
