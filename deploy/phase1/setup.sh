#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Agentic PM System — Phase 1 Server Setup
# Run once on a fresh Ubuntu 22.04 server as root or sudo user.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/ayushgarg35/Vibe-Coding/claude/agentic-pm-system-boXvy/deploy/phase1/setup.sh | bash
#   OR: scp setup.sh ubuntu@<server>:~ && ssh ubuntu@<server> 'bash setup.sh'
#
# What this does:
#   1. Hardens the server (firewall, fail2ban, unattended upgrades)
#   2. Installs Docker, Docker Compose
#   3. Installs Caddy (reverse proxy + auto SSL)
#   4. Clones the repo
#   5. Generates strong secrets
#   6. Prompts for API keys
#   7. Starts all services
#   8. Runs DB migrations
#   9. Verifies health
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()    { echo -e "${GREEN}[+]${NC} $*"; }
warn()   { echo -e "${YELLOW}[!]${NC} $*"; }
error()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }
header() { echo -e "\n${BOLD}${BLUE}━━━ $* ━━━${NC}\n"; }

# ── Preflight ─────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "Run as root: sudo bash setup.sh"
[[ $(lsb_release -rs 2>/dev/null) != "22.04" ]] && warn "Tested on Ubuntu 22.04 — proceed with caution on other distros"

header "Agentic PM System — Phase 1 Setup"
echo "This script will set up your server and start all services."
echo "Estimated time: 10–15 minutes."
read -rp "Continue? [y/N] " confirm
[[ $confirm =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# ── Collect config up front ───────────────────────────────────────
header "Configuration"
read -rp "Domain name (e.g. pm.mycompany.com): " DOMAIN
read -rp "Git branch to deploy [claude/agentic-pm-system-boXvy]: " GIT_BRANCH
GIT_BRANCH=${GIT_BRANCH:-claude/agentic-pm-system-boXvy}
read -rp "Anthropic API key (required): " ANTHROPIC_KEY
read -rp "OpenAI API key (optional, press enter to skip): " OPENAI_KEY
read -rp "Clerk Secret Key: " CLERK_SECRET
read -rp "Clerk Publishable Key: " CLERK_PUB
read -rp "LangSmith API key (optional): " LANGSMITH_KEY

# ── Generate secrets ──────────────────────────────────────────────
log "Generating secrets..."
APP_SECRET=$(openssl rand -hex 32)
PG_PASSWORD=$(openssl rand -hex 24)
REDIS_PASSWORD=$(openssl rand -hex 24)
S3_ACCESS=$(openssl rand -hex 16)
S3_SECRET=$(openssl rand -hex 32)
LITELLM_KEY=$(openssl rand -hex 32)

# ── System hardening ──────────────────────────────────────────────
header "System Hardening"

log "Updating packages..."
apt-get update -qq && apt-get upgrade -y -qq

log "Installing base tools..."
apt-get install -y -qq \
    curl wget git unzip htop ufw fail2ban \
    unattended-upgrades apt-transport-https \
    ca-certificates gnupg lsb-release

log "Configuring firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
log "Firewall: SSH, HTTP, HTTPS allowed"

log "Enabling automatic security updates..."
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF

log "Configuring fail2ban..."
systemctl enable fail2ban --quiet
systemctl start fail2ban

# Swap (important for t3.xlarge to handle memory spikes)
if [[ ! -f /swapfile ]]; then
    log "Creating 4GB swap..."
    fallocate -l 4G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile -q
    swapon /swapfile
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ── Docker ────────────────────────────────────────────────────────
header "Installing Docker"

if ! command -v docker &>/dev/null; then
    log "Installing Docker Engine..."
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker ubuntu 2>/dev/null || true
    systemctl enable docker --quiet
    systemctl start docker
    log "Docker installed: $(docker --version)"
else
    log "Docker already installed: $(docker --version)"
fi

# ── Caddy ─────────────────────────────────────────────────────────
header "Installing Caddy"

if ! command -v caddy &>/dev/null; then
    log "Installing Caddy..."
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq
    apt-get install -y -qq caddy
    log "Caddy installed: $(caddy version)"
else
    log "Caddy already installed: $(caddy version)"
fi

# ── Clone repo ────────────────────────────────────────────────────
header "Cloning Repository"

APP_DIR="/opt/agentic-pm"
if [[ -d "$APP_DIR" ]]; then
    log "Updating existing repo..."
    cd "$APP_DIR"
    git fetch origin
    git checkout "$GIT_BRANCH"
    git pull origin "$GIT_BRANCH"
else
    log "Cloning repo..."
    git clone -b "$GIT_BRANCH" \
        https://github.com/ayushgarg35/Vibe-Coding.git "$APP_DIR"
    cd "$APP_DIR"
fi

# ── Write .env.production ─────────────────────────────────────────
header "Writing Environment Config"

log "Writing .env.production..."
cat > "$APP_DIR/.env.production" <<EOF
# Generated by setup.sh — $(date -u +"%Y-%m-%dT%H:%M:%SZ")
APP_ENV=production
APP_SECRET_KEY=${APP_SECRET}
APP_BASE_URL=https://${DOMAIN}
CORS_ORIGINS=["https://${DOMAIN}"]

POSTGRES_USER=pmuser
POSTGRES_PASSWORD=${PG_PASSWORD}
POSTGRES_DB=agenticpm
DATABASE_URL=postgresql+asyncpg://pmuser:${PG_PASSWORD}@postgres:5432/agenticpm

REDIS_PASSWORD=${REDIS_PASSWORD}
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0

QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=

ANTHROPIC_API_KEY=${ANTHROPIC_KEY}
OPENAI_API_KEY=${OPENAI_KEY}
GOOGLE_API_KEY=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
LITELLM_MASTER_KEY=${LITELLM_KEY}

CLERK_SECRET_KEY=${CLERK_SECRET}
CLERK_WEBHOOK_SECRET=
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=${CLERK_PUB}

S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY=${S3_ACCESS}
S3_SECRET_KEY=${S3_SECRET}
S3_BUCKET_NAME=agentic-pm
S3_REGION=us-east-1

LANGSMITH_API_KEY=${LANGSMITH_KEY}
LANGSMITH_PROJECT=agentic-pm-prod
LANGSMITH_TRACING=${LANGSMITH_KEY:+true}
LANGSMITH_TRACING=${LANGSMITH_KEY:-false}

DEFAULT_DATA_REGION=US
PII_DETECTION_ENABLED=true
AUDIT_LOG_ENABLED=true

NEXT_PUBLIC_API_URL=https://${DOMAIN}
NEXT_PUBLIC_WS_URL=wss://${DOMAIN}

REGISTRY=ghcr.io/ayushgarg35
IMAGE_TAG=latest
EOF
chmod 600 "$APP_DIR/.env.production"
log ".env.production written (permissions: 600)"

# ── Write Caddyfile ───────────────────────────────────────────────
header "Configuring Caddy"

cat > /etc/caddy/Caddyfile <<EOF
${DOMAIN} {
    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        -Server
    }

    # WebSocket — collab server (must come before general /api proxy)
    @websocket {
        path /api/v1/collab/*
        header Connection *Upgrade*
        header Upgrade websocket
    }
    reverse_proxy @websocket localhost:8000 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }

    # SSE — agent streaming (disable buffering)
    @sse {
        path /api/v1/sessions/*/stream
    }
    reverse_proxy @sse localhost:8000 {
        flush_interval -1
        header_up Host {host}
        header_up X-Real-IP {remote_host}
    }

    # API
    reverse_proxy /api/* localhost:8000 {
        header_up Host {host}
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
        lb_policy round_robin
        health_uri /health
        health_interval 30s
    }

    # Metrics (internal only — restrict to trusted IPs in production)
    reverse_proxy /metrics localhost:8000

    # Frontend
    reverse_proxy * localhost:3000 {
        header_up Host {host}
    }

    # Access log
    log {
        output file /var/log/caddy/access.log {
            roll_size 50mb
            roll_keep 5
        }
    }
}
EOF

mkdir -p /var/log/caddy
systemctl reload caddy
log "Caddyfile written and Caddy reloaded"

# ── Build and start services ──────────────────────────────────────
header "Building and Starting Services"

cd "$APP_DIR"

log "Building Docker images (this takes 5–10 minutes)..."
docker compose \
    -f deploy/phase1/docker-compose.prod.yml \
    --env-file .env.production \
    build --no-cache --parallel

log "Starting services..."
docker compose \
    -f deploy/phase1/docker-compose.prod.yml \
    --env-file .env.production \
    up -d

log "Waiting for PostgreSQL to be ready..."
until docker compose \
    -f deploy/phase1/docker-compose.prod.yml \
    --env-file .env.production \
    exec -T postgres pg_isready -U pmuser -d agenticpm &>/dev/null; do
    sleep 2
done
log "PostgreSQL is ready"

# ── Run migrations ────────────────────────────────────────────────
header "Running Database Migrations"

log "Applying schema..."
docker compose \
    -f deploy/phase1/docker-compose.prod.yml \
    --env-file .env.production \
    exec -T postgres psql -U pmuser -d agenticpm \
    < "$APP_DIR/backend/storage/migrations/001_initial.sql"
log "Schema applied"

# Create MinIO bucket
log "Creating MinIO bucket..."
sleep 5  # let MinIO fully start
docker compose \
    -f deploy/phase1/docker-compose.prod.yml \
    --env-file .env.production \
    exec -T minio mc alias set local http://localhost:9000 \
    "$(grep S3_ACCESS_KEY "$APP_DIR/.env.production" | cut -d= -f2)" \
    "$(grep S3_SECRET_KEY "$APP_DIR/.env.production" | cut -d= -f2)" 2>/dev/null || true
docker compose \
    -f deploy/phase1/docker-compose.prod.yml \
    --env-file .env.production \
    exec -T minio mc mb local/agentic-pm 2>/dev/null || true

# ── Health check ─────────────────────────────────────────────────
header "Health Verification"

log "Waiting for backend to be healthy..."
RETRIES=0
until curl -sf "http://localhost:8000/health" &>/dev/null; do
    RETRIES=$((RETRIES+1))
    [[ $RETRIES -gt 30 ]] && error "Backend failed to start. Check: docker compose logs backend"
    sleep 3
done

HEALTH=$(curl -s http://localhost:8000/health)
log "Backend health: $HEALTH"

# ── Install systemd service for auto-start on reboot ─────────────
header "Configuring Auto-Start"

cat > /etc/systemd/system/agentic-pm.service <<EOF
[Unit]
Description=Agentic PM System
Requires=docker.service
After=docker.service network.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/docker compose -f deploy/phase1/docker-compose.prod.yml --env-file .env.production up -d
ExecStop=/usr/bin/docker compose -f deploy/phase1/docker-compose.prod.yml --env-file .env.production down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable agentic-pm.service
log "Auto-start on reboot: enabled"

# ── Summary ───────────────────────────────────────────────────────
header "Setup Complete"

echo ""
echo -e "${GREEN}${BOLD}✓ Agentic PM System is live!${NC}"
echo ""
echo -e "  ${BOLD}URL:${NC}           https://${DOMAIN}"
echo -e "  ${BOLD}API docs:${NC}      https://${DOMAIN}/api/docs"
echo -e "  ${BOLD}App dir:${NC}       ${APP_DIR}"
echo -e "  ${BOLD}Env file:${NC}      ${APP_DIR}/.env.production"
echo ""
echo -e "${BOLD}Useful commands:${NC}"
echo "  View all logs:    cd ${APP_DIR} && docker compose -f deploy/phase1/docker-compose.prod.yml logs -f"
echo "  View backend:     docker compose -f deploy/phase1/docker-compose.prod.yml logs -f backend"
echo "  Restart all:      systemctl restart agentic-pm"
echo "  Pull + redeploy:  cd ${APP_DIR} && bash deploy/phase1/redeploy.sh"
echo "  Health check:     bash deploy/phase1/health.sh"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Point DNS: ${DOMAIN} → $(curl -4s ifconfig.me 2>/dev/null || echo '<server-IP>')"
echo "  2. Add Clerk webhook URL in Clerk dashboard: https://${DOMAIN}/api/v1/webhooks/clerk"
echo "  3. Add LangSmith project at https://smith.langchain.com"
echo ""
