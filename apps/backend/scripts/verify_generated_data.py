"""Validate raw-input hashes and the exact deterministic generated-data set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.structured.manifest import (  # noqa: E402
    BundleIntegrityError,
    validate_generated_bundle,
)


def main() -> int:
    default_generated = Path(__file__).resolve().parents[3] / "data/generated"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated-dir", type=Path, default=default_generated)
    parser.add_argument("--expected-bundle-version", default="2.0.0")
    args = parser.parse_args()
    try:
        result = validate_generated_bundle(args.generated_dir)
        if result.bundle_version != args.expected_bundle_version:
            raise BundleIntegrityError(
                "Generated bundle version mismatch: "
                f"{result.bundle_version} != {args.expected_bundle_version}"
            )
    except BundleIntegrityError as exc:
        print(f"verify_generated_data: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "valid",
                "bundle_version": result.bundle_version,
                "manifest_sha256": result.manifest_sha256,
                "files_checked": result.files_checked,
                "raw_inputs_checked": result.raw_inputs_checked,
                "exact_file_set": result.exact_file_set,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
