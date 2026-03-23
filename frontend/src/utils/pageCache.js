/**
 * Simple module-level page cache.
 * Survives React component unmount/remount (navigation away and back).
 * Does NOT survive a full page reload — intentional; stale data on hard refresh is a bug.
 *
 * Usage in a page component:
 *   const { data, loading, refresh } = useCachedFetch('/api/domains', 'domains');
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import api from './api';

const _cache = new Map();   // key → { data, fetchedAt }

export function getCached(key) {
  return _cache.get(key) ?? null;
}

export function setCached(key, data) {
  _cache.set(key, { data, fetchedAt: Date.now() });
}

export function invalidate(key) {
  _cache.delete(key);
}

export function invalidatePrefix(prefix) {
  for (const k of _cache.keys()) {
    if (k.startsWith(prefix)) _cache.delete(k);
  }
}

/**
 * Hook: fetch once, serve from cache on subsequent mounts.
 *
 * @param {string}  url       API path
 * @param {string}  cacheKey  Unique cache key (defaults to url)
 * @param {number}  ttl       Max age in ms before re-fetch (default: 60 000)
 */
export function useCachedFetch(url, cacheKey, { ttl = 60_000, transform = null } = {}) {
  const key     = cacheKey || url;
  const cached  = getCached(key);
  const isStale = !cached || (Date.now() - cached.fetchedAt) > ttl;

  const [data,    setData]    = useState(cached?.data ?? null);
  const [loading, setLoading] = useState(isStale);
  const [error,   setError]   = useState(null);
  const mounted = useRef(true);

  const fetch_ = useCallback(async (force = false) => {
    const c = getCached(key);
    if (!force && c && (Date.now() - c.fetchedAt) <= ttl) {
      setData(c.data);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res  = await api.get(url);
      const value = transform ? transform(res.data) : res.data;
      setCached(key, value);
      if (mounted.current) setData(value);
    } catch (e) {
      if (mounted.current) setError(e?.response?.data?.detail || 'Load failed');
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [url, key, ttl, transform]);

  useEffect(() => {
    mounted.current = true;
    fetch_();
    return () => { mounted.current = false; };
  }, [fetch_]);

  const refresh = useCallback(() => fetch_(true), [fetch_]);

  return { data, loading, error, refresh };
}
