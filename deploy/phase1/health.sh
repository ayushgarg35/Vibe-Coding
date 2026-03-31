#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Health check — prints the status of every service.
# Run on the server: bash deploy/phase1/health.sh
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $*"; }
fail() { echo -e "  ${RED}✗${NC} $*"; FAILURES=$((FAILURES+1)); }
warn() { echo -e "  ${YELLOW}~${NC} $*"; }

APP_DIR="/opt/agentic-pm"
COMPOSE="docker compose -f ${APP_DIR}/deploy/phase1/docker-compose.prod.yml --env-file ${APP_DIR}/.env.production"
FAILURES=0

echo -e "\n${BOLD}Agentic PM System — Health Report${NC}"
echo -e "$(date -u +"%Y-%m-%d %H:%M:%S UTC")\n"

# ── Docker services ───────────────────────────────────────────────
echo -e "${BOLD}Docker Services:${NC}"
while IFS= read -r line; do
    name=$(echo "$line" | awk '{print $1}')
    status=$(echo "$line" | awk '{print $4}')
    health=$(echo "$line" | awk '{print $5, $6, $7}')
    if echo "$status" | grep -q "Up"; then
        ok "$name — $status $health"
    else
        fail "$name — $status"
    fi
done < <($COMPOSE ps --format "table {{.Name}}\t{{.Service}}\t{{.Image}}\t{{.Status}}" 2>/dev/null | tail -n +2)

# ── Endpoint health ───────────────────────────────────────────────
echo -e "\n${BOLD}Endpoints:${NC}"

if curl -sf http://localhost:8000/health &>/dev/null; then
    VERSION=$(curl -s http://localhost:8000/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('version','?'))" 2>/dev/null)
    ok "Backend API — http://localhost:8000 (v${VERSION})"
else
    fail "Backend API — http://localhost:8000 (not responding)"
fi

if curl -sf http://localhost:3000 &>/dev/null; then
    ok "Frontend — http://localhost:3000"
else
    fail "Frontend — http://localhost:3000 (not responding)"
fi

if curl -sf http://localhost:6333/healthz &>/dev/null; then
    ok "Qdrant — http://localhost:6333"
else
    warn "Qdrant — http://localhost:6333 (check if needed)"
fi

# ── Database ──────────────────────────────────────────────────────
echo -e "\n${BOLD}Database:${NC}"
if $COMPOSE exec -T postgres pg_isready -U pmuser -d agenticpm &>/dev/null; then
    TABLES=$($COMPOSE exec -T postgres psql -U pmuser -d agenticpm -t \
        -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | tr -d ' ')
    ok "PostgreSQL — connected (${TABLES} tables)"
else
    fail "PostgreSQL — not ready"
fi

# ── Redis ─────────────────────────────────────────────────────────
echo -e "\n${BOLD}Cache:${NC}"
REDIS_PASS=$(grep REDIS_PASSWORD "$APP_DIR/.env.production" | cut -d= -f2)
if $COMPOSE exec -T redis redis-cli -a "$REDIS_PASS" ping &>/dev/null; then
    KEYS=$($COMPOSE exec -T redis redis-cli -a "$REDIS_PASS" dbsize 2>/dev/null | tr -d ' \r')
    ok "Redis — connected (${KEYS} keys)"
else
    fail "Redis — not responding"
fi

# ── Disk & memory ─────────────────────────────────────────────────
echo -e "\n${BOLD}Resources:${NC}"
DISK_USE=$(df -h / | awk 'NR==2{print $5}' | tr -d '%')
MEM_USE=$(free | awk '/Mem:/{printf "%.0f", $3/$2*100}')

if [[ $DISK_USE -lt 80 ]]; then
    ok "Disk — ${DISK_USE}% used"
else
    fail "Disk — ${DISK_USE}% used (WARNING: above 80%)"
fi

if [[ $MEM_USE -lt 85 ]]; then
    ok "Memory — ${MEM_USE}% used"
else
    warn "Memory — ${MEM_USE}% used (consider upgrading instance)"
fi

# ── Nginx reverse proxy ───────────────────────────────────────────
echo -e "\n${BOLD}Reverse Proxy:${NC}"
if systemctl is-active --quiet nginx; then
    ok "Nginx — running"
elif systemctl is-active --quiet caddy; then
    ok "Caddy — running"
else
    fail "Nginx/Caddy — not running (run: systemctl start nginx)"
fi

# ── Summary ───────────────────────────────────────────────────────
echo ""
if [[ $FAILURES -eq 0 ]]; then
    echo -e "${GREEN}${BOLD}All checks passed.${NC}"
else
    echo -e "${RED}${BOLD}${FAILURES} check(s) failed — review output above.${NC}"
    exit 1
fi
