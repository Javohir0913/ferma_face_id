#!/bin/sh
# PostgreSQL zaxirasi: backups/ferma_YYYYMMDD_HHMMSS.dump (pg_dump custom format).
# Oxirgi KEEP_DAYS kundagilari saqlanadi. Cron misol (har kuni 02:30):
#   30 2 * * * cd /opt/ferma && ./deploy/backup.sh >> backups/backup.log 2>&1
# Tiklash:
#   docker compose exec -T db pg_restore -U ferma -d ferma --clean --if-exists < backups/<fayl>.dump
set -eu
cd "$(dirname "$0")/.."
KEEP_DAYS="${KEEP_DAYS:-30}"
mkdir -p backups
out="backups/ferma_$(date +%Y%m%d_%H%M%S).dump"
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$out.tmp"
mv "$out.tmp" "$out"
find backups -name 'ferma_*.dump' -mtime +"$KEEP_DAYS" -delete
echo "$(date '+%F %T') zaxira: $out ($(du -h "$out" | cut -f1))"
