#!/usr/bin/env bash
# RNF-08: copia de seguridad diaria con retención de 30 días.
# Cron sugerido:  0 2 * * *  /ruta/scripts/backup_db.sh
set -euo pipefail
DEST="${BACKUP_DIR:-/var/backups/desaparecidos}"
mkdir -p "$DEST"
export PGPASSWORD="${DB_PASSWORD:-desap}"
pg_dump -h "${DB_HOST:-localhost}" -p "${DB_PORT:-5432}" -U "${DB_USER:-desap}" -Fc "${DB_NAME:-desaparecidos}" \
  -f "$DEST/desaparecidos_$(date +%Y%m%d_%H%M%S).dump"
# Los archivos cifrados (fotos/videos) también se respaldan
[ -d "${PRIVATE_MEDIA_ROOT:-}" ] && tar -czf "$DEST/media_$(date +%Y%m%d).tar.gz" -C "$PRIVATE_MEDIA_ROOT" .
find "$DEST" -type f -mtime +30 -delete
