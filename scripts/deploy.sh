#!/usr/bin/env bash
set -Eeuo pipefail

monitoring=false
skip_build=false
run_model_preflight=false
env_file=.env
project_name=hera

while (($#)); do
  case "$1" in
    --monitoring) monitoring=true ;;
    --skip-build) skip_build=true ;;
    --model-preflight) run_model_preflight=true ;;
    --skip-model-preflight) run_model_preflight=false ;;
    --env-file)
      (($# >= 2)) || { echo "--env-file requires a value." >&2; exit 2; }
      env_file=$2
      shift
      ;;
    --project-name)
      (($# >= 2)) || { echo "--project-name requires a value." >&2; exit 2; }
      project_name=$2
      shift
      ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

[[ $project_name =~ ^[a-z0-9][a-z0-9_-]*$ ]] || {
  echo "Project name must contain only lowercase letters, numbers, underscore or dash." >&2
  exit 2
}

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"

for command_name in docker openssl; do
  command -v "$command_name" >/dev/null || {
    echo "$command_name is required but was not found." >&2
    exit 1
  }
done
docker compose version >/dev/null

restrict_secret_file() {
  local file=$1 filesystem_type
  if chmod 600 "$file"; then
    return 0
  fi

  filesystem_type=$(stat -f -c %T "$file" 2>/dev/null || true)
  case "$filesystem_type" in
    9p|v9fs|drvfs)
      echo "Warning: could not enforce mode 600 on $file because this appears to be a WSL/Windows mount ($filesystem_type)." >&2
      echo "Keep this local env file private and avoid committing or sharing it." >&2
      ;;
    *)
      echo "Could not restrict $file to mode 600; refusing to continue." >&2
      exit 1
      ;;
  esac
}

if [[ ! -f "$env_file" ]]; then
  cp .env.example "$env_file"
  echo "Created $env_file from .env.example."
fi
restrict_secret_file "$env_file"

get_env() {
  local file=$1 name=$2
  [[ -f "$file" ]] || return 0
  awk -F= -v key="$name" '
    $1 == key {sub(/^[^=]*=/, ""); sub(/\r$/, ""); value=$0}
    END {print value}
  ' "$file"
}

verify_internal_release_manifest() {
  local package_root manifest
  package_root=$(cd "$repo_root/.." && pwd)
  manifest="$package_root/release-manifest.sha256"
  [[ -f "$manifest" ]] || return 0
  command -v sha256sum >/dev/null || {
    echo "sha256sum is required to verify this release package." >&2
    exit 1
  }
  (
    cd "$package_root"
    sha256sum --quiet -c release-manifest.sha256
  )
  echo "Verified the internal release payload manifest."
}

set_env() {
  local file=$1 name=$2 value=$3 temporary
  temporary=$(mktemp)
  awk -F= -v key="$name" -v replacement="$name=$value" '
    BEGIN {found=0}
    $1 == key {print replacement; found=1; next}
    {print}
    END {if (!found) print replacement}
  ' "$file" > "$temporary"
  restrict_secret_file "$temporary"
  mv "$temporary" "$file"
}

configured_api_repository=$(get_env "$env_file" HERA_API_IMAGE_REPOSITORY)
if [[ $configured_api_repository == ghcr.io/* || -f .release.env ]]; then
  echo "This server is pinned to a CI-verified GHCR release." >&2
  echo "Refusing a local rebuild that could overwrite the verified SHA tag." >&2
  echo "Deploy updates through the GitHub workflow; use docker compose --no-build only for an ordinary restart." >&2
  exit 1
fi

for secret_name in POSTGRES_PASSWORD HOLD_TOKEN_SECRET BOOKING_PII_HASH_SECRET GRAFANA_ADMIN_PASSWORD; do
  if [[ -z "$(get_env "$env_file" "$secret_name")" ]]; then
    set_env "$env_file" "$secret_name" "$(openssl rand -hex 32)"
    echo "Generated $secret_name in the ignored env file."
  fi
done

if [[ -z "$(get_env "$env_file" API_KEY)" ]]; then
  parent_api_key=$(get_env ../.env API_KEY)
  if [[ -z "$parent_api_key" ]]; then
    echo "API_KEY is missing. Put the FPT key in .env or ../.env." >&2
    exit 1
  fi
  export API_KEY="$parent_api_key"
  unset parent_api_key
  echo "Using API_KEY from ../.env without copying or printing it."
fi

required_paths=(
  apps/backend/data/hera_postgres_seed.json.gz
  apps/backend/data/hera_postgres_seed.json.gz.sha256
)
for required_path in "${required_paths[@]}"; do
  [[ -e "$required_path" ]] || {
    echo "Required release data is missing: $required_path" >&2
    exit 1
  }
done
[[ -s apps/backend/data/hera_postgres_seed.json.gz ]] || {
  echo "hera_postgres_seed.json.gz is empty." >&2
  exit 1
}
verify_internal_release_manifest
if command -v git >/dev/null && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git check-ignore -q "$env_file" || {
    echo "$env_file is not ignored by Git; refusing to continue." >&2
    exit 1
  }
else
  echo "Release bundle has no Git worktree; Git ignore check is not applicable."
fi

compose=(docker compose --env-file "$env_file" -p "$project_name" -f docker-compose.yml)
if $monitoring; then
  compose+=(-f docker-compose.monitoring.yml)
fi

"${compose[@]}" config --quiet
if ! $skip_build; then
  "${compose[@]}" build --pull backend frontend
fi
"${compose[@]}" run --rm --no-deps backend \
  python scripts/verify_release_assets.py \
  --seed-archive /app/data/hera_postgres_seed.json.gz \
  --expected-bundle-version 2.0.0
if $run_model_preflight; then
  "${compose[@]}" run --rm --no-deps backend \
    python scripts/verify_model_gateway.py
else
  echo "Paid model preflight not requested; deploy continues with offline config/readiness checks."
fi
BACKUP_DIR="$repo_root/backups/pre-deploy" ENV_FILE="$env_file" \
PROJECT_NAME="$project_name" bash scripts/backup.sh
"${compose[@]}" up -d --wait --wait-timeout 240
"${compose[@]}" exec -T backend \
  python scripts/smoke_deploy.py --base-url http://frontend

public_base_url=$(get_env "$env_file" PUBLIC_BASE_URL)
echo "HERA is healthy at ${public_base_url:-http://127.0.0.1:8080}"
if $monitoring; then
  grafana_port=$(get_env "$env_file" GRAFANA_PORT)
  echo "Grafana is available on loopback port ${grafana_port:-13000}."
fi
unset API_KEY 2>/dev/null || true
