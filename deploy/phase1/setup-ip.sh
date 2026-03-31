#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Agentic PM System — IP-only setup (no domain required)
# HTTP on port 80, no SSL. For internal/team use only.
#
# Usage (as root on fresh Ubuntu 22.04):
#   bash setup-ip.sh
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()    { echo -e "${GREEN}[+]${NC} $*"; }
warn()   { echo -e "${YELLOW}[!]${NC} $*"; }
error()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }
header() { echo -e "\n${BOLD}${BLUE}━━━ $* ━━━${NC}\n"; }

[[ $EUID -ne 0 ]] && error "Run as root: sudo bash setup-ip.sh"

# ── Detect server IP ──────────────────────────────────────────────
SERVER_IP=$(curl -4s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')

header "Agentic PM System — IP-only Setup"
echo -e "  Detected IP: ${BOLD}${SERVER_IP}${NC}"
echo ""
read -rp "Use this IP? [Y/n] " confirm
if [[ $confirm =~ ^[Nn]$ ]]; then
    read -rp "Enter IP address to use: " SERVER_IP
fi

# ── Collect API keys ──────────────────────────────────────────────
header "API Keys"
echo "Required:"
read -rsp "  Anthropic API key: " ANTHROPIC_KEY; echo
echo ""
echo "Optional (press Enter to skip):"
read -rsp "  OpenAI API key: " OPENAI_KEY; echo
read -rsp "  Clerk Secret Key: " CLERK_SECRET; echo
read -rsp "  Clerk Publishable Key: " CLERK_PUB; echo
read -rsp "  LangSmith API key: " LANGSMITH_KEY; echo
echo ""

[[ -z "$ANTHROPIC_KEY" ]] && error "Anthropic API key is required"

# ── Generate secrets ──────────────────────────────────────────────
APP_SECRET=$(openssl rand -hex 32)
PG_PASSWORD=$(openssl rand -hex 24)
REDIS_PASSWORD=$(openssl rand -hex 24)
S3_ACCESS=$(openssl rand -hex 16)
S3_SECRET=$(openssl rand -hex 32)
LITELLM_KEY=$(openssl rand -hex 32)

# ── System hardening ──────────────────────────────────────────────
header "System Setup"

log "Updating packages..."
apt-get update -qq && apt-get upgrade -y -qq 2>/dev/null

log "Installing tools..."
apt-get install -y -qq \
    curl wget git unzip htop ufw fail2ban \
    unattended-upgrades apt-transport-https \
    ca-certificates gnupg lsb-release 2>/dev/null

log "Configuring firewall..."
ufw --force reset -q
ufw default deny incoming -q
ufw default allow outgoing -q
ufw allow ssh -q
ufw allow 80/tcp -q     # HTTP (app)
ufw allow 9001/tcp -q   # MinIO console (optional, can remove)
ufw --force enable -q
log "Firewall active: SSH + port 80 open"

log "Enabling fail2ban..."
systemctl enable fail2ban --quiet && systemctl start fail2ban

# Swap
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
    log "Installing Docker..."
    curl -fsSL https://get.docker.com | sh -s -- -q
    usermod -aG docker ubuntu 2>/dev/null || true
    systemctl enable docker --quiet
    log "Docker: $(docker --version)"
else
    log "Docker already present: $(docker --version)"
fi

# Install docker compose plugin if missing
if ! docker compose version &>/dev/null 2>&1; then
    log "Installing Docker Compose plugin..."
    apt-get install -y -qq docker-compose-plugin
fi

# ── Clone repo ────────────────────────────────────────────────────
header "Cloning Repository"
APP_DIR="/opt/agentic-pm"

if [[ -d "$APP_DIR" ]]; then
    log "Updating existing repo..."
    git -C "$APP_DIR" fetch origin
    git -C "$APP_DIR" checkout claude/agentic-pm-system-boXvy
    git -C "$APP_DIR" pull origin claude/agentic-pm-system-boXvy
else
    log "Cloning..."
    git clone -b claude/agentic-pm-system-boXvy \
        https://github.com/ayushgarg35/Vibe-Coding.git "$APP_DIR"
fi

# ── Write .env.production ─────────────────────────────────────────
header "Writing Config"

cat > "$APP_DIR/.env.production" <<EOF
# Generated $(date -u +"%Y-%m-%dT%H:%M:%SZ") — server: ${SERVER_IP}
APP_ENV=production
APP_SECRET_KEY=${APP_SECRET}
APP_BASE_URL=http://${SERVER_IP}
CORS_ORIGINS=["http://${SERVER_IP}","http://localhost:3000"]

POSTGRES_USER=pmuser
POSTGRES_PASSWORD=${PG_PASSWORD}
POSTGRES_DB=agenticpm
DATABASE_URL=postgresql+asyncpg://pmuser:${PG_PASSWORD}@postgres:5432/agenticpm

REDIS_PASSWORD=${REDIS_PASSWORD}
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0

QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=

ANTHROPIC_API_KEY=${ANTHROPIC_KEY}
OPENAI_API_KEY=${OPENAI_KEY:-}
GOOGLE_API_KEY=
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
LITELLM_MASTER_KEY=${LITELLM_KEY}

CLERK_SECRET_KEY=${CLERK_SECRET:-}
CLERK_WEBHOOK_SECRET=
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=${CLERK_PUB:-}

S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY=${S3_ACCESS}
S3_SECRET_KEY=${S3_SECRET}
S3_BUCKET_NAME=agentic-pm
S3_REGION=us-east-1

LANGSMITH_API_KEY=${LANGSMITH_KEY:-}
LANGSMITH_PROJECT=agentic-pm-prod
LANGSMITH_TRACING=false

DEFAULT_DATA_REGION=US
PII_DETECTION_ENABLED=true
AUDIT_LOG_ENABLED=true

NEXT_PUBLIC_API_URL=http://${SERVER_IP}
NEXT_PUBLIC_WS_URL=ws://${SERVER_IP}

REGISTRY=ghcr.io/ayushgarg35
IMAGE_TAG=latest
EOF
chmod 600 "$APP_DIR/.env.production"
log ".env.production written"

# ── Write nginx config (lightweight, no Caddy needed for HTTP) ────
header "Configuring Nginx Reverse Proxy"

apt-get install -y -qq nginx

cat > /etc/nginx/sites-available/agentic-pm <<'NGINX'
upstream backend {
    server 127.0.0.1:8000;
    keepalive 32;
}
upstream frontend {
    server 127.0.0.1:3000;
    keepalive 16;
}

server {
    listen 80;
    server_name _;

    client_max_body_size 50M;
    proxy_read_timeout 300s;
    proxy_connect_timeout 10s;

    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";

    # SSE — disable buffering for agent streaming
    location ~ ^/api/v1/sessions/.*/stream {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        chunked_transfer_encoding on;
    }

    # WebSocket — Yjs collab
    location /api/v1/collab/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 3600s;
    }

    # API
    location /api/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health (direct, no auth)
    location /health {
        proxy_pass http://backend/health;
    }

    # Frontend
    location / {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Upgrade $http_upgrade;
    }

    access_log /var/log/nginx/agentic-pm.access.log;
    error_log  /var/log/nginx/agentic-pm.error.log;
}
NGINX

ln -sf /etc/nginx/sites-available/agentic-pm /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx && systemctl enable nginx
log "Nginx configured"

# ── Build and start ───────────────────────────────────────────────
header "Building Docker Images"
cd "$APP_DIR"

log "Building backend image (5–8 minutes)..."
docker compose \
    -f deploy/phase1/docker-compose.prod.yml \
    --env-file .env.production \
    build --no-cache backend worker 2>&1 | grep -E "^(Step|#|ERROR|Successfully)" || true

log "Building frontend image (3–5 minutes)..."
docker compose \
    -f deploy/phase1/docker-compose.prod.yml \
    --env-file .env.production \
    build --no-cache frontend 2>&1 | grep -E "^(Step|#|ERROR|Successfully)" || true

header "Starting Services"
docker compose \
    -f deploy/phase1/docker-compose.prod.yml \
    --env-file .env.production \
    up -d

log "Waiting for PostgreSQL..."
RETRIES=0
until docker compose \
    -f deploy/phase1/docker-compose.prod.yml \
    --env-file .env.production \
    exec -T postgres pg_isready -U pmuser -d agenticpm &>/dev/null; do
    sleep 2
    RETRIES=$((RETRIES+1))
    [[ $RETRIES -gt 30 ]] && error "Postgres failed to start"
done
log "PostgreSQL ready"

# ── Migrations ────────────────────────────────────────────────────
header "Running Migrations"

docker compose \
    -f deploy/phase1/docker-compose.prod.yml \
    --env-file .env.production \
    exec -T postgres psql -U pmuser -d agenticpm \
    < "$APP_DIR/backend/storage/migrations/001_initial.sql" && log "Schema applied"

# MinIO bucket
log "Creating MinIO bucket..."
sleep 5
docker compose \
    -f deploy/phase1/docker-compose.prod.yml \
    --env-file .env.production \
    exec -T minio sh -c "
        mc alias set local http://localhost:9000 '${S3_ACCESS}' '${S3_SECRET}' --quiet 2>/dev/null
        mc mb local/agentic-pm --quiet 2>/dev/null || true
    " 2>/dev/null || warn "MinIO bucket setup skipped (will retry on first upload)"

# ── Health check ─────────────────────────────────────────────────
header "Verifying Health"

log "Waiting for backend..."
RETRIES=0
until curl -sf "http://localhost:8000/health" &>/dev/null; do
    sleep 3
    RETRIES=$((RETRIES+1))
    [[ $RETRIES -gt 40 ]] && {
        error "Backend not healthy. Check logs: docker compose -f ${APP_DIR}/deploy/phase1/docker-compose.prod.yml logs backend"
    }
done
log "Backend healthy: $(curl -s http://localhost:8000/health)"

# ── Systemd service ───────────────────────────────────────────────
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
systemctl enable agentic-pm.service --quiet

# ── Setup nightly backup ──────────────────────────────────────────
echo "0 2 * * * root bash ${APP_DIR}/deploy/phase1/backup.sh >> /var/log/agentic-pm-backup.log 2>&1" \
    > /etc/cron.d/agentic-pm-backup

# ── Done ──────────────────────────────────────────────────────────
header "Done"

echo ""
echo -e "${GREEN}${BOLD}✓ Agentic PM System is live!${NC}"
echo ""
echo -e "  ${BOLD}App URL:${NC}      http://${SERVER_IP}"
echo -e "  ${BOLD}API docs:${NC}     http://${SERVER_IP}/api/docs"
echo -e "  ${BOLD}API health:${NC}   http://${SERVER_IP}/health"
echo ""
echo -e "${BOLD}Saved secrets (keep safe):${NC}"
echo -e "  Config file:  ${APP_DIR}/.env.production"
echo ""
echo -e "${BOLD}Useful commands:${NC}"
echo "  Logs:      cd ${APP_DIR} && docker compose -f deploy/phase1/docker-compose.prod.yml logs -f"
echo "  Health:    bash ${APP_DIR}/deploy/phase1/health.sh"
echo "  Redeploy:  bash ${APP_DIR}/deploy/phase1/redeploy.sh"
echo "  Restart:   systemctl restart agentic-pm"
echo ""
