# Installation

## Requirements

- **OS**: Ubuntu 22.04+ / Debian 12+ (or any Linux with Docker support)
- **Docker**: 24.0+ with Docker Compose plugin v2+
- **CPU**: 2+ cores
- **RAM**: 4 GB minimum, 8 GB recommended
- **Disk**: 20 GB+ free
- **Domain**: a domain pointed to your server IP (for panel access and customer sites)

## Quick Install

```bash
git clone https://github.com/timehub-uk/GnuKontrolR.git
cd GnuKontrolR
sudo bash setup.sh install
```

The installer will:

1. Check prerequisites (Docker, Git, sudo)
2. Detect your server IP and Docker socket GID
3. Generate `.env` with random secrets (DB passwords, API keys, JWT secret)
4. Prompt for the panel domain and admin credentials
5. Build all Docker images and start containers
6. Create the superadmin account

## Configuration Prompts

During installation you'll be asked for:

| Prompt | Description |
|--------|-------------|
| **Panel Domain** | Public domain for the panel UI (e.g., `panel.example.com`) |
| **Server IP** | Public IP address of the server |
| **Admin Username** | Superadmin login username |
| **Admin Email** | Superadmin email address |
| **Admin Password** | Superadmin login password |

## Generated `.env` File

The installer creates `.env` with the following:

```ini
PANEL_DOMAIN=panel.example.com
SERVER_IP=1.2.3.4
MYSQL_ROOT_PASSWORD=<random>
POSTGRES_PASSWORD=<random>
SECRET_KEY=<random>
PDNS_API_KEY=<random>
DOCKER_SOCK_GID=129
```

## Post-Install

After installation:

1. Access the panel at `https://your-panel-domain:8443`
2. Log in with the admin credentials you created
3. Go to **Domains** to add your first customer domain
4. Go to **DNS** to configure DNS zones

## Manual Configuration

If `setup.sh install` fails or you need to customise:

### Port 53 Conflict

If systemd-resolved is already using port 53 (common on Ubuntu), the installer will detect this and offer to:

- **Auto-fix**: temporarily disable systemd-resolved's DNSStubListener
- **Skip**: leave PowerDNS disabled (manual fix later)
- **Cancel**: abort installation

After install, PowerDNS can be re-enabled by editing `docker-compose.yml` and restarting.

### Docker Socket GID

The Docker socket GID varies by system. The installer detects it automatically. If it changes later, update `DOCKER_SOCK_GID` in `.env`.

## Directory Layout

```
/opt/gnukontrolr/
├── backend/              # FastAPI Python application
│   ├── app/
│   │   ├── routers/      # API route handlers
│   │   ├── models/       # SQLAlchemy models
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── auth.py       # JWT authentication
│   │   ├── database.py   # DB connection management
│   │   └── cli.py        # panel CLI tool
│   └── requirements.txt
├── frontend/             # React + Vite SPA
│   ├── src/
│   │   ├── components/   # Reusable UI components
│   │   ├── pages/        # Page views
│   │   ├── services/     # API client
│   │   └── stores/       # State management (Zustand)
│   └── dist/             # Built frontend
├── docker/               # Docker configurations
│   ├── traefik/          # Traefik dynamic config
│   ├── powerdns/         # PowerDNS config
│   └── site-template/    # Customer site container
├── docker-compose.yml    # Service definitions
├── setup.sh              # Installer & management CLI
└── .env                  # Environment configuration
```
