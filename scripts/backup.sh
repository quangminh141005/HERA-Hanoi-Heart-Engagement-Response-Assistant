#!/usr/bin/env bash
set -Eeuo pipefail

umask 077
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

env_file=${ENV_FILE:-.env}
project_name=${PROJECT_NAME:-hera}
backup_dir=${BACKUP_DIR:-$repo_root/backups}
result_file=${BACKUP_RESULT_FILE:-}

[[ $project_name =~ ^[a-z0-9][a-z0-9_-]*$ ]] || {
  echo "Invalid Compose project name." >&2
  exit 2
}
[[ -f $env_file ]] || { echo "Missing env file: $env_file" >&2; exit 1; }
for command_name in docker sha256sum; do
  command -v "$command_name" >/dev/null || {
    echo "$command_name is required." >&2
    exit 1
  }
done
docker compose version >/dev/null

mkdir -p -- "$backup_dir"
chmod 700 "$backup_dir"
backup_dir=$(cd "$backup_dir" && pwd -P)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
filename="hera-postgresql-$stamp.dump"
final_path="$backup_dir/$filename"
partial_path="$backup_dir/.$filename.partial.$$"
[[ ! -e $final_path && ! -e $final_path.sha256 ]] || {
  echo "Backup name already exists: $final_path" >&2
  exit 1
}

cleanup() {
  rm -f -- "$partial_path"
}
trap cleanup EXIT

compose=(docker compose --env-file "$env_file" -p "$project_name" -f docker-compose.yml)
"${compose[@]}" config --quiet
"${compose[@]}" up -d --wait --wait-timeout 120 db

"${compose[@]}" exec -T db sh -eu -c \
  'pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format=custom --no-owner --no-privileges' \
  >"$partial_path"
[[ -s $partial_path ]] || { echo "pg_dump produced an empty file." >&2; exit 1; }
"${compose[@]}" exec -T db sh -eu -c 'pg_restore --list >/dev/null' <"$partial_path"

mv -- "$partial_path" "$final_path"
chmod 600 "$final_path"
(
  cd "$backup_dir"
  sha256sum "$filename" >"$filename.sha256"
  chmod 600 "$filename.sha256"
)

if [[ -n $result_file ]]; then
  printf '%s\n' "$final_path" >"$result_file"
  chmod 600 "$result_file"
fi
echo "PostgreSQL backup: $final_path"
echo "Checksum: $final_path.sha256"
