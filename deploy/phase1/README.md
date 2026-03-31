# Phase 1 Deployment — Single Server

Production deployment on a single Ubuntu 22.04 server using Docker Compose + Caddy.

## Prerequisites

- Ubuntu 22.04 VPS or EC2 (recommended: t3.xlarge — 4 vCPU, 16GB RAM)
- Domain name pointed at your server IP
- API keys: Anthropic (required), OpenAI (optional), Clerk, LangSmith (optional)

## One-Command Deploy

SSH into your server as root, then:

```bash
curl -fsSL https://raw.githubusercontent.com/ayushgarg35/Vibe-Coding/claude/agentic-pm-system-boXvy/deploy/phase1/setup.sh | bash
```

The script will:
1. Harden the server (firewall, fail2ban, auto-updates)
2. Install Docker + Caddy
3. Clone the repo
4. Generate all secrets (DB password, Redis password, etc.)
5. Prompt for your API keys
6. Build and start all services
7. Run DB migrations
8. Verify health

**Total time: ~15 minutes.**

## GitHub Actions CI/CD (Auto-Deploy on Push)

Add these secrets to your GitHub repo (`Settings → Secrets → Actions`):

| Secret | Value |
|---|---|
| `SERVER_HOST` | Your server IP or domain |
| `SERVER_USER` | `ubuntu` (or your SSH user) |
| `SERVER_SSH_KEY` | Private SSH key for the server |
| `SERVER_PORT` | `22` (default) |
| `NEXT_PUBLIC_API_URL` | `https://your-domain.com` |
| `NEXT_PUBLIC_WS_URL` | `wss://your-domain.com` |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | From Clerk dashboard |

After adding secrets, every push to `main` will:
- Run tests
- Build Docker images → push to GHCR
- SSH into server → pull new images → rolling restart → health check

## Useful Commands (on server)

```bash
# Full health check
bash /opt/agentic-pm/deploy/phase1/health.sh

# Redeploy (pull latest + restart)
bash /opt/agentic-pm/deploy/phase1/redeploy.sh

# View all logs
cd /opt/agentic-pm
docker compose -f deploy/phase1/docker-compose.prod.yml logs -f

# View specific service logs
docker compose -f deploy/phase1/docker-compose.prod.yml logs -f backend
docker compose -f deploy/phase1/docker-compose.prod.yml logs -f worker

# Restart a service
docker compose -f deploy/phase1/docker-compose.prod.yml restart backend

# Run DB migration manually
docker compose -f deploy/phase1/docker-compose.prod.yml exec postgres \
  psql -U pmuser -d agenticpm < backend/storage/migrations/001_initial.sql

# Backup database
bash /opt/agentic-pm/deploy/phase1/backup.sh
```

## Setup Nightly Backups

```bash
# Add to crontab (runs at 2am UTC)
echo "0 2 * * * /opt/agentic-pm/deploy/phase1/backup.sh >> /var/log/agentic-pm-backup.log 2>&1" | crontab -
```

## Services & Ports

| Service | Internal Port | External |
|---|---|---|
| Backend (FastAPI) | 8000 | via Caddy (HTTPS) |
| Frontend (Next.js) | 3000 | via Caddy (HTTPS) |
| PostgreSQL | 5432 | internal only |
| Redis | 6379 | internal only |
| Qdrant | 6333 | internal only |
| MinIO | 9000/9001 | internal only |

## Resource Requirements

| Tier | Instance | Cost/mo |
|---|---|---|
| Minimum (dev/small team) | t3.medium (2 vCPU, 4GB) | ~$30 |
| Recommended (internal tool) | t3.xlarge (4 vCPU, 16GB) | ~$120 |
| Comfortable headroom | t3.2xlarge (8 vCPU, 32GB) | ~$240 |
