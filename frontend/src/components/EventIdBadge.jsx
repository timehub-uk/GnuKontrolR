/**
 * EventIdBadge
 * Displays the X-Request-ID event UUID alongside error messages so admins
 * can paste it into server logs to trace exactly what went wrong.
 *
 * Usage:
 *   import { useEventId } from '../components/EventIdBadge';
 *   const eventId = useEventId();           // after a failed api call
 *   <EventIdBadge id={eventId} />
 *
 * Or inline:
 *   <EventIdBadge />                        // reads api.lastEventId automatically
 */
import { useState } from 'react';
import { Hash, Copy, CheckCircle } from 'lucide-react';
import api from '../utils/api';

export function useEventId() {
  return api.lastEventId;
}

export default function EventIdBadge({ id }) {
  const eventId = id ?? api.lastEventId;
  const [copied, setCopied] = useState(false);

  if (!eventId) return null;

  const copy = async () => {
    await navigator.clipboard.writeText(eventId).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex items-center gap-1.5 mt-1">
      <Hash size={10} className="text-gray-600 flex-shrink-0" />
      <span className="text-xs font-mono text-gray-600 select-all tracking-tight">
        {eventId}
      </span>
      <button
        onClick={copy}
        title="Copy event ID for support"
        className="text-gray-600 hover:text-gray-400 transition-colors"
      >
        {copied
          ? <CheckCircle size={10} className="text-green-500" />
          : <Copy size={10} />}
      </button>
    </div>
  );
}
