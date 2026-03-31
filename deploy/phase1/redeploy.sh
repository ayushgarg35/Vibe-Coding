#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Zero-downtime redeploy — pull latest code and restart services.
# Run on the server: bash deploy/phase1/redeploy.sh
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()   { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

APP_DIR="/opt/agentic-pm"
COMPOSE="docker compose -f deploy/phase1/docker-compose.prod.yml --env-file .env.production"
BRANCH=$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD)

cd "$APP_DIR"

log "Pulling latest code from branch: $BRANCH"
git fetch origin
git pull origin "$BRANCH"

log "Building updated images..."
$COMPOSE build --parallel

log "Applying any new DB migrations..."
$COMPOSE exec -T postgres psql -U pmuser -d agenticpm \
    < backend/storage/migrations/001_initial.sql 2>/dev/null || true

log "Rolling restart (backend → worker → frontend)..."
$COMPOSE up -d --no-deps backend
sleep 10

# Health check before rolling forward
until curl -sf http://localhost:8000/health &>/dev/null; do
    sleep 2
done
log "Backend healthy — continuing..."

$COMPOSE up -d --no-deps worker beat
$COMPOSE up -d --no-deps frontend

log "Cleaning up old images..."
docker image prune -f --filter "until=24h"

log "Redeploy complete. Services:"
$COMPOSE ps
