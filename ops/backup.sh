#!/usr/bin/env bash
# Дамп БД: по расписанию (cron) и перед каждым выкатом (CD).
#
# Один pg_dump покрывает ВСЁ, включая файлы документов: блобы лежат в таблице
# blob (BYTEA), отдельного файлового хранилища нет.
#
# Запуск:  bash /opt/apps/shop/ops/backup.sh [префикс]
#   префикс по умолчанию daily; CD передаёт pre-<тег>.
# Переменные: KEEP — сколько дампов держать (по умолчанию 14).
set -euo pipefail

cd "$(dirname "$0")/.."          # корень проекта: рядом docker-compose.yml
PREFIX="${1:-daily}"
DIR="${BACKUP_DIR:-/opt/apps/backups}"
KEEP="${KEEP:-14}"
ts=$(date +%Y%m%d-%H%M%S)
part="$DIR/.${PREFIX}-${ts}.sql.gz.part"
out="$DIR/${PREFIX}-${ts}.sql.gz"

mkdir -p "$DIR"

# пишем во временный .part: оборванный дамп не должен выглядеть как годный бэкап
docker compose exec -T postgres \
  sh -c 'PGPASSWORD=$POSTGRES_PASSWORD pg_dump -U shop shop' | gzip > "$part"

# дамп годен, только если архив цел и не подозрительно мал (пустой = провал)
gzip -t "$part"
size=$(stat -c%s "$part")
if [ "$size" -lt 1000 ]; then
    rm -f "$part"
    echo "$(date -Is) FAIL ${PREFIX}: дамп подозрительно мал (${size} байт)" >&2
    exit 1
fi

mv "$part" "$out"                # только теперь бэкап «существует»

# чистим старые этого же вида, чтобы не забить диск VPS
ls -t "$DIR/${PREFIX}"-*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm --

# маркер свежести: по нему видно, что расписание живо (см. README ops)
date -Is > "$DIR/LAST_SUCCESS"
echo "$(date -Is) OK ${out} ($(du -h "$out" | cut -f1))"
