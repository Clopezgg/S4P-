#!/usr/bin/env bash
set -euo pipefail

# Restore only into a NEW disposable database on a local PostgreSQL instance.
# Never drop an existing target: even a QA database may contain evidence.
DUMP="${1:?uso: db_restore.sh <archivo.dump> <db_destino>}"
TARGET="${2:?uso: db_restore.sh <archivo.dump> <db_destino>}"

case "${PGHOST:-localhost}" in
  localhost|127.0.0.1) ;;
  *) echo "Restore requires a local isolated PostgreSQL host" >&2; exit 1 ;;
esac
if [[ ! "$TARGET" =~ ^(s4p_restore_|nexora_backup_target_)[a-z0-9_]+$ ]]; then
  echo "Restore target must be a disposable s4p_restore_ or nexora_backup_target_ database" >&2
  exit 1
fi
if [[ -n "${PGHOSTADDR:-}" || -n "${PGSERVICE:-}" || -n "${PGSERVICEFILE:-}" ]]; then
  echo "Restore refuses connection overrides (PGHOSTADDR/PGSERVICE/PGSERVICEFILE)" >&2
  exit 1
fi
[[ -r "$DUMP" ]] || { echo "Backup file is not readable" >&2; exit 1; }

# createdb fails if the target exists. Do not suppress that failure or clean it
# up automatically: preserve both existing data and failed-restore evidence.
createdb --host="${PGHOST:-localhost}" -- "$TARGET"
pg_restore --host="${PGHOST:-localhost}" --exit-on-error --single-transaction \
  --no-owner --no-privileges --dbname="$TARGET" -- "$DUMP"
echo "Restore real completado en '$TARGET'"
