# backend/

FastAPI application — the GnuKontrolR control panel API.

## Structure

```
backend/
├── Dockerfile           Multi-stage build (builder → slim runtime)
├── requirements.txt     Pinned Python dependencies
└── app/
    ├── main.py          App entry, middleware (CORS, HTTPS redirect,
    │                    request lifecycle, Prometheus metrics endpoint)
    ├── auth.py          JWT (HS256), bcrypt password hashing, role guards
    ├── database.py      SQLAlchemy async engine — SQLite via aiosqlite
    ├── cache.py         Redis async cache (graceful no-op fallback)
    ├── models/          ORM table definitions
    └── routers/         One file per API feature group
```

## Running locally (dev)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The app reads config from environment variables (see `../.env.example`).
In development, CORS allows `localhost:5173` automatically.

## Database

SQLite database is stored at `/app/data/webpanel.db` inside the container.
The `webpanel_db` Docker volume mounts at `/app/data` so data persists across restarts.

## Authentication flow

1. `POST /api/auth/token` — returns `access_token` (60 min) + `refresh_token` (7 days)
2. All other `/api/*` routes require `Authorization: Bearer <access_token>`
3. Role hierarchy: `superadmin > admin > reseller > user`

## Adding a new router

1. Create `app/routers/my_feature.py` with `router = APIRouter(prefix="/api/my_feature")`
2. Import and include it in `app/main.py`
