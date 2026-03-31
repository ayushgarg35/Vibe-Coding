#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Backup — dumps Postgres + uploads to S3/MinIO.
# Add to cron: 0 2 * * * /opt/agentic-pm/deploy/phase1/backup.sh
# ─────────────────────────────────────────────────────────────────
set -euo pipefail

APP_DIR="/opt/agentic-pm"
COMPOSE="docker compose -f ${APP_DIR}/deploy/phase1/docker-compose.prod.yml --env-file ${APP_DIR}/.env.production"
BACKUP_DIR="/opt/backups/agentic-pm"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
PG_USER=$(grep POSTGRES_USER "$APP_DIR/.env.production" | cut -d= -f2)
PG_DB=$(grep POSTGRES_DB "$APP_DIR/.env.production" | cut -d= -f2)

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

# Postgres dump
DUMP_FILE="$BACKUP_DIR/postgres_${TIMESTAMP}.sql.gz"
$COMPOSE exec -T postgres pg_dump -U "$PG_USER" "$PG_DB" | gzip > "$DUMP_FILE"
echo "[$(date)] Postgres dump: $DUMP_FILE ($(du -sh "$DUMP_FILE" | cut -f1))"

# Keep only last 7 days of local backups
find "$BACKUP_DIR" -name "postgres_*.sql.gz" -mtime +7 -delete
echo "[$(date)] Cleaned backups older than 7 days"

# Optional: upload to S3 (uncomment and configure)
# aws s3 cp "$DUMP_FILE" "s3://your-backup-bucket/agentic-pm/$(basename "$DUMP_FILE")"

echo "[$(date)] Backup complete"
