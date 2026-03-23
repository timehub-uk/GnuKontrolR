/**
 * SmartInput — input with:
 *   • Live validation (errors / warnings / suggestions shown inline)
 *   • Autocomplete dropdown from static list or API endpoint
 *   • Error resolution hints with one-click fix callbacks
 *   • Security advice badge
 *
 * Props:
 *   value, onChange(v)          controlled input
 *   label, placeholder, type
 *   rules                       useLiveValidation rule array
 *   suggestItems                string[]  (static autocomplete list)
 *   suggestEndpoint             string    (API endpoint for suggestions)
 *   onSuggestionSelect(v)       callback when suggestion chosen
 *   showStrength                bool      (password strength meter)
 *   required                    bool
 *   className                   extra classes on wrapper
 */
import { useState, useRef } from 'react';
import { AlertCircle, AlertTriangle, Lightbulb, CheckCircle, Eye, EyeOff } from 'lucide-react';
import { useLiveValidation } from '../hooks/useLiveValidation';
import { useAutoSuggest }    from '../hooks/useAutoSuggest';

function StrengthMeter({ value }) {
  const score = [
    value.length >= 12,
    /[A-Z]/.test(value),
    /[0-9]/.test(value),
    /[^A-Za-z0-9]/.test(value),
    value.length >= 20,
  ].filter(Boolean).length;

  const labels = ['', 'Weak', 'Fair', 'Good', 'Strong', 'Excellent'];
  const colors = ['', 'bg-red-500', 'bg-orange-500', 'bg-yellow-500', 'bg-green-400', 'bg-green-500'];

  return (
    <div className="mt-1.5 space-y-1">
      <div className="flex gap-1">
        {[1,2,3,4,5].map(i => (
          <div
            key={i}
            className={`h-1 flex-1 rounded-full transition-colors duration-300 ${
              i <= score ? colors[score] : 'bg-panel-600'
            }`}
          />
        ))}
      </div>
      {value.length > 0 && (
        <p className={`text-xs ${score >= 4 ? 'text-green-400' : score >= 3 ? 'text-yellow-400' : 'text-red-400'}`}>
          Password strength: {labels[score]}
        </p>
      )}
    </div>
  );
}

export default function SmartInput({
  value,
  onChange,
  label,
  placeholder,
  type = 'text',
  rules = [],
  suggestItems = null,
  suggestEndpoint = null,
  onSuggestionSelect,
  showStrength = false,
  required = false,
  className = '',
  ...rest
}) {
  const [touched, setTouched]     = useState(false);
  const [showPwd, setShowPwd]     = useState(false);
  const inputRef                  = useRef(null);
  const wrapRef                   = useRef(null);

  const validation = useLiveValidation(value, rules);
  const suggest    = useAutoSuggest(value, {
    items:    suggestItems,
    endpoint: suggestEndpoint,
  });

  const inputType = type === 'password' ? (showPwd ? 'text' : 'password') : type;
  const showErrors = touched && validation.errors.length > 0;

  function handleSelect(item) {
    const chosen = suggest.select(item);
    onChange(chosen);
    onSuggestionSelect?.(chosen);
    inputRef.current?.focus();
  }

  return (
    <div className={`relative space-y-1 ${className}`} ref={wrapRef}>
      {label && (
        <label className="block text-sm font-medium text-gray-300">
          {label}
          {required && <span className="text-red-400 ml-1">*</span>}
        </label>
      )}

      {/* Input row */}
      <div className="relative">
        <input
          ref={inputRef}
          type={inputType}
          value={value}
          placeholder={placeholder}
          onChange={e => onChange(e.target.value)}
          onBlur={() => setTouched(true)}
          onKeyDown={e => suggest.onKeyDown(e, handleSelect)}
          onFocus={() => value && suggest.setOpen(true)}
          className={[
            'input pr-8',
            showErrors ? 'border-red-500 focus:border-red-500' : '',
            touched && validation.valid && value ? 'border-green-600' : '',
          ].join(' ')}
          {...rest}
        />

        {/* Right icon */}
        <div className="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
          {type === 'password' && (
            <button type="button" onClick={() => setShowPwd(s => !s)}
              className="text-gray-500 hover:text-gray-300">
              {showPwd ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          )}
          {touched && value.length > 0 && (
            validation.valid
              ? <CheckCircle size={14} className="text-green-500" />
              : <AlertCircle size={14} className="text-red-400" />
          )}
        </div>
      </div>

      {/* Autocomplete dropdown */}
      {suggest.open && suggest.suggestions.length > 0 && (
        <div className="absolute z-50 w-full mt-1 bg-panel-800 border border-panel-500 rounded-lg shadow-xl overflow-hidden">
          {suggest.suggestions.map((s, i) => (
            <button
              key={s}
              type="button"
              onMouseDown={e => { e.preventDefault(); handleSelect(s); }}
              className={[
                'w-full text-left px-3 py-2 text-sm transition-colors',
                i === suggest.active
                  ? 'bg-brand-600/30 text-brand-300'
                  : 'text-gray-200 hover:bg-panel-700',
              ].join(' ')}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Password strength meter */}
      {showStrength && type === 'password' && value.length > 0 && (
        <StrengthMeter value={value} />
      )}

      {/* Validation feedback */}
      {touched && (
        <div className="space-y-0.5">
          {validation.errors.map(e => (
            <p key={e} className="flex items-center gap-1.5 text-xs text-red-400">
              <AlertCircle size={11} className="flex-shrink-0" /> {e}
            </p>
          ))}
          {validation.warnings.map(w => (
            <p key={w} className="flex items-center gap-1.5 text-xs text-yellow-400">
              <AlertTriangle size={11} className="flex-shrink-0" /> {w}
            </p>
          ))}
          {validation.suggestions.map(s => (
            <p key={s} className="flex items-center gap-1.5 text-xs text-blue-400">
              <Lightbulb size={11} className="flex-shrink-0" /> {s}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
