import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Bot, X, ChevronDown, Send, AlertTriangle, Loader2, Globe,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import api from '../utils/api';

const AGENTS = ['general', 'email', 'database', 'dns', 'ssl', 'files', 'logs', 'security'];

// ── Status bar ────────────────────────────────────────────────────────────────
function StatusBar({ status, domain }) {
  if (status === 'active') {
    return (
      <div className="flex items-center gap-1.5 text-[11px] text-green-400">
        <span className="w-1.5 h-1.5 rounded-full bg-green-400 flex-shrink-0 shadow-[0_0_4px_rgba(74,222,128,0.6)]" />
        Connected to GnuKontrolR
        {domain && <span className="text-ink-muted">— {domain}</span>}
      </div>
    );
  }
  if (status === 'starting') {
    return (
      <div className="flex items-center gap-1.5 text-[11px] text-yellow-400">
        <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 flex-shrink-0 animate-pulse" />
        Connecting…
      </div>
    );
  }
  if (status === 'error') {
    return (
      <div className="flex items-center gap-1.5 text-[11px] text-red-400">
        <span className="w-1.5 h-1.5 rounded-full bg-red-400 flex-shrink-0" />
        Connection error
      </div>
    );
  }
  if (status === 'blocked') {
    return (
      <div className="flex items-center gap-1.5 text-[11px] text-red-400">
        <span className="w-1.5 h-1.5 rounded-full bg-red-400 flex-shrink-0" />
        Session blocked
      </div>
    );
  }
  // idle / stopping
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-ink-muted">
      <span className="w-1.5 h-1.5 rounded-full border border-ink-muted flex-shrink-0" />
      Disconnected
    </div>
  );
}

// ── Legal modal ───────────────────────────────────────────────────────────────
function LegalModal({ onAccept }) {
  return (
    <div className="absolute inset-0 z-10 flex items-center justify-center bg-panel-base/80 backdrop-blur-sm rounded-2xl">
      <div className="mx-4 bg-panel-card border border-panel-subtle rounded-xl shadow-2xl p-5 flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <AlertTriangle size={16} className="text-warn-light flex-shrink-0" />
          <h3 className="text-[13px] font-semibold text-ink-primary">AI Assistant Usage Policy</h3>
        </div>
        <p className="text-[12px] text-ink-secondary leading-relaxed">
          This AI assistant is connected to GnuKontrolR and operates within your
          domain&apos;s security boundary. Sessions are monitored by administrators.
          Abuse of this service will result in suspension.{' '}
          <strong className="text-ink-primary">
            By continuing, you agree to use this assistant responsibly.
          </strong>
        </p>
        <button
          onClick={onAccept}
          className="w-full py-2 rounded-lg bg-brand hover:bg-brand/90 text-white text-[12px] font-semibold transition-colors"
        >
          I Understand &amp; Accept
        </button>
      </div>
    </div>
  );
}

// ── Chat message bubble ───────────────────────────────────────────────────────
function Bubble({ role, content }) {
  const isUser = role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-2`}>
      <div
        className={`max-w-[85%] rounded-xl px-3 py-2 text-[12px] leading-relaxed whitespace-pre-wrap break-words ${
          isUser
            ? 'bg-brand/20 text-ink-primary border border-brand/30'
            : 'bg-panel-elevated text-ink-secondary border border-panel-subtle'
        }`}
      >
        {content}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function AiPanel() {
  const { user } = useAuth();

  const [open, setOpen]                   = useState(false);
  const [domain, setDomain]               = useState(null);
  const [domains, setDomains]             = useState([]);
  const [agent, setAgent]                 = useState('general');
  const [status, setStatus]               = useState('idle'); // idle|starting|active|stopping|error|blocked
  const [messages, setMessages]           = useState([]);
  const [input, setInput]                 = useState('');
  const [warning, setWarning]             = useState(null);
  const [domainsLoaded, setDomainsLoaded] = useState(false);
  const [legalAccepted, setLegalAccepted] = useState(
    () => localStorage.getItem('ai_legal_accepted') === 'true'
  );

  const wsRef           = useRef(null);
  const suspendTimerRef = useRef(null);
  const messagesEndRef  = useRef(null);

  // ── Auto-scroll ──────────────────────────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ── Load domains on first open (after legal accepted) ────────────────────────
  useEffect(() => {
    if (open && !domainsLoaded && legalAccepted) {
      api.get('/api/domains')
        .then(({ data }) => {
          const list  = Array.isArray(data) ? data : (data.domains ?? []);
          const names = list
            .map(d => (typeof d === 'string' ? d : (d.domain ?? d.name)))
            .filter(Boolean);
          setDomains(names);
          if (names.length > 0 && !domain) setDomain(names[0]);
          setDomainsLoaded(true);
        })
        .catch(() => setDomainsLoaded(true));
    }
  }, [open, domainsLoaded, legalAccepted, domain]);

  // ── WebSocket connect ────────────────────────────────────────────────────────
  const connect = useCallback(async (targetDomain, targetAgent) => {
    if (!targetDomain) return;
    setStatus('starting');
    setWarning(null);
    try {
      const { data } = await api.post(
        `/api/ai/start/${targetDomain}?agent=${targetAgent}`
      );

      // Restore history if present (context restore — Task 19)
      if (data.history?.length > 0) {
        setMessages(
          data.history.map(h => ({
            role: h.role === 'user' ? 'user' : 'ai',
            content: h.content,
          }))
        );
      } else {
        setMessages([]);
      }

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(
        `${protocol}//${window.location.host}/api/ai/ws/${targetDomain}/${targetAgent}`
      );
      wsRef.current = ws;

      ws.onopen = () => setStatus('active');

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.type === 'warning') {
            setWarning(msg.content || msg.message || 'Warning from server.');
            return;
          }
          const text = msg.content || msg.message || e.data;
          setMessages(prev => [...prev, { role: 'ai', content: text }]);
        } catch {
          setMessages(prev => [...prev, { role: 'ai', content: e.data }]);
        }
      };

      ws.onclose = (e) => {
        if (e.code === 4008)      setStatus('error');    // session expired
        else if (e.code === 4020) setStatus('blocked');  // abuse block
        else                      setStatus('idle');
        wsRef.current = null;
      };

      ws.onerror = () => setStatus('error');
    } catch {
      setStatus('error');
    }
  }, []);

  // ── Auto-start when panel opens and domain is available ──────────────────────
  useEffect(() => {
    if (open && legalAccepted && domain && status === 'idle' && domainsLoaded) {
      connect(domain, agent);
    }
  }, [open, legalAccepted, domain, status, domainsLoaded, connect, agent]);

  // ── Open: cancel pending suspend ─────────────────────────────────────────────
  const handleOpen = () => {
    if (suspendTimerRef.current) {
      clearTimeout(suspendTimerRef.current);
      suspendTimerRef.current = null;
    }
    setOpen(true);
    // If status was idle after a completed auto-stop, auto-start triggers via
    // the useEffect above once domain is confirmed available.
  };

  // ── Close: start 60-second auto-suspend countdown (Task 19) ─────────────────
  const handleClose = () => {
    setOpen(false);
    if (status === 'active' && domain) {
      suspendTimerRef.current = setTimeout(async () => {
        try {
          await api.delete(`/api/ai/stop/${domain}?save_context=true`);
        } catch {
          // best-effort — context saved if possible
        }
        if (wsRef.current) {
          wsRef.current.close();
          wsRef.current = null;
        }
        setStatus('idle');
        setMessages([]); // history preserved server-side; will be restored on reconnect
        suspendTimerRef.current = null;
      }, 60000);
    }
  };

  // ── Send message ─────────────────────────────────────────────────────────────
  const send = () => {
    if (!input.trim() || !wsRef.current || status !== 'active') return;
    const text = input.trim();
    wsRef.current.send(JSON.stringify({ type: 'message', content: text }));
    setMessages(prev => [...prev, { role: 'user', content: text }]);
    setInput('');
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  // ── Agent switch: close WS + re-connect with new agent ───────────────────────
  const handleAgentChange = (newAgent) => {
    if (newAgent === agent) return;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setAgent(newAgent);
    setStatus('idle');
    setMessages([]);
  };

  // ── Domain switch: stop current session + reconnect ──────────────────────────
  const handleDomainChange = (newDomain) => {
    if (newDomain === domain) return;
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (domain && (status === 'active' || status === 'starting')) {
      api.delete(`/api/ai/stop/${domain}?save_context=true`).catch(() => {});
    }
    setDomain(newDomain);
    setStatus('idle');
    setMessages([]);
  };

  // ── Logout cleanup: immediate stop, no 60s delay ────────────────────────────
  useEffect(() => {
    if (!user) {
      if (suspendTimerRef.current) {
        clearTimeout(suspendTimerRef.current);
        suspendTimerRef.current = null;
      }
      if ((status === 'active' || status === 'starting') && domain) {
        api.delete(`/api/ai/stop/${domain}`).catch(() => {});
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setStatus('idle');
      setMessages([]);
      setOpen(false);
    }
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Accept legal ─────────────────────────────────────────────────────────────
  const acceptLegal = () => {
    localStorage.setItem('ai_legal_accepted', 'true');
    setLegalAccepted(true);
  };

  // Don't render when not logged in
  if (!user) return null;

  return (
    <>
      {/* ── Floating panel ─────────────────────────────────────────────────── */}
      {open && (
        <div
          className="fixed bottom-20 right-5 z-50 flex flex-col bg-panel-surface border border-panel-subtle rounded-2xl shadow-2xl overflow-hidden"
          style={{ width: 380, height: 540 }}
        >
          {/* Legal acceptance overlay */}
          {!legalAccepted && <LegalModal onAccept={acceptLegal} />}

          {/* ── Header ─────────────────────────────────────────────────── */}
          <div className="flex items-center justify-between px-4 py-2.5 border-b border-panel-subtle bg-panel-card flex-shrink-0">
            <div className="flex items-center gap-2">
              <div
                className="w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0"
                style={{ background: 'linear-gradient(135deg,#6366f1,#8b5cf6)' }}
              >
                <Bot size={13} className="text-white" />
              </div>
              <span className="text-[13px] font-semibold text-ink-primary">AI Assistant</span>
            </div>
            <button
              onClick={handleClose}
              className="text-ink-muted hover:text-ink-primary transition-colors rounded-md p-1 hover:bg-panel-elevated"
              aria-label="Close AI assistant"
            >
              <X size={14} />
            </button>
          </div>

          {/* ── Domain selector ────────────────────────────────────────── */}
          <div className="px-3 pt-2.5 flex-shrink-0">
            <div className="relative">
              <Globe
                size={12}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint pointer-events-none"
              />
              <select
                value={domain ?? ''}
                onChange={e => handleDomainChange(e.target.value)}
                disabled={status === 'starting' || domains.length === 0}
                className="w-full pl-7 pr-7 py-1.5 rounded-lg bg-panel-elevated border border-panel-subtle text-[12px] text-ink-primary appearance-none cursor-pointer disabled:opacity-50 disabled:cursor-default focus:outline-none focus:ring-1 focus:ring-brand/50"
              >
                {domains.length === 0 && (
                  <option value="">Loading domains…</option>
                )}
                {domains.map(d => (
                  <option key={d} value={d}>{d}</option>
                ))}
              </select>
              <ChevronDown
                size={11}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-muted pointer-events-none"
              />
            </div>
          </div>

          {/* ── Agent chips ────────────────────────────────────────────── */}
          <div className="px-3 pt-2 flex-shrink-0">
            <div className="flex gap-1.5 overflow-x-auto pb-0.5" style={{ scrollbarWidth: 'none' }}>
              {AGENTS.map(a => (
                <button
                  key={a}
                  onClick={() => handleAgentChange(a)}
                  className={`flex-shrink-0 px-2.5 py-1 rounded-full text-[11px] font-medium transition-colors border ${
                    a === agent
                      ? 'bg-brand/20 text-brand-light border-brand/40'
                      : 'bg-panel-elevated text-ink-muted border-panel-subtle hover:text-ink-secondary hover:bg-panel-card'
                  }`}
                >
                  {a}
                </button>
              ))}
            </div>
          </div>

          {/* ── Status bar ─────────────────────────────────────────────── */}
          <div className="px-3 py-1.5 flex-shrink-0">
            <StatusBar status={status} domain={domain} />
          </div>

          {/* ── Warning banner ─────────────────────────────────────────── */}
          {warning && (
            <div className="mx-3 mb-1 px-3 py-1.5 rounded-lg bg-warn/10 border border-warn/30 flex items-start gap-2 flex-shrink-0">
              <AlertTriangle size={12} className="text-warn-light flex-shrink-0 mt-0.5" />
              <span className="text-[11px] text-warn-light leading-relaxed flex-1">
                {warning}
              </span>
              <button
                onClick={() => setWarning(null)}
                className="text-warn-light/60 hover:text-warn-light transition-colors flex-shrink-0"
                aria-label="Dismiss warning"
              >
                <X size={11} />
              </button>
            </div>
          )}

          {/* ── Chat thread ────────────────────────────────────────────── */}
          <div className="flex-1 overflow-y-auto px-3 py-2 min-h-0">
            {status === 'starting' && messages.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <div className="flex items-center gap-2 text-ink-muted text-[12px]">
                  <Loader2 size={14} className="animate-spin" />
                  Starting session…
                </div>
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full gap-2 text-center">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center opacity-40"
                  style={{ background: 'linear-gradient(135deg,#6366f1,#8b5cf6)' }}
                >
                  <Bot size={20} className="text-white" />
                </div>
                <p className="text-[12px] text-ink-faint max-w-[220px] leading-relaxed">
                  {status === 'error'
                    ? 'Connection failed. Try closing and reopening the panel.'
                    : status === 'blocked'
                    ? 'Your session has been blocked by an administrator.'
                    : domain
                    ? 'Session ready. Say hello!'
                    : 'Loading your domains…'}
                </p>
              </div>
            ) : (
              messages.map((m, i) => (
                <Bubble key={i} role={m.role} content={m.content} />
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* ── Input row ──────────────────────────────────────────────── */}
          <div className="border-t border-panel-subtle px-3 py-2.5 flex gap-2 items-end flex-shrink-0 bg-panel-card">
            <textarea
              rows={1}
              placeholder={
                status === 'active'
                  ? 'Ask anything…'
                  : status === 'starting'
                  ? 'Connecting…'
                  : 'Not connected'
              }
              disabled={status !== 'active'}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              className="flex-1 resize-none bg-panel-elevated border border-panel-subtle rounded-lg px-3 py-2 text-[12px] text-ink-primary placeholder:text-ink-faint focus:outline-none focus:ring-1 focus:ring-brand/50 disabled:opacity-40 max-h-24 leading-relaxed"
              style={{ minHeight: 36 }}
            />
            <button
              onClick={send}
              disabled={status !== 'active' || !input.trim()}
              className="w-9 h-9 rounded-lg bg-brand hover:bg-brand/90 disabled:opacity-40 disabled:cursor-default flex items-center justify-center transition-colors flex-shrink-0"
              aria-label="Send message"
            >
              <Send size={14} className="text-white" />
            </button>
          </div>
        </div>
      )}

      {/* ── FAB (floating action button) ───────────────────────────────────── */}
      <button
        onClick={open ? handleClose : handleOpen}
        className="fixed bottom-5 right-5 z-50 w-12 h-12 rounded-full shadow-lg flex items-center justify-center transition-all duration-200 hover:scale-105 active:scale-95 relative"
        style={{
          background: 'linear-gradient(135deg,#6366f1,#8b5cf6)',
          boxShadow: '0 4px 20px rgba(99,102,241,0.45)',
        }}
        aria-label={open ? 'Close AI assistant' : 'Open AI assistant'}
        title={open ? 'Close AI assistant' : 'Open AI assistant'}
      >
        {open ? (
          <ChevronDown size={20} className="text-white" />
        ) : (
          <Bot size={20} className="text-white" />
        )}
        {/* Green dot when active session is running in background */}
        {status === 'active' && !open && (
          <span className="absolute top-0.5 right-0.5 w-2.5 h-2.5 rounded-full bg-green-400 border-2 border-panel-base" />
        )}
      </button>
    </>
  );
}
