#!/usr/bin/env bash
set -Eeuo pipefail

# Deploy an already tested GHCR release on an Ubuntu server. The GHCR token is
# read from stdin and stored only in a temporary DOCKER_CONFIG directory.

api_repository=
web_repository=
image_tag=
ghcr_user=
project_name=hera
run_model_preflight=false

while (($#)); do
  case "$1" in
    --api-repository) api_repository=${2:?}; shift ;;
    --web-repository) web_repository=${2:?}; shift ;;
    --image-tag) image_tag=${2:?}; shift ;;
    --ghcr-user) ghcr_user=${2:?}; shift ;;
    --project-name) project_name=${2:?}; shift ;;
    --model-preflight) run_model_preflight=true ;;
    --skip-model-preflight) run_model_preflight=false ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

[[ $api_repository =~ ^ghcr\.io/[a-z0-9._/-]+$ ]] || {
  echo "Invalid API image repository." >&2; exit 2;
}
[[ $web_repository =~ ^ghcr\.io/[a-z0-9._/-]+$ ]] || {
  echo "Invalid web image repository." >&2; exit 2;
}
[[ $image_tag =~ ^[0-9a-f]{40}$ ]] || {
  echo "Image tag must be a full 40-character Git commit SHA." >&2; exit 2;
}
[[ $ghcr_user =~ ^[A-Za-z0-9-]+$ ]] || {
  echo "Invalid GHCR user." >&2; exit 2;
}
[[ $project_name =~ ^[a-z0-9][a-z0-9_-]*$ ]] || {
  echo "Invalid Compose project name." >&2; exit 2;
}

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
[[ -f .env ]] || { echo ".env is missing on the server." >&2; exit 1; }
chmod 600 .env

for command_name in docker awk mktemp; do
  command -v "$command_name" >/dev/null || {
    echo "$command_name is required but was not found." >&2; exit 1;
  }
done
docker compose version >/dev/null

exec 9>.hera-deploy.lock
if command -v flock >/dev/null; then
  flock -n 9 || { echo "Another HERA deployment is already running." >&2; exit 1; }
fi

get_env() {
  local file=$1 name=$2
  [[ -f $file ]] || return 0
  awk -F= -v key="$name" '
    $1 == key {sub(/^[^=]*=/, ""); sub(/\r$/, ""); value=$0}
    END {print value}
  ' "$file"
}

verify_internal_release_manifest() {
  local package_root manifest
  package_root=$(cd "$repo_root/.." && pwd)
  manifest="$package_root/release-manifest.sha256"
  [[ -f $manifest ]] || return 0
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

image_digest() {
  local image=$1 repository=$2
  docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$image" |
    awk -v prefix="$repository@" 'index($0, prefix) == 1 {print; exit}'
}

promote_release() {
  local candidate=$1 env_next release_next previous_next
  env_next=$(mktemp .env.next.XXXXXX)
  release_next=$(mktemp .release.next.XXXXXX)
  previous_next=$(mktemp .release.previous.next.XXXXXX)

  awk \
    -v api="$api_repository" \
    -v web="$web_repository" \
    -v tag="$image_tag" '
      BEGIN {seen_api=seen_web=seen_tag=seen_version=0}
      /^HERA_API_IMAGE_REPOSITORY=/ {print "HERA_API_IMAGE_REPOSITORY=" api; seen_api=1; next}
      /^HERA_WEB_IMAGE_REPOSITORY=/ {print "HERA_WEB_IMAGE_REPOSITORY=" web; seen_web=1; next}
      /^HERA_IMAGE_TAG=/ {print "HERA_IMAGE_TAG=" tag; seen_tag=1; next}
      /^APP_VERSION=/ {print "APP_VERSION=" tag; seen_version=1; next}
      {print}
      END {
        if (!seen_api) print "HERA_API_IMAGE_REPOSITORY=" api
        if (!seen_web) print "HERA_WEB_IMAGE_REPOSITORY=" web
        if (!seen_tag) print "HERA_IMAGE_TAG=" tag
        if (!seen_version) print "APP_VERSION=" tag
      }
    ' .env >"$env_next"
  chmod 600 "$env_next"
  cp -- "$candidate" "$release_next"
  chmod 600 "$release_next"

  if [[ -f .release.env ]]; then
    cp -- .release.env "$previous_next"
  else
    {
      echo "RELEASE_STATUS=pre_ci_release"
      echo "HERA_API_IMAGE_REPOSITORY=$(get_env .env HERA_API_IMAGE_REPOSITORY)"
      echo "HERA_WEB_IMAGE_REPOSITORY=$(get_env .env HERA_WEB_IMAGE_REPOSITORY)"
      echo "HERA_IMAGE_TAG=$(get_env .env HERA_IMAGE_TAG)"
      echo "APP_VERSION=$(get_env .env APP_VERSION)"
    } >"$previous_next"
  fi
  chmod 600 "$previous_next"

  # Every file is prepared before these same-filesystem atomic renames.
  mv -f -- "$previous_next" .release.previous.env
  mv -f -- "$env_next" .env
  mv -f -- "$release_next" .release.env
}

docker_config=$(mktemp -d "${TMPDIR:-/tmp}/hera-docker-config.XXXXXX")
candidate=$(mktemp .release.candidate.XXXXXX)
backup_result=$(mktemp "${TMPDIR:-/tmp}/hera-pre-deploy.XXXXXX")
deployment_started=false
promoted=false
pre_deploy_backup=

old_api=$(get_env .env HERA_API_IMAGE_REPOSITORY)
old_web=$(get_env .env HERA_WEB_IMAGE_REPOSITORY)
old_tag=$(get_env .env HERA_IMAGE_TAG)
old_api=${old_api:-hera-api}
old_web=${old_web:-hera-web}
old_tag=${old_tag:-local}
rollback_available=false
if docker image inspect "$old_api:$old_tag" "$old_web:$old_tag" >/dev/null 2>&1; then
  rollback_available=true
fi

cleanup() {
  local status=$?
  if ((status != 0)) && $deployment_started && ! $promoted && $rollback_available; then
    echo "Deployment failed; attempting the previous image tag from .env." >&2
    unset HERA_API_IMAGE_REPOSITORY HERA_WEB_IMAGE_REPOSITORY HERA_IMAGE_TAG APP_VERSION
    docker compose --env-file .env -p "$project_name" -f docker-compose.yml \
      up -d --no-build --wait --wait-timeout 240 >&2 || true
  fi
  rm -f -- "$candidate"
  rm -f -- "$backup_result"
  rm -rf -- "$docker_config"
  exit "$status"
}
trap cleanup EXIT

export DOCKER_CONFIG=$docker_config
docker login ghcr.io -u "$ghcr_user" --password-stdin >/dev/null

export HERA_API_IMAGE_REPOSITORY=$api_repository
export HERA_WEB_IMAGE_REPOSITORY=$web_repository
export HERA_IMAGE_TAG=$image_tag
export APP_VERSION=$image_tag
compose=(docker compose --env-file .env -p "$project_name" -f docker-compose.yml)

verify_internal_release_manifest
"${compose[@]}" config --quiet
"${compose[@]}" pull backend frontend

api_digest=$(image_digest "$api_repository:$image_tag" "$api_repository")
web_digest=$(image_digest "$web_repository:$image_tag" "$web_repository")
[[ $api_digest == "$api_repository@sha256:"* ]] || {
  echo "Could not resolve the pulled API image digest." >&2; exit 1;
}
[[ $web_digest == "$web_repository@sha256:"* ]] || {
  echo "Could not resolve the pulled web image digest." >&2; exit 1;
}

{
  echo "RELEASE_STATUS=verified"
  echo "DEPLOYED_AT_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "RELEASE_GIT_SHA=$image_tag"
  echo "HERA_API_IMAGE_REPOSITORY=$api_repository"
  echo "HERA_WEB_IMAGE_REPOSITORY=$web_repository"
  echo "HERA_IMAGE_TAG=$image_tag"
  echo "HERA_API_IMAGE_DIGEST=$api_digest"
  echo "HERA_WEB_IMAGE_DIGEST=$web_digest"
} >"$candidate"
chmod 600 "$candidate"

"${compose[@]}" run --rm --no-deps backend \
  python scripts/verify_release_assets.py \
  --seed-archive /app/data/hera_postgres_seed.json.gz \
  --expected-bundle-version 2.0.0
if $run_model_preflight; then
  "${compose[@]}" run --rm --no-deps backend \
    python scripts/verify_model_gateway.py
else
  echo "Paid model preflight not requested; release verification remains offline."
fi

BACKUP_DIR="$repo_root/backups/pre-deploy" BACKUP_RESULT_FILE="$backup_result" \
ENV_FILE=.env PROJECT_NAME="$project_name" bash scripts/backup.sh
pre_deploy_backup=$(<"$backup_result")
[[ -s $pre_deploy_backup && -s $pre_deploy_backup.sha256 ]] || {
  echo "Automatic pre-deploy PostgreSQL backup was not created." >&2
  exit 1
}

deployment_started=true
"${compose[@]}" up -d --no-build --wait --wait-timeout 240
"${compose[@]}" exec -T backend \
  python scripts/smoke_deploy.py --base-url http://frontend

promote_release "$candidate"
promoted=true
echo "Deployed and recorded release $image_tag ($api_digest, $web_digest)."
echo "Pre-deploy PostgreSQL backup: $pre_deploy_backup"
