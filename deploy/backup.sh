#!/bin/sh
# Резервная копия PostgreSQL: backups/ferma_YYYYMMDD_HHMMSS.dump (формат pg_dump custom).
# Хранятся копии за последние KEEP_DAYS дней. Пример cron (каждый день в 02:30):
#   30 2 * * * cd /opt/ferma && ./deploy/backup.sh >> backups/backup.log 2>&1
# Восстановление:
#   docker compose exec -T db pg_restore -U ferma -d ferma --clean --if-exists < backups/<файл>.dump
set -eu
cd "$(dirname "$0")/.."
KEEP_DAYS="${KEEP_DAYS:-30}"
mkdir -p backups
out="backups/ferma_$(date +%Y%m%d_%H%M%S).dump"
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$out.tmp"
mv "$out.tmp" "$out"
find backups -name 'ferma_*.dump' -mtime +"$KEEP_DAYS" -delete
echo "$(date '+%F %T') zaxira: $out ($(du -h "$out" | cut -f1))"
