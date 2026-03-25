import { z } from 'zod';

export const domainSchema = z.object({
  name: z.string().min(3, 'Domain too short').regex(
    /^[a-zA-Z0-9][a-zA-Z0-9-_.]+\.[a-zA-Z]{2,}$/,
    'Invalid domain format'
  ),
  php_version: z.enum(['8.3', '8.2', '8.1', '8.0', '7.4']),
  domain_type: z.enum(['main', 'addon', 'subdomain', 'parked', 'redirect']),
});

export const loginSchema = z.object({
  username: z.string().min(1, 'Username required'),
  password: z.string().min(1, 'Password required'),
});

export const userSchema = z.object({
  username: z.string().min(3, 'At least 3 characters').max(32),
  email: z.string().email('Invalid email'),
  password: z.string().min(8, 'At least 8 characters'),
  role: z.enum(['user', 'reseller', 'admin', 'superadmin']),
});
