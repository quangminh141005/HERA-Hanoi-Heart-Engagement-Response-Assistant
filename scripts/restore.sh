#!/usr/bin/env bash
set -Eeuo pipefail

umask 077
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

env_file=${ENV_FILE:-.env}
project_name=${PROJECT_NAME:-hera}
restore_file=${RESTORE_FILE:-}
confirm_restore=${CONFIRM_RESTORE:-NO}

[[ $confirm_restore == YES ]] || {
  echo "Refusing destructive restore. Set CONFIRM_RESTORE=YES after checking the target." >&2
  exit 2
}
[[ $project_name =~ ^[a-z0-9][a-z0-9_-]*$ ]] || {
  echo "Invalid Compose project name." >&2
  exit 2
}
[[ -f $env_file ]] || { echo "Missing env file: $env_file" >&2; exit 1; }
[[ -n $restore_file && -f $restore_file ]] || {
  echo "RESTORE_FILE must point to an existing PostgreSQL custom dump." >&2
  exit 2
}
[[ -f $restore_file.sha256 ]] || {
  echo "Missing checksum sidecar: $restore_file.sha256" >&2
  exit 1
}
for command_name in docker sha256sum awk mktemp; do
  command -v "$command_name" >/dev/null || { echo "$command_name is required." >&2; exit 1; }
done

expected=$(awk 'NR == 1 {print $1}' "$restore_file.sha256")
actual=$(sha256sum "$restore_file" | awk '{print $1}')
[[ $expected =~ ^[0-9a-fA-F]{64}$ && ${actual,,} == ${expected,,} ]] || {
  echo "Backup checksum mismatch; restore was not started." >&2
  exit 1
}

compose=(docker compose --env-file "$env_file" -p "$project_name" -f docker-compose.yml)
"${compose[@]}" config --quiet
"${compose[@]}" up -d --wait --wait-timeout 120 db redis
"${compose[@]}" exec -T db sh -eu -c 'pg_restore --list >/dev/null' <"$restore_file"

result_file=$(mktemp "${TMPDIR:-/tmp}/hera-pre-restore.XXXXXX")
pre_restore_backup=
maintenance_started=false
restore_complete=false
cleanup() {
  local status=$?
  rm -f -- "$result_file"
  if ((status != 0)) && $maintenance_started && ! $restore_complete; then
    "${compose[@]}" stop frontend backend >/dev/null 2>&1 || true
    echo "Restore failed; frontend/backend remain stopped to avoid serving partial data." >&2
    [[ -n $pre_restore_backup ]] && echo "Recovery backup: $pre_restore_backup" >&2
  fi
  exit "$status"
}
trap cleanup EXIT

BACKUP_DIR=${PRE_RESTORE_BACKUP_DIR:-$repo_root/backups/pre-restore} \
BACKUP_RESULT_FILE=$result_file ENV_FILE=$env_file PROJECT_NAME=$project_name \
  bash scripts/backup.sh
pre_restore_backup=$(<"$result_file")
[[ -s $pre_restore_backup && -s $pre_restore_backup.sha256 ]] || {
  echo "Automatic pre-restore backup was not created." >&2
  exit 1
}

maintenance_started=true
"${compose[@]}" stop frontend backend
"${compose[@]}" exec -T db sh -eu -c \
  'pg_restore --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --clean --if-exists --no-owner --no-privileges --exit-on-error' \
  <"$restore_file"
"${compose[@]}" run --rm --no-deps migrate
"${compose[@]}" up -d --no-build --no-deps --wait --wait-timeout 240 backend frontend
"${compose[@]}" exec -T backend python scripts/smoke_deploy.py --base-url http://frontend
restore_complete=true
echo "Restore completed from: $restore_file"
echo "Automatic recovery backup: $pre_restore_backup"
