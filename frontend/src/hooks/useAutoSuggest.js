/**
 * useAutoSuggest
 * Returns filtered suggestions from a static list or remote API.
 *
 * Usage (static):
 *   const { suggestions, select, active, setActive } =
 *     useAutoSuggest(query, { items: ['nginx','apache','lighttpd'] });
 *
 * Usage (remote):
 *   const { suggestions } =
 *     useAutoSuggest(query, { endpoint: '/api/domains/suggest' });
 *
 * Keyboard nav: call onKeyDown(e) on the input.
 */
import { useState, useEffect, useCallback } from 'react';
import { useDebounce } from './useDebounce';
import api from '../utils/api';

export function useAutoSuggest(query, { items = null, endpoint = null, minLength = 1 } = {}) {
  const [suggestions, setSuggestions] = useState([]);
  const [active, setActive]           = useState(-1);
  const [open, setOpen]               = useState(false);
  const debounced                     = useDebounce(query, 200);

  useEffect(() => {
    if (!debounced || debounced.length < minLength) {
      setSuggestions([]);
      setOpen(false);
      return;
    }

    if (items) {
      const q = debounced.toLowerCase();
      const filtered = items.filter(i => i.toLowerCase().includes(q)).slice(0, 8);
      setSuggestions(filtered);
      setOpen(filtered.length > 0);
      setActive(-1);
    } else if (endpoint) {
      api.get(endpoint, { params: { q: debounced } })
        .then(r => {
          const results = Array.isArray(r.data) ? r.data : r.data.results || [];
          setSuggestions(results.slice(0, 8));
          setOpen(results.length > 0);
          setActive(-1);
        })
        .catch(() => setSuggestions([]));
    }
  }, [debounced, items, endpoint, minLength]);

  const select = useCallback((item) => {
    setOpen(false);
    setSuggestions([]);
    return item;
  }, []);

  const onKeyDown = useCallback((e, onSelect) => {
    if (!open) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive(a => Math.min(a + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive(a => Math.max(a - 1, 0));
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault();
      onSelect(select(suggestions[active]));
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  }, [open, suggestions, active, select]);

  return { suggestions, active, setActive, open, setOpen, select, onKeyDown };
}
