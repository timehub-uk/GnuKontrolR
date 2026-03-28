/**
 * Server-Sent Events (SSE) helper — one-way server → browser push.
 *
 * Lighter than WebSocket for read-only streams (log tailing, notifications,
 * install progress, activity feed).  Uses the native EventSource API and
 * automatically reconnects with exponential back-off.
 *
 * Usage:
 *   const feed = createSSE('/api/activity/stream', msg => console.log(msg));
 *   // later:
 *   feed.close();
 */

const MIN_RETRY_MS  = 1_000;
const MAX_RETRY_MS  = 30_000;
const BACKOFF_MULT  = 1.8;

/**
 * @param {string}   path       — relative URL, e.g. '/api/activity/stream'
 * @param {function} onMessage  — called with parsed JSON for each `data:` line
 * @param {object}   [opts]
 * @param {function} [opts.onError]   — called when connection errors
 * @param {function} [opts.onOpen]    — called when connection opens/re-opens
 * @param {string}   [opts.token]     — if set, appended as ?token=… query param
 */
export function createSSE(path, onMessage, { onError, onOpen, token } = {}) {
  let es;
  let retryMs  = MIN_RETRY_MS;
  let timer    = null;
  let closed   = false;

  function buildUrl() {
    const base = `${path}${path.includes('?') ? '&' : '?'}_t=${Date.now()}`;
    return token ? `${base}&token=${encodeURIComponent(token)}` : base;
  }

  function connect() {
    if (closed) return;
    es = new EventSource(buildUrl(), { withCredentials: true });

    es.onopen = () => {
      retryMs = MIN_RETRY_MS;   // reset back-off on successful connect
      onOpen?.();
    };

    es.onmessage = e => {
      try { onMessage(JSON.parse(e.data)); } catch { onMessage(e.data); }
    };

    // Named event types (server sends `event: ping`, `event: notify`, etc.)
    es.addEventListener('ping',   () => { /* keep-alive, ignore */ });
    es.addEventListener('notify', e => {
      try { onMessage({ _type: 'notify', ...JSON.parse(e.data) }); } catch { /* ignore */ }
    });

    es.onerror = () => {
      es.close();
      onError?.();
      if (closed) return;
      timer = setTimeout(() => {
        retryMs = Math.min(retryMs * BACKOFF_MULT, MAX_RETRY_MS);
        connect();
      }, retryMs);
    };
  }

  connect();

  return {
    /** Permanently close — will not reconnect. */
    close() {
      closed = true;
      clearTimeout(timer);
      es?.close();
    },
  };
}
