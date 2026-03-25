/**
 * Toggle — animated live switch with loading + error states.
 *
 * Props:
 *   checked    boolean
 *   onChange   async fn(newValue) — can throw; error shown inline
 *   label      string
 *   description string (optional)
 *   disabled   boolean
 *   size       'sm' | 'md' (default md)
 *   colorOn    'green' | 'blue' | 'brand' (default green)
 */
import { useState } from 'react';
import { Loader, AlertCircle } from 'lucide-react';

const SIZES = {
  sm: { track: 'w-8 h-4',  thumb: 'w-3 h-3',  translate: 'translate-x-4' },
  md: { track: 'w-11 h-6', thumb: 'w-5 h-5',  translate: 'translate-x-5' },
};

const COLORS = {
  green: 'bg-ok',
  blue:  'bg-brand',
  brand: 'bg-brand',
};

export default function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled = false,
  size = 'md',
  colorOn = 'green',
}) {
  const [pending, setPending] = useState(false);
  const [error, setError]     = useState('');
  const sz  = SIZES[size] || SIZES.md;
  const col = COLORS[colorOn] || COLORS.green;

  async function handle() {
    if (disabled || pending) return;
    setError('');
    setPending(true);
    try {
      await onChange(!checked);
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || 'Failed');
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex items-start gap-3">
      {/* Track */}
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled || pending}
        onClick={handle}
        className={[
          'relative inline-flex flex-shrink-0 rounded-full border-2 border-transparent',
          'transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2',
          'focus:ring-brand focus:ring-offset-2 focus:ring-offset-panel-surface',
          sz.track,
          checked ? col : 'bg-panel-subtle',
          disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer',
        ].join(' ')}
      >
        {/* Thumb */}
        <span
          className={[
            'pointer-events-none inline-block rounded-full bg-white shadow',
            'transform transition-transform duration-200 ease-in-out',
            sz.thumb,
            checked ? sz.translate : 'translate-x-0',
          ].join(' ')}
        />
      </button>

      {/* Label + state */}
      {(label || description || pending || error) && (
        <div className="flex flex-col min-w-0">
          <span className="flex items-center gap-1.5">
            {label && (
              <span className="text-sm font-medium text-ink-secondary">{label}</span>
            )}
            {pending && <Loader size={12} className="animate-spin text-brand" />}
            {error && !pending && (
              <span className="flex items-center gap-1 text-xs text-bad-light">
                <AlertCircle size={11} /> {error}
              </span>
            )}
          </span>
          {description && (
            <span className="text-xs text-ink-muted mt-0.5">{description}</span>
          )}
        </div>
      )}
    </div>
  );
}
