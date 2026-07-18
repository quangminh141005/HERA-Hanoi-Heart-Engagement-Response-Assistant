#!/usr/bin/env bash
set -Eeuo pipefail

umask 077
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
repo_name=$(basename "$repo_root")
output_dir=${OUTPUT_DIRECTORY:-$workspace_root/release}
release_name=${RELEASE_NAME:-}

for command_name in python3 sha256sum tar; do
  command -v "$command_name" >/dev/null || { echo "$command_name is required." >&2; exit 1; }
done

full_commit=unavailable
short_commit=uncommitted
git_dirty=null
if command -v git >/dev/null && git -C "$repo_root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  full_commit=$(git -C "$repo_root" rev-parse HEAD)
  short_commit=${full_commit:0:12}
  if [[ -n $(git -C "$repo_root" status --porcelain --untracked-files=all) ]]; then
    git_dirty=true
  else
    git_dirty=false
  fi
fi
if [[ -z $release_name ]]; then
  release_name="HERA-$(date -u +%Y%m%dT%H%M%SZ)-$short_commit"
fi
[[ $release_name =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo "RELEASE_NAME contains an unsafe character." >&2
  exit 2
}

seed_archive="$repo_root/apps/backend/data/hera_postgres_seed.json.gz"
seed_checksum="$seed_archive.sha256"
[[ -s $seed_archive && -s $seed_checksum ]] || {
  echo "The PostgreSQL seed archive or checksum is missing." >&2
  exit 1
}
(
  cd "$(dirname "$seed_archive")"
  sha256sum --quiet --check "$(basename "$seed_checksum")"
)

mkdir -p -- "$output_dir"
chmod 700 "$output_dir"
output_dir=$(cd "$output_dir" && pwd -P)
zip_path="$output_dir/$release_name.zip"
checksum_path="$zip_path.sha256"
[[ ! -e $zip_path && ! -e $checksum_path ]] || {
  echo "Release already exists: $zip_path" >&2
  exit 1
}

temp_root=$(mktemp -d "${TMPDIR:-/tmp}/hera-release.XXXXXX")
package_root="$temp_root/HERA"
package_repo="$package_root/$repo_name"
mkdir -p "$package_repo"
cleanup() {
  local resolved
  resolved=$(cd "$temp_root" 2>/dev/null && pwd -P || true)
  if [[ -n $resolved && $resolved == "${TMPDIR:-/tmp}"/hera-release.* ]]; then
    rm -rf -- "$resolved"
  fi
}
trap cleanup EXIT

tar -C "$repo_root" \
  --exclude='./.git' \
  --exclude='./.env' --exclude='./.env.*' --exclude='*.env' --exclude='*.env.*' \
  --exclude='./.venv' --exclude='*/node_modules' --exclude='*/dist' \
  --exclude='*/__pycache__' --exclude='*/.pytest_cache' --exclude='*/.ruff_cache' \
  --exclude='*/.mypy_cache' --exclude='./.tmp' --exclude='./artifacts' --exclude='./backups' \
  --exclude='.release*.env' --exclude='.hera-deploy.lock' \
  --exclude='.npmrc' --exclude='.pypirc' --exclude='.netrc' \
  --exclude='id_rsa' --exclude='id_ed25519' \
  --exclude='*.pem' --exclude='*.key' --exclude='*.p12' --exclude='*.pfx' \
  --exclude='*.db' --exclude='*.db-wal' --exclude='*.db-shm' --exclude='*.db-journal' \
  --exclude='*.log' --exclude='*.pyc' \
  --exclude='release-manifest.sha256' --exclude='release-metadata.json' \
  -cf - . | tar -C "$package_repo" -xf -
cp -- "$repo_root/.env.example" "$package_repo/.env.example"

for documentation in TECHNICAL.md PROBLEM.md Embedding.md LLM.md data-generation-spec.json; do
  [[ -f $workspace_root/$documentation ]] && cp -- "$workspace_root/$documentation" "$package_root/$documentation"
done

PACKAGE_ROOT=$package_root PACKAGE_REPO=$package_repo RELEASE_NAME=$release_name \
FULL_COMMIT=$full_commit GIT_DIRTY=$git_dirty python3 - <<'PY'
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["PACKAGE_ROOT"])
repo = Path(os.environ["PACKAGE_REPO"])
archive = repo / "apps/backend/data/hera_postgres_seed.json.gz"
checksum = archive.with_name(archive.name + ".sha256")
if not archive.is_file() or not checksum.is_file():
    raise SystemExit("Packaged PostgreSQL seed files are missing")

expected_parts = checksum.read_text(encoding="ascii").strip().split()
if len(expected_parts) != 2 or expected_parts[1] != archive.name:
    raise SystemExit("Malformed PostgreSQL seed checksum sidecar")
archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
if archive_sha != expected_parts[0].lower():
    raise SystemExit("Packaged PostgreSQL seed checksum mismatch")
with gzip.open(archive, "rt", encoding="utf-8") as stream:
    seed = json.load(stream)
if seed.get("format") != "hera-postgres-seed-v1":
    raise SystemExit("Unsupported PostgreSQL seed format")

for path in root.rglob("*"):
    if path.is_symlink():
        raise SystemExit(f"Symlink is not permitted in a release: {path.relative_to(root)}")
    if not path.is_file():
        continue
    relative = path.relative_to(root)
    if "\n" in relative.as_posix() or "\r" in relative.as_posix():
        raise SystemExit("Newline in release path is not permitted")
    name = path.name.lower()
    if name == ".env.example":
        continue
    forbidden = (
        name == ".env"
        or name.startswith(".env.")
        or name.endswith(".env")
        or ".env." in name
        or name in {".envrc", ".npmrc", ".pypirc", ".netrc", "id_rsa", "id_ed25519"}
        or any(name.endswith(suffix) for suffix in (".pem", ".key", ".p12", ".pfx", ".db", ".db-wal", ".db-shm", ".db-journal"))
    )
    if forbidden:
        raise SystemExit(f"Credential/database-shaped file entered release: {relative}")

table_counts = seed.get("source_table_counts", {})
if not isinstance(table_counts, dict):
    table_counts = {}
tables = seed.get("tables", [])
if isinstance(tables, list):
    for table in tables:
        if isinstance(table, dict) and isinstance(table.get("rows"), list):
            table_counts[str(table.get("name"))] = len(table["rows"])
metadata = {
    "schema_version": "1.0",
    "release_name": os.environ["RELEASE_NAME"],
    "source": {
        "repository": repo.name,
        "git_commit": os.environ["FULL_COMMIT"],
        "git_dirty": None if os.environ["GIT_DIRTY"] == "null" else os.environ["GIT_DIRTY"] == "true",
    },
    "application": {
        "llm_model": "gpt-oss-120b",
        "embedding_model": "Vietnamese_Embedding",
        "embedding_dimensions": 1024,
    },
    "data": {
        "runtime_database": "postgresql",
        "seed_format": seed["format"],
        "bundle_version": seed.get("bundle_version"),
        "generated_manifest_sha256": seed.get("manifest_sha256"),
        "alembic_revision": seed.get("alembic_revision"),
        "postgres_seed_archive_sha256": archive_sha,
        "table_counts": dict(sorted(table_counts.items())),
    },
    "verification": {
        "external_zip_checksum": os.environ["RELEASE_NAME"] + ".zip.sha256",
        "internal_payload_manifest": "release-manifest.sha256",
    },
}
(root / "release-metadata.json").write_text(
    json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)

manifest = root / "release-manifest.sha256"
lines = []
for path in sorted((item for item in root.rglob("*") if item.is_file() and item != manifest), key=lambda item: item.relative_to(root).as_posix()):
    relative = path.relative_to(root).as_posix()
    lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {relative}")
manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

PACKAGE_ROOT=$package_root ZIP_PATH=$zip_path python3 - <<'PY'
from pathlib import Path
import os
import zipfile

root = Path(os.environ["PACKAGE_ROOT"])
destination = Path(os.environ["ZIP_PATH"])
with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(root).as_posix()):
        archive.write(path, (Path(root.name) / path.relative_to(root)).as_posix())
PY
chmod 600 "$zip_path"
(
  cd "$output_dir"
  sha256sum "$(basename "$zip_path")" >"$(basename "$checksum_path")"
  chmod 600 "$(basename "$checksum_path")"
)
echo "Release package: $zip_path"
echo "SHA-256 file: $checksum_path"
echo "The package contains PostgreSQL seed data, metadata and a per-file manifest; no .env or .db file."
