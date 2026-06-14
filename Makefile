# ────────────────────────────────────────────────────────────────────────────
# GnuKontrolR — Local validation targets
#
# Mirrors the CI pipeline so you can check before pushing.
# ────────────────────────────────────────────────────────────────────────────

.PHONY: help check check-all lint-py lint-docker lint-js compose-check build-test

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

check-all: compose-check lint-py lint-docker lint-js build-test ## Run all checks

# ── Docker Compose validation ──────────────────────────────────────────────
compose-check: ## Validate docker-compose.yml syntax & structure
	@echo "→ Validating docker-compose.yml..."
	python3 -c "
import yaml, sys
with open('docker-compose.yml') as f:
    data = yaml.safe_load(f)
services = list(data.get('services', {}).keys())
print(f'  ✓ {len(services)} services defined')
exit_code = 0
for s in services:
    svc = data['services'][s]
    if not svc.get('cap_drop'):
        print(f'  ⚠  {s}: no cap_drop')
    if not svc.get('restart'):
        print(f'  ⚠  {s}: no restart policy')
names = {}
for s, svc in data.get('services', {}).items():
    cname = svc.get('container_name', s)
    if cname in names:
        print(f'  ✗ Duplicate container_name: {cname}')
        exit_code = 1
    names[cname] = s
    if svc.get('privileged'):
        print(f'  ✗ {s} is PRIVILEGED')
        exit_code = 1
sys.exit(exit_code)
	"
	@echo "  ✓ docker-compose.yml is valid"

# ── Python lint ────────────────────────────────────────────────────────────
lint-py: ## Lint Python backend with ruff
	@echo "→ Linting Python backend..."
	@command -v ruff >/dev/null 2>&1 || { echo "  ⚠  ruff not found — install with: pip install ruff"; exit 1; }
	cd backend && ruff check .
	cd backend && ruff format --check .
	@echo "  ✓ Python lint passed"

lint-py-fix: ## Auto-fix Python lint issues
	@command -v ruff >/dev/null 2>&1 || { echo "  ⚠  ruff not found"; exit 1; }
	cd backend && ruff check --fix .
	cd backend && ruff format .

# ── Dockerfile lint ────────────────────────────────────────────────────────
lint-docker: ## Lint Dockerfiles with hadolint (docker run)
	@echo "→ Linting Dockerfiles..."
	@command -v docker >/dev/null 2>&1 || { echo "  ⚠  docker not found"; exit 1; }
	@for df in backend/Dockerfile docker/opendkim/Dockerfile docker/localdns/Dockerfile docker/mediadump/Dockerfile docker/site-template/Dockerfile; do \
		echo "  → $$df"; \
		docker run --rm -i ghcr.io/hadolint/hadolint < "$$df" || true; \
	done
	@echo "  ✓ Dockerfile lint complete"

# ── Frontend lint ──────────────────────────────────────────────────────────
lint-js: ## Lint frontend with ESLint
	@echo "→ Linting frontend..."
	@command -v npx >/dev/null 2>&1 || { echo "  ⚠  node/npx not found"; exit 1; }
	cd frontend && npm ci --silent 2>/dev/null; npx eslint src/ --max-warnings=0
	@echo "  ✓ Frontend lint passed"

# ── Build test ─────────────────────────────────────────────────────────────
build-test: ## Build webpanel Docker image (no push)
	@echo "→ Building webpanel Docker image..."
	docker build -f backend/Dockerfile -t webpanel:ci-test .
	@echo "  ✓ Build successful"

# ── Security scan ──────────────────────────────────────────────────────────
security-scan: ## Run trivy filesystem scan (docker run)
	@echo "→ Scanning for vulnerabilities..."
	@command -v docker >/dev/null 2>&1 || { echo "  ⚠  docker not found"; exit 1; }
	docker run --rm -v .:/workspace aquasec/trivy:latest \
		fs --severity HIGH,CRITICAL --exit-code 0 /workspace
	@echo "  ✓ Security scan complete"

# ── Git hooks setup ────────────────────────────────────────────────────────
install-hooks: ## Install pre-commit hooks
	@echo "→ Installing pre-commit hook..."
	@mkdir -p .git/hooks
	@printf '#!/bin/sh\nmake check-all\n' > .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "  ✓ Pre-commit hook installed (runs 'make check-all' on every commit)"
