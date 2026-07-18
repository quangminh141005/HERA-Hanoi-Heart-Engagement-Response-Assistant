#!/usr/bin/env bash
set -Eeuo pipefail

umask 077
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

env_file=${ENV_FILE:-.env}
project_name=${PROJECT_NAME:-hera}
[[ ${CONFIRM_ROLLBACK:-NO} == YES ]] || {
  echo "Refusing rollback. Set CONFIRM_ROLLBACK=YES." >&2
  exit 2
}
[[ ${CONFIRM_SCHEMA_COMPATIBLE:-NO} == YES ]] || {
  echo "Refusing rollback without CONFIRM_SCHEMA_COMPATIBLE=YES." >&2
  exit 2
}
[[ $project_name =~ ^[a-z0-9][a-z0-9_-]*$ ]] || { echo "Invalid project name." >&2; exit 2; }
[[ -f $env_file && -f .release.env && -f .release.previous.env ]] || {
  echo "Rollback requires .env, .release.env and .release.previous.env." >&2
  exit 1
}
for command_name in docker awk mktemp; do
  command -v "$command_name" >/dev/null || { echo "$command_name is required." >&2; exit 1; }
done

get_env() {
  local file=$1 name=$2
  awk -F= -v key="$name" '$1 == key {sub(/^[^=]*=/, ""); sub(/\r$/, ""); value=$0} END {print value}' "$file"
}
previous_api=$(get_env .release.previous.env HERA_API_IMAGE_REPOSITORY)
previous_web=$(get_env .release.previous.env HERA_WEB_IMAGE_REPOSITORY)
previous_tag=$(get_env .release.previous.env HERA_IMAGE_TAG)
previous_version=$(get_env .release.previous.env APP_VERSION)
previous_version=${previous_version:-$previous_tag}
[[ $previous_api =~ ^ghcr\.io/[a-z0-9._/-]+$ ]] || { echo "Previous API repository is invalid." >&2; exit 1; }
[[ $previous_web =~ ^ghcr\.io/[a-z0-9._/-]+$ ]] || { echo "Previous web repository is invalid." >&2; exit 1; }
[[ $previous_tag =~ ^[0-9a-f]{40}$ ]] || { echo "Previous release is not pinned to a full Git SHA." >&2; exit 1; }
docker image inspect "$previous_api:$previous_tag" "$previous_web:$previous_tag" >/dev/null 2>&1 || {
  echo "Previous verified images are not present locally; pull them through the approved deploy flow first." >&2
  exit 1
}

saved_env=$(mktemp "$repo_root/.env.rollback.current.XXXXXX")
previous_metadata=$(mktemp "$repo_root/.release.rollback.previous.XXXXXX")
current_metadata=$(mktemp "$repo_root/.release.rollback.current.XXXXXX")
next_env=$(mktemp "$repo_root/.env.rollback.next.XXXXXX")
backup_result=$(mktemp "${TMPDIR:-/tmp}/hera-pre-rollback.XXXXXX")
cp -- "$env_file" "$saved_env"
cp -- .release.previous.env "$previous_metadata"
cp -- .release.env "$current_metadata"
chmod 600 "$saved_env" "$previous_metadata" "$current_metadata" "$next_env" "$backup_result"

compose=(docker compose --env-file "$env_file" -p "$project_name" -f docker-compose.yml)
rollback_started=false
rollback_complete=false
pre_rollback_backup=
cleanup() {
  local status=$?
  if ((status != 0)) && $rollback_started && ! $rollback_complete; then
    mv -f -- "$saved_env" "$env_file"
    chmod 600 "$env_file"
    docker compose --env-file "$env_file" -p "$project_name" -f docker-compose.yml \
      up -d --no-build --wait --wait-timeout 240 >/dev/null 2>&1 || true
    echo "Rollback failed; the current release configuration was restored." >&2
    [[ -n $pre_rollback_backup ]] && echo "Recovery backup: $pre_rollback_backup" >&2
  fi
  rm -f -- "$saved_env" "$previous_metadata" "$current_metadata" "$next_env" "$backup_result"
  exit "$status"
}
trap cleanup EXIT

BACKUP_DIR=${PRE_ROLLBACK_BACKUP_DIR:-$repo_root/backups/pre-rollback} \
BACKUP_RESULT_FILE=$backup_result ENV_FILE=$env_file PROJECT_NAME=$project_name \
  bash scripts/backup.sh
pre_rollback_backup=$(<"$backup_result")
[[ -s $pre_rollback_backup && -s $pre_rollback_backup.sha256 ]] || {
  echo "Automatic pre-rollback backup was not created." >&2
  exit 1
}

awk -F= -v api="$previous_api" -v web="$previous_web" -v tag="$previous_tag" -v version="$previous_version" '
  BEGIN {seen_api=seen_web=seen_tag=seen_version=0}
  $1 == "HERA_API_IMAGE_REPOSITORY" {print "HERA_API_IMAGE_REPOSITORY=" api; seen_api=1; next}
  $1 == "HERA_WEB_IMAGE_REPOSITORY" {print "HERA_WEB_IMAGE_REPOSITORY=" web; seen_web=1; next}
  $1 == "HERA_IMAGE_TAG" {print "HERA_IMAGE_TAG=" tag; seen_tag=1; next}
  $1 == "APP_VERSION" {print "APP_VERSION=" version; seen_version=1; next}
  {print}
  END {
    if (!seen_api) print "HERA_API_IMAGE_REPOSITORY=" api
    if (!seen_web) print "HERA_WEB_IMAGE_REPOSITORY=" web
    if (!seen_tag) print "HERA_IMAGE_TAG=" tag
    if (!seen_version) print "APP_VERSION=" version
  }
' "$env_file" >"$next_env"
chmod 600 "$next_env"
rollback_started=true
mv -f -- "$next_env" "$env_file"

compose=(docker compose --env-file "$env_file" -p "$project_name" -f docker-compose.yml)
"${compose[@]}" config --quiet
"${compose[@]}" run --rm --no-deps backend python scripts/verify_release_assets.py \
  --seed-archive /app/data/hera_postgres_seed.json.gz --expected-bundle-version 2.0.0
"${compose[@]}" up -d --no-build --wait --wait-timeout 240
"${compose[@]}" exec -T backend python scripts/smoke_deploy.py --base-url http://frontend

cp -- "$current_metadata" .release.previous.env
cp -- "$previous_metadata" .release.env
chmod 600 .release.previous.env .release.env "$env_file"
rollback_complete=true
echo "Rolled back to verified image tag: $previous_tag"
echo "Automatic PostgreSQL backup: $pre_rollback_backup"
