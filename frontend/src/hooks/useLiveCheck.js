/**
 * useLiveCheck
 * Polls or subscribes via WebSocket to a live-check endpoint.
 * Returns real-time status, errors, and auto-resolved advice.
 *
 * Modes:
 *   'ws'    — WebSocket duplex (preferred, instant)
 *   'poll'  — HTTP polling fallback
 *
 * Usage:
 *   const { checks, loading, error } = useLiveCheck('/api/security/ws/example.com');
 *   const { checks } = useLiveCheck('/api/security/check/example.com', { mode: 'poll', interval: 15000 });
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../utils/api';
import { createWS } from '../utils/ws';

export function useLiveCheck(endpoint, { mode = 'ws', interval = 15000, enabled = true } = {}) {
  const [checks, setChecks]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const wsRef                 = useRef(null);
  const timerRef              = useRef(null);

  const fetchPoll = useCallback(async () => {
    try {
      const r = await api.get(endpoint);
      setChecks(r.data.checks || r.data || []);
      setError(null);
    } catch (e) {
      setError(e?.response?.data?.detail || 'Check failed');
    } finally {
      setLoading(false);
    }
  }, [endpoint]);

  useEffect(() => {
    if (!enabled || !endpoint) return;

    if (mode === 'ws') {
      setLoading(true);
      wsRef.current = createWS(endpoint, {
        onMessage: (data) => {
          try {
            const parsed = JSON.parse(data);
            setChecks(parsed.checks || parsed || []);
            setError(null);
          } catch {
            setChecks([]);
          }
          setLoading(false);
        },
        onError: () => {
          // Fallback to poll on WS failure
          fetchPoll();
          timerRef.current = setInterval(fetchPoll, interval);
        },
      });
    } else {
      fetchPoll();
      timerRef.current = setInterval(fetchPoll, interval);
    }

    return () => {
      wsRef.current?.close?.();
      clearInterval(timerRef.current);
    };
  }, [endpoint, mode, interval, enabled, fetchPoll]);

  const refresh = useCallback(() => {
    setLoading(true);
    fetchPoll();
  }, [fetchPoll]);

  return { checks, loading, error, refresh };
}


/**
 * useWebhook
 * Register/trigger webhook URLs and track their delivery status.
 */
export function useWebhook(domain) {
  const [webhooks, setWebhooks] = useState([]);
  const [sending, setSending]   = useState(null);

  useEffect(() => {
    if (!domain) return;
    api.get(`/api/webhooks/${domain}`)
      .then(r => setWebhooks(r.data || []))
      .catch(() => {});
  }, [domain]);

  async function trigger(webhookId) {
    setSending(webhookId);
    try {
      await api.post(`/api/webhooks/${domain}/${webhookId}/trigger`);
    } finally {
      setSending(null);
    }
  }

  return { webhooks, trigger, sending };
}


/**
 * useDuplexChannel
 * Full-duplex WebSocket channel to a container or service endpoint.
 * Sends messages and receives async replies.
 *
 * Usage:
 *   const { send, messages, connected } = useDuplexChannel('/api/container/example.com/ws');
 */
export function useDuplexChannel(endpoint, { enabled = true } = {}) {
  const [messages, setMessages]   = useState([]);
  const [connected, setConnected] = useState(false);
  const wsRef                     = useRef(null);

  useEffect(() => {
    if (!enabled || !endpoint) return;

    wsRef.current = createWS(endpoint, {
      onOpen:    ()    => setConnected(true),
      onClose:   ()    => setConnected(false),
      onMessage: (msg) => {
        try {
          const parsed = JSON.parse(msg);
          setMessages(prev => [...prev.slice(-99), { ...parsed, ts: Date.now() }]);
        } catch {
          setMessages(prev => [...prev.slice(-99), { raw: msg, ts: Date.now() }]);
        }
      },
    });

    return () => {
      wsRef.current?.close?.();
      setConnected(false);
    };
  }, [endpoint, enabled]);

  const send = useCallback((payload) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
    }
  }, []);

  const clearMessages = useCallback(() => setMessages([]), []);

  return { send, messages, connected, clearMessages };
}
