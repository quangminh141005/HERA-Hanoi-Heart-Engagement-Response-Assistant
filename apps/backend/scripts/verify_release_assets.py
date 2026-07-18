"""Fail-fast release checks for the PostgreSQL seed archive and source manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = Path(__file__).resolve().parent
for candidate in (BACKEND_ROOT, SCRIPTS_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.structured.manifest import (  # noqa: E402
    BundleIntegrityError,
    validate_generated_bundle,
)
from seed_postgres import SeedError, load_seed_archive  # noqa: E402


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed-archive",
        type=Path,
        default=BACKEND_ROOT / "data" / "hera_postgres_seed.json.gz",
        help="Checksum-pinned portable PostgreSQL seed archive.",
    )
    parser.add_argument(
        "--generated-dir",
        type=Path,
        default=None,
        help="Optional source directory containing 00-manifest.json and shards.",
    )
    parser.add_argument(
        "--require-generated",
        action="store_true",
        help="Fail when --generated-dir is unavailable.",
    )
    parser.add_argument(
        "--expected-bundle-version",
        default="2.0.0",
        help="Bundle version accepted by this release.",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    try:
        archive = load_seed_archive(args.seed_archive)
    except SeedError as exc:
        raise RuntimeError(str(exc)) from exc
    if archive.bundle_version != args.expected_bundle_version:
        raise RuntimeError(
            "PostgreSQL seed bundle version mismatch: "
            f"{archive.bundle_version} != {args.expected_bundle_version}"
        )

    evidence: dict[str, object] = {
        "runtime_database": "postgresql",
        "seed_archive": archive.path.name,
        "seed_archive_sha256": archive.archive_sha256,
        "bundle_version": archive.bundle_version,
        "manifest_sha256": archive.manifest_sha256,
        "table_counts": dict(sorted(archive.table_counts.items())),
    }

    generated_dir = args.generated_dir.resolve() if args.generated_dir else None
    if generated_dir and generated_dir.is_dir():
        try:
            bundle = validate_generated_bundle(generated_dir)
        except BundleIntegrityError as exc:
            raise RuntimeError(str(exc)) from exc
        if bundle.manifest_sha256 != archive.manifest_sha256:
            raise RuntimeError(
                "PostgreSQL seed archive and generated manifest have different "
                "SHA-256 values"
            )
        evidence["generated_bundle"] = {
            "files_checked": bundle.files_checked,
            "raw_inputs_checked": bundle.raw_inputs_checked,
            "exact_file_set": bundle.exact_file_set,
        }
    elif args.require_generated:
        raise RuntimeError(
            f"Generated bundle is missing: {generated_dir or '--generated-dir'}"
        )
    else:
        evidence["generated_bundle"] = "not_requested"

    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
