import { format, formatDistanceToNow, parseISO, isValid } from 'date-fns';

export function fmtDate(dateStr) {
  if (!dateStr) return '—';
  try {
    const d = typeof dateStr === 'string' ? parseISO(dateStr) : new Date(dateStr);
    return isValid(d) ? format(d, 'dd MMM yyyy') : '—';
  } catch { return '—'; }
}

export function fmtDateTime(dateStr) {
  if (!dateStr) return '—';
  try {
    const d = typeof dateStr === 'string' ? parseISO(dateStr) : new Date(dateStr);
    return isValid(d) ? format(d, 'dd MMM yyyy HH:mm') : '—';
  } catch { return '—'; }
}

export function fmtRelative(dateStr) {
  if (!dateStr) return '—';
  try {
    const d = typeof dateStr === 'string' ? parseISO(dateStr) : new Date(dateStr);
    return isValid(d) ? formatDistanceToNow(d, { addSuffix: true }) : '—';
  } catch { return '—'; }
}
