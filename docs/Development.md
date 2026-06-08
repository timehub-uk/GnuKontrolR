# Development

## Prerequisites

- Docker 24+
- Docker Compose v2+
- Node.js 20+
- Python 3.11+
- Git

## Local Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/timehub-uk/GnuKontrolR.git
cd GnuKontrolR
```

### 2. Frontend Development

```bash
cd frontend
npm install
npm run dev    # Vite dev server on :5173
```

The frontend runs independently with hot-reload. API calls are proxied to the panel container.

### 3. Backend Development

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Or develop inside Docker for full integration:

```bash
# Start the full stack
sudo bash setup.sh install

# View logs
docker compose logs -f webpanel_api
```

### 4. Database Setup

For local development outside Docker:

```bash
# Start only the databases
docker compose up -d mysql postgres redis
```

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, middleware, CORS
│   ├── auth.py              # JWT auth, password hashing
│   ├── database.py          # DB engine, session management
│   ├── cli.py               # CLI tool
│   ├── models/              # SQLAlchemy models
│   │   ├── user.py
│   │   ├── domain.py
│   │   ├── site.py
│   │   ├── site_backup.py
│   │   └── ...
│   ├── routers/             # API route handlers
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── domains.py
│   │   ├── dns.py
│   │   ├── terminal.py
│   │   ├── fail2ban.py
│   │   ├── cve.py
│   │   └── ...
│   └── schemas/             # Pydantic schemas
│       ├── user.py
│       ├── domain.py
│       └── ...
└── requirements.txt

frontend/
├── src/
│   ├── App.tsx              # Main app, routing
│   ├── main.tsx             # Entry point
│   ├── components/          # Reusable components
│   ├── pages/               # Page views
│   ├── services/            # API client, auth store
│   └── stores/              # Zustand state stores
├── index.html
├── vite.config.ts
├── tailwind.config.js
└── package.json

docker/
├── site-template/
│   ├── Dockerfile           # Customer site container
│   ├── nginx.conf
│   └── container_api.py     # Site container management API
├── traefik/
│   └── dynamic/             # Traefik dynamic config
└── powerdns/
    └── pdns.conf

docker-compose.yml           # Service definitions
setup.sh                     # Installer & management
```

## Code Conventions

### Python (Backend)

- **Framework**: FastAPI with async routes
- **ORM**: SQLAlchemy 2.0 async
- **Auth**: JWT with python-jose
- **Formatting**: PEP 8
- **Imports**: standard lib → third-party → local

### TypeScript/React (Frontend)

- **Framework**: React 18 with TypeScript
- **State**: Zustand stores
- **Styling**: Tailwind CSS
- **Components**: Functional components with hooks
- **Routing**: React Router v6

## Making Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make changes
4. Test locally
5. Submit a pull request

## Testing

```bash
# Backend tests (if available)
cd backend
pytest

# Frontend build check
cd frontend
npm run build

# Full integration test
sudo bash setup.sh cmd_test
```
