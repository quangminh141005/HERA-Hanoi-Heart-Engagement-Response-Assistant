#!/usr/bin/env bash
set -Eeuo pipefail

# This command intentionally deletes only a dedicated development/demo/test
# Compose project's volumes. It can never target the default `hera` project.

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

env_file=${ENV_FILE:-.env}
project_name=${DEV_PROJECT_NAME:-hera-dev}
confirm=${CONFIRM_DATA_RESET:-NO}

[[ $confirm == YES ]] || {
  echo "Refusing reset. Set CONFIRM_DATA_RESET=YES." >&2
  exit 2
}
[[ $project_name =~ ^hera-(dev|demo|test)(-[a-z0-9_-]+)?$ ]] || {
  echo "DEV_PROJECT_NAME must start with hera-dev, hera-demo or hera-test." >&2
  exit 2
}
[[ $project_name != hera ]] || {
  echo "The production/default HERA project can never be reset by this script." >&2
  exit 2
}
[[ -f $env_file ]] || { echo "Missing env file: $env_file" >&2; exit 1; }

environment=$(awk -F= '$1 == "ENVIRONMENT" {sub(/^[^=]*=/, ""); sub(/\r$/, ""); value=$0} END {print tolower(value)}' "$env_file")
[[ $environment != production ]] || {
  echo "Refusing: ENVIRONMENT=production in $env_file." >&2
  exit 2
}

for command_name in docker awk; do
  command -v "$command_name" >/dev/null || {
    echo "$command_name is required." >&2
    exit 1
  }
done
docker compose version >/dev/null

compose=(docker compose --env-file "$env_file" -p "$project_name" -f docker-compose.yml)
"${compose[@]}" config --quiet

mapfile -t project_volumes < <(
  docker volume ls --quiet --filter "label=com.docker.compose.project=$project_name"
)
for volume in "${project_volumes[@]}"; do
  [[ $volume == "${project_name}_"* ]] || {
    echo "Refusing unexpected volume outside the project prefix: $volume" >&2
    exit 1
  }
done

if ((${#project_volumes[@]} > 0)); then
  BACKUP_DIR="$repo_root/backups/pre-reset-dev" \
  ENV_FILE="$env_file" PROJECT_NAME="$project_name" bash scripts/backup.sh
fi

# `down -v` is permitted only after all project/volume guards above pass.
"${compose[@]}" down -v --remove-orphans
"${compose[@]}" build backend
"${compose[@]}" up -d --wait --wait-timeout 120 db
"${compose[@]}" run --rm migrate
"${compose[@]}" run --rm seed

echo "Reset and reseeded dedicated project: $project_name"
echo "No volume belonging to the default/prod HERA project was touched."
