#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Hetzner Auto-Provision — creates server + deploys Agentic PM
#
# Prerequisites (on your local machine):
#   brew install hcloud     # macOS
#   apt install hcloud-cli  # Ubuntu/Debian
#   hcloud context create agentic-pm   # then paste your API token
#
# Usage:
#   export HCLOUD_TOKEN=your_hetzner_api_token
#   export ANTHROPIC_API_KEY=sk-ant-...
#   bash hetzner-provision.sh
#
# What it does:
#   1. Creates a CX32 server (4 vCPU, 8 GB RAM) in Hetzner Falkenstein
#   2. Waits for SSH to be ready
#   3. Uploads and runs setup-ip.sh non-interactively
#   4. Prints the app URL
#
# Cost: ~€12/month (CX32) — delete with: hcloud server delete agentic-pm-1
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()    { echo -e "${GREEN}[+]${NC} $*"; }
warn()   { echo -e "${YELLOW}[!]${NC} $*"; }
error()  { echo -e "${RED}[✗]${NC} $*"; exit 1; }
header() { echo -e "\n${BOLD}${BLUE}━━━ $* ━━━${NC}\n"; }

# ── Validate prerequisites ────────────────────────────────────────
header "Pre-flight Checks"

command -v hcloud &>/dev/null || error "hcloud CLI not found.
Install it:
  macOS:  brew install hcloud
  Linux:  https://github.com/hetznercloud/cli/releases"

command -v ssh &>/dev/null || error "ssh not found"

[[ -z "${HCLOUD_TOKEN:-}" ]] && error "Set HCLOUD_TOKEN:
  export HCLOUD_TOKEN=your_hetzner_api_token
  Get one at: https://console.hetzner.cloud → Project → API Tokens"

[[ -z "${ANTHROPIC_API_KEY:-}" ]] && error "Set ANTHROPIC_API_KEY:
  export ANTHROPIC_API_KEY=sk-ant-..."

log "hcloud CLI found: $(hcloud version)"
log "HCLOUD_TOKEN: set"
log "ANTHROPIC_API_KEY: set"

# ── Configuration ─────────────────────────────────────────────────
SERVER_NAME="${SERVER_NAME:-agentic-pm-1}"
SERVER_TYPE="${SERVER_TYPE:-cx32}"          # 4 vCPU, 8 GB — ~€12/mo
LOCATION="${LOCATION:-fsn1}"               # Falkenstein, Germany
IMAGE="${IMAGE:-ubuntu-22.04}"
SSH_KEY_NAME="${SSH_KEY_NAME:-}"           # optional: name of existing Hetzner SSH key

# Optional API keys (can be set as env vars)
OPENAI_KEY="${OPENAI_API_KEY:-}"
CLERK_SECRET="${CLERK_SECRET_KEY:-}"
CLERK_PUB="${NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY:-}"
LANGSMITH_KEY="${LANGSMITH_API_KEY:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

header "Hetzner Server Provisioning"
echo -e "  Server:   ${BOLD}${SERVER_NAME}${NC}"
echo -e "  Type:     ${BOLD}${SERVER_TYPE}${NC} (4 vCPU, 8 GB RAM)"
echo -e "  Location: ${BOLD}${LOCATION}${NC}"
echo -e "  Image:    ${BOLD}${IMAGE}${NC}"
echo ""

# ── Check if server already exists ───────────────────────────────
if hcloud server describe "$SERVER_NAME" &>/dev/null; then
    EXISTING_IP=$(hcloud server describe "$SERVER_NAME" -o json | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d['public_net']['ipv4']['ip'])
")
    warn "Server '${SERVER_NAME}' already exists at ${EXISTING_IP}"
    read -rp "Use existing server? [Y/n] " use_existing
    if [[ $use_existing =~ ^[Nn]$ ]]; then
        error "Aborting. Delete the server first: hcloud server delete ${SERVER_NAME}"
    fi
    SERVER_IP="$EXISTING_IP"
    log "Using existing server: ${SERVER_IP}"
else
    # ── Generate SSH key if needed ────────────────────────────────
    SSH_KEY_FILE="${HOME}/.ssh/agentic-pm-hetzner"
    if [[ ! -f "${SSH_KEY_FILE}" ]]; then
        log "Generating SSH key: ${SSH_KEY_FILE}"
        ssh-keygen -t ed25519 -f "${SSH_KEY_FILE}" -N "" -C "agentic-pm-hetzner"
    fi

    # Upload SSH public key to Hetzner if not present
    HCLOUD_KEY_NAME="agentic-pm-deploy"
    if ! hcloud ssh-key describe "$HCLOUD_KEY_NAME" &>/dev/null; then
        log "Uploading SSH public key to Hetzner..."
        hcloud ssh-key create --name "$HCLOUD_KEY_NAME" \
            --public-key-from-file "${SSH_KEY_FILE}.pub"
    fi

    # Determine SSH keys to use
    SSH_KEY_ARG="--ssh-key $HCLOUD_KEY_NAME"
    if [[ -n "$SSH_KEY_NAME" ]]; then
        SSH_KEY_ARG="--ssh-key $SSH_KEY_NAME --ssh-key $HCLOUD_KEY_NAME"
    fi

    # ── Create the server ─────────────────────────────────────────
    log "Creating server '${SERVER_NAME}'..."
    # shellcheck disable=SC2086
    hcloud server create \
        --name "$SERVER_NAME" \
        --type "$SERVER_TYPE" \
        --image "$IMAGE" \
        --location "$LOCATION" \
        $SSH_KEY_ARG \
        --label "app=agentic-pm" \
        --label "managed-by=hetzner-provision.sh"

    SERVER_IP=$(hcloud server describe "$SERVER_NAME" -o json | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d['public_net']['ipv4']['ip'])
")

    log "Server created: ${SERVER_IP}"

    # ── Wait for SSH ──────────────────────────────────────────────
    log "Waiting for SSH to be ready..."
    RETRIES=0
    until ssh -o StrictHostKeyChecking=no \
               -o ConnectTimeout=5 \
               -o BatchMode=yes \
               -i "${SSH_KEY_FILE}" \
               root@"${SERVER_IP}" "echo ok" &>/dev/null; do
        sleep 5
        RETRIES=$((RETRIES+1))
        [[ $RETRIES -gt 36 ]] && error "SSH not ready after 3 minutes"
        echo -n "."
    done
    echo ""
    log "SSH ready"
fi

# ── Write non-interactive setup script ───────────────────────────
header "Preparing Setup"

# Create a wrapper that feeds answers non-interactively
REMOTE_SETUP=$(mktemp /tmp/agentic-pm-setup-XXXX.sh)
cat > "$REMOTE_SETUP" <<WRAPPER
#!/usr/bin/env bash
set -euo pipefail

# Install expect for non-interactive input handling
apt-get install -y -qq expect 2>/dev/null

# Download the setup-ip.sh from the repo (or upload directly)
SETUP_SCRIPT=\$(mktemp /tmp/setup-ip-XXXX.sh)

cat > "\$SETUP_SCRIPT" << 'HEREDOC'
$(cat "${SCRIPT_DIR}/setup-ip.sh")
HEREDOC

chmod +x "\$SETUP_SCRIPT"

# Run non-interactively by pre-answering prompts
export SERVER_IP_OVERRIDE="${SERVER_IP}"
export ANTHROPIC_API_KEY_OVERRIDE="${ANTHROPIC_KEY}"
export OPENAI_API_KEY_OVERRIDE="${OPENAI_KEY}"
export CLERK_SECRET_KEY_OVERRIDE="${CLERK_SECRET}"
export CLERK_PUB_KEY_OVERRIDE="${CLERK_PUB}"
export LANGSMITH_KEY_OVERRIDE="${LANGSMITH_KEY}"

# Patch setup-ip.sh to read from env vars when set
sed -i 's/read -rp "Use this IP.*confirm/: # skipped by automation; confirm=y/' "\$SETUP_SCRIPT"
sed -i 's/if \[\[ \$confirm =~ .*then/if false; then # skipped/' "\$SETUP_SCRIPT"
sed -i 's/read -rp "Enter IP address.*SERVER_IP/SERVER_IP="\${SERVER_IP_OVERRIDE}"/' "\$SETUP_SCRIPT"
sed -i 's|read -rsp "  Anthropic API key.*ANTHROPIC_KEY.*echo|ANTHROPIC_KEY="\${ANTHROPIC_API_KEY_OVERRIDE}"|' "\$SETUP_SCRIPT"
sed -i 's|read -rsp "  OpenAI API key.*OPENAI_KEY.*echo|OPENAI_KEY="\${OPENAI_API_KEY_OVERRIDE:-}"|' "\$SETUP_SCRIPT"
sed -i 's|read -rsp "  Clerk Secret Key.*CLERK_SECRET.*echo|CLERK_SECRET="\${CLERK_SECRET_KEY_OVERRIDE:-}"|' "\$SETUP_SCRIPT"
sed -i 's|read -rsp "  Clerk Publishable Key.*CLERK_PUB.*echo|CLERK_PUB="\${CLERK_PUB_KEY_OVERRIDE:-}"|' "\$SETUP_SCRIPT"
sed -i 's|read -rsp "  LangSmith API key.*LANGSMITH_KEY.*echo|LANGSMITH_KEY="\${LANGSMITH_KEY_OVERRIDE:-}"|' "\$SETUP_SCRIPT"

bash "\$SETUP_SCRIPT"
WRAPPER

chmod +x "$REMOTE_SETUP"

# ── Copy setup files to server ────────────────────────────────────
header "Uploading Setup Files"

SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=30 -i ${SSH_KEY_FILE}"

log "Uploading setup script..."
scp $SSH_OPTS "$REMOTE_SETUP" root@"${SERVER_IP}":/tmp/run-setup.sh

rm -f "$REMOTE_SETUP"

# ── Execute setup ─────────────────────────────────────────────────
header "Running Setup on Server (15–25 minutes)"
echo -e "  ${YELLOW}Watch the logs stream below. Do not close this terminal.${NC}"
echo ""

# shellcheck disable=SC2086
ssh $SSH_OPTS root@"${SERVER_IP}" "bash /tmp/run-setup.sh 2>&1" | tee /tmp/agentic-pm-deploy.log

# ── Verify deployment ─────────────────────────────────────────────
header "Verifying Deployment"

log "Checking backend health..."
RETRIES=0
until curl -sf "http://${SERVER_IP}/health" &>/dev/null; do
    sleep 5
    RETRIES=$((RETRIES+1))
    [[ $RETRIES -gt 24 ]] && {
        warn "Health check timed out. The app may still be starting."
        warn "Check manually: curl http://${SERVER_IP}/health"
        break
    }
    echo -n "."
done
echo ""

HEALTH=$(curl -s "http://${SERVER_IP}/health" 2>/dev/null || echo '{"status":"starting"}')
log "Health response: ${HEALTH}"

# ── Save connection info ──────────────────────────────────────────
INFO_FILE="${SCRIPT_DIR}/server-info.txt"
cat > "$INFO_FILE" <<EOF
# Agentic PM — Server Info
# Created: $(date -u +"%Y-%m-%dT%H:%M:%SZ")

SERVER_NAME=${SERVER_NAME}
SERVER_IP=${SERVER_IP}
SERVER_TYPE=${SERVER_TYPE}
LOCATION=${LOCATION}

SSH_KEY=${SSH_KEY_FILE}

# App endpoints
APP_URL=http://${SERVER_IP}
API_URL=http://${SERVER_IP}/api
HEALTH_URL=http://${SERVER_IP}/health
API_DOCS_URL=http://${SERVER_IP}/api/docs

# SSH access
SSH_CMD=ssh -i ${SSH_KEY_FILE} root@${SERVER_IP}

# Useful commands (run on server)
LOGS=cd /opt/agentic-pm && docker compose -f deploy/phase1/docker-compose.prod.yml logs -f
HEALTH=bash /opt/agentic-pm/deploy/phase1/health.sh
REDEPLOY=bash /opt/agentic-pm/deploy/phase1/redeploy.sh

# Delete server (irreversible)
DELETE=hcloud server delete ${SERVER_NAME}
EOF

chmod 600 "$INFO_FILE"

# ── Done ──────────────────────────────────────────────────────────
header "Done"

echo ""
echo -e "${GREEN}${BOLD}✓ Agentic PM is live on Hetzner!${NC}"
echo ""
echo -e "  ${BOLD}App URL:${NC}      http://${SERVER_IP}"
echo -e "  ${BOLD}API docs:${NC}     http://${SERVER_IP}/api/docs"
echo -e "  ${BOLD}Health:${NC}       http://${SERVER_IP}/health"
echo ""
echo -e "  ${BOLD}SSH access:${NC}"
echo "    ssh -i ${SSH_KEY_FILE} root@${SERVER_IP}"
echo ""
echo -e "  ${BOLD}Server info saved to:${NC} ${INFO_FILE}"
echo ""
echo -e "  ${BOLD}Useful commands (on server):${NC}"
echo "    Logs:     cd /opt/agentic-pm && docker compose -f deploy/phase1/docker-compose.prod.yml logs -f"
echo "    Health:   bash /opt/agentic-pm/deploy/phase1/health.sh"
echo "    Redeploy: bash /opt/agentic-pm/deploy/phase1/redeploy.sh"
echo ""
echo -e "  ${YELLOW}${BOLD}Cost:${NC} ~€12/month. Delete when done:"
echo "    hcloud server delete ${SERVER_NAME}"
echo ""
