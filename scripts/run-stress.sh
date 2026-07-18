#!/usr/bin/env bash
set -Eeuo pipefail

profile=standard
scenario=mixed
replicas=1
min_replicas=1
confirm_extreme=false
project_name=hera-stress
stress_port=${STRESS_HTTP_PORT:-18080}
output_path=${STRESS_OUTPUT:-artifacts/stress/latest.json}

while (($#)); do
  case "$1" in
    --profile)
      (($# >= 2)) || { echo "--profile requires a value." >&2; exit 2; }
      profile=$2
      shift
      ;;
    --scenario)
      (($# >= 2)) || { echo "--scenario requires a value." >&2; exit 2; }
      scenario=$2
      shift
      ;;
    --replicas)
      (($# >= 2)) || { echo "--replicas requires a value." >&2; exit 2; }
      replicas=$2
      shift
      ;;
    --min-replicas)
      (($# >= 2)) || { echo "--min-replicas requires a value." >&2; exit 2; }
      min_replicas=$2
      shift
      ;;
    --confirm-extreme) confirm_extreme=true ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

[[ $profile =~ ^(ci|standard|extreme)$ ]] || {
  echo "Profile must be ci, standard or extreme." >&2; exit 2;
}
[[ $scenario =~ ^(reads|booking|mixed)$ ]] || {
  echo "Scenario must be reads, booking or mixed." >&2; exit 2;
}
[[ $replicas =~ ^[1-9][0-9]*$ && $min_replicas =~ ^[1-9][0-9]*$ ]] || {
  echo "Replica values must be positive integers." >&2; exit 2;
}
((min_replicas <= replicas)) || {
  echo "--min-replicas cannot exceed --replicas." >&2; exit 2;
}
if [[ $profile == extreme && $confirm_extreme != true ]]; then
  echo "Extreme stress requires --confirm-extreme." >&2
  exit 2
fi
if [[ $profile == extreme && $replicas -ne 3 ]]; then
  echo "Extreme stress is pinned to exactly three backend replicas." >&2
  exit 2
fi
[[ $stress_port =~ ^[0-9]+$ ]] && ((stress_port >= 1024 && stress_port <= 65535)) || {
  echo "STRESS_HTTP_PORT must be an unprivileged TCP port." >&2; exit 2;
}

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_root"
[[ -f scripts/stress_test.py ]] || {
  echo "scripts/stress_test.py is missing." >&2; exit 1;
}
for command_name in docker python3; do
  command -v "$command_name" >/dev/null || {
    echo "$command_name is required." >&2; exit 1;
  }
done
docker compose version >/dev/null

# The dedicated project name is a safety boundary for cleanup.
[[ $project_name == hera-stress ]] || {
  echo "Refusing an unexpected stress project name." >&2; exit 1;
}
if docker ps -aq \
  --filter "label=com.docker.compose.project=$project_name" | grep -q .; then
  echo "The dedicated hera-stress project already exists; inspect it before retrying." >&2
  exit 1
fi

env_args=()
if [[ -f .env ]]; then
  env_args=(--env-file .env)
fi
compose=(
  docker compose
  "${env_args[@]}"
  -p "$project_name"
  -f docker-compose.yml
  -f docker-compose.stress.yml
)

# Never expose or spend the operator's real model key in a load test.
export API_KEY=stress-placeholder-no-model-api-calls
export POSTGRES_PASSWORD=stress-postgres-only-0123456789abcdef
export HOLD_TOKEN_SECRET=stress-hold-only-0123456789abcdef0123456789abcdef
export BOOKING_PII_HASH_SECRET=stress-pii-only-0123456789abcdef0123456789abcdef
export HERA_API_IMAGE_REPOSITORY=hera-api
export HERA_WEB_IMAGE_REPOSITORY=hera-web
export STRESS_HTTP_PORT=$stress_port
export ENVIRONMENT=hackathon
export BOOKING_PROVIDER=local_prototype
export BOOKING_ALLOW_PROJECT_MVP_RULE=true
export BOOKING_REQUIRE_APPROVED_CAPACITY_RULE=false

started=false
cleanup() {
  local status=$?
  if $started; then
    "${compose[@]}" up -d --no-build --scale backend=1 backend frontend >/dev/null 2>&1 || true
    "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap cleanup EXIT

"${compose[@]}" config --quiet
if [[ ${STRESS_BUILD:-1} == 1 ]]; then
  "${compose[@]}" build backend frontend
fi
started=true
"${compose[@]}" up -d --no-build --wait --wait-timeout 240 \
  --scale "backend=$replicas"

mkdir -p "$(dirname "$output_path")"
python3 scripts/stress_test.py \
  --base-url "http://127.0.0.1:$stress_port" \
  --profile "$profile" \
  --scenario "$scenario" \
  --min-replicas "$min_replicas" \
  --output "$output_path"

echo "Stress report: $output_path"
