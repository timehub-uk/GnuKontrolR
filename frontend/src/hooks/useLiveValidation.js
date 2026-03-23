/**
 * useLiveValidation
 * Runs a set of validator rules against a value and returns
 * { valid, errors, warnings, suggestions } reactively.
 *
 * Rules format:
 *   [{ test: fn(v) => bool, message: string, level: 'error'|'warning'|'suggestion' }]
 *
 * Example:
 *   const v = useLiveValidation(email, [
 *     { test: v => v.includes('@'), message: 'Must be a valid email', level: 'error' },
 *     { test: v => !v.endsWith('.ru'), message: 'Unusual TLD', level: 'warning' },
 *   ]);
 */
import { useMemo } from 'react';

export function useLiveValidation(value, rules = []) {
  return useMemo(() => {
    const errors      = [];
    const warnings    = [];
    const suggestions = [];

    for (const rule of rules) {
      if (!rule.test(value)) {
        if (rule.level === 'warning')    warnings.push(rule.message);
        else if (rule.level === 'suggestion') suggestions.push(rule.message);
        else errors.push(rule.message);
      }
    }

    return {
      valid:       errors.length === 0,
      errors,
      warnings,
      suggestions,
      hasIssues:   errors.length > 0 || warnings.length > 0,
    };
  }, [value, rules]);
}

// ── Pre-built rule sets ───────────────────────────────────────────────────────

export const DOMAIN_RULES = [
  { test: v => v.length > 0,                message: 'Domain name is required',          level: 'error' },
  { test: v => /^[a-z0-9.-]+$/.test(v),     message: 'Only lowercase letters, numbers, dots, hyphens', level: 'error' },
  { test: v => v.includes('.'),             message: 'Must include a TLD (e.g. .com)',   level: 'error' },
  { test: v => !v.startsWith('-'),          message: 'Cannot start with a hyphen',       level: 'error' },
  { test: v => v.length <= 253,             message: 'Domain too long (max 253 chars)',  level: 'error' },
  { test: v => !v.startsWith('www.'),       message: 'Add without www — panel adds it',  level: 'suggestion' },
];

export const PASSWORD_RULES = [
  { test: v => v.length >= 12,              message: 'Use at least 12 characters',       level: 'error' },
  { test: v => /[A-Z]/.test(v),            message: 'Add an uppercase letter',           level: 'warning' },
  { test: v => /[0-9]/.test(v),            message: 'Add a number',                      level: 'warning' },
  { test: v => /[^A-Za-z0-9]/.test(v),    message: 'Add a special character (!@#...)',  level: 'suggestion' },
  { test: v => !/^(.)\1+$/.test(v),        message: 'Avoid repeated characters',         level: 'warning' },
];

export const EMAIL_RULES = [
  { test: v => v.length > 0,               message: 'Email is required',                level: 'error' },
  { test: v => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v), message: 'Enter a valid email address', level: 'error' },
];

export const USERNAME_RULES = [
  { test: v => v.length >= 3,              message: 'At least 3 characters',            level: 'error' },
  { test: v => /^[a-z0-9_-]+$/.test(v),   message: 'Lowercase letters, numbers, _ or - only', level: 'error' },
  { test: v => !['admin','root','test','user'].includes(v), message: 'Choose a less common username', level: 'warning' },
];

export const PIN_RULES = [
  { test: v => /^\d{6}$/.test(v),          message: 'PIN must be exactly 6 digits',     level: 'error' },
  { test: v => !/^(\d)\1{5}$/.test(v),     message: 'Avoid repeated digits (111111)',   level: 'warning' },
  { test: v => !['123456','654321','000000','111111','123123'].includes(v), message: 'Too predictable — choose a random PIN', level: 'warning' },
];
