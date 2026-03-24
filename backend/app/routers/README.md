# backend/app/routers/

API route handlers — one file per feature group.

| File | Prefix | Auth required | Description |
|---|---|---|---|
| `auth.py` | `/api/auth` | No (login/register) | Token login, registration, /me |
| `users.py` | `/api/users` | admin+ | User CRUD, quota management |
| `domains.py` | `/api/domains` | user+ | Domain add/update/delete |
| `docker_mgr.py` | `/api/docker` | admin+ | Container lifecycle, port allocation |
| `services.py` | `/api/services` | user+ | Per-container service marketplace |
| `server.py` | `/api/server` | user+ (stats), admin+ (control) | Host stats, service control, WS live feed |
| `security.py` | `/api/security` | user+ | Security advisor, auto-fix, WS stream |
| `activity_log.py` | `/api/log` | user+ | Per-user request history |
| `container_proxy.py` | `/api/container` | user+ | Proxy to per-domain container API (port 9000) |
| `admin_content.py` | `/api/admin/content` | superadmin + PIN | File browser with PIN-protected access |
| `marketplace.py` | `/api/marketplace` | user+ | One-click app installer catalogue |

## Auth guards (from `auth.py`)

```python
Depends(get_current_user)   # any authenticated user
Depends(require_admin)      # admin or superadmin
Depends(require_superadmin) # superadmin only
Depends(require_reseller)   # reseller, admin, or superadmin
```
