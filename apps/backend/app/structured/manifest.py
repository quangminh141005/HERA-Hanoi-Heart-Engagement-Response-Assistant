"""Integrity checks for the deterministic generated-data bundle."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class BundleIntegrityError(RuntimeError):
    """Raised when the generated bundle cannot be trusted."""


@dataclass(frozen=True)
class BundleIntegrityResult:
    """Evidence returned after validating the complete bundle."""

    bundle_version: str
    manifest_sha256: str
    files_checked: int
    raw_inputs_checked: int
    exact_file_set: bool


def sha256_file(path: Path) -> str:
    """Return a file SHA-256 without loading large shards into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(generated_dir: Path) -> dict[str, Any]:
    """Load the bundle manifest as strict UTF-8 JSON."""

    manifest_path = generated_dir / "00-manifest.json"
    if not manifest_path.is_file():
        raise BundleIntegrityError(f"Missing manifest: {manifest_path}")
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleIntegrityError(f"Invalid manifest JSON: {exc}") from exc


def validate_generated_bundle(generated_dir: Path) -> BundleIntegrityResult:
    """Validate exact-set, byte-count and SHA-256 invariants.

    The function intentionally validates raw inputs as well as generated shards.
    A database must never be rebuilt from a partial or silently modified bundle.
    """

    generated_dir = generated_dir.resolve()
    manifest = load_manifest(generated_dir)
    manifest_path = generated_dir / "00-manifest.json"
    report_path = generated_dir / "23-validation-report.json"

    declared_files = manifest.get("files")
    if not isinstance(declared_files, list) or not declared_files:
        raise BundleIntegrityError("manifest.files must be a non-empty array")

    expected_names = {
        "00-manifest.json",
        "23-validation-report.json",
        *(
            str(item.get("file", ""))
            for item in declared_files
            if isinstance(item, dict)
        ),
    }
    if "" in expected_names:
        raise BundleIntegrityError("manifest.files contains an empty file name")

    actual_names = {path.name for path in generated_dir.glob("*.json")}
    missing = sorted(expected_names - actual_names)
    extra = sorted(actual_names - expected_names)
    if missing or extra:
        raise BundleIntegrityError(
            "Generated bundle exact-set mismatch: "
            f"missing={missing or []}, extra={extra or []}"
        )

    for item in declared_files:
        if not isinstance(item, dict):
            raise BundleIntegrityError("manifest.files contains a non-object entry")
        file_name = str(item.get("file", ""))
        path = generated_dir / file_name
        expected_bytes = int(item.get("bytes", -1))
        actual_bytes = path.stat().st_size
        if actual_bytes != expected_bytes:
            raise BundleIntegrityError(
                f"Byte-count mismatch for {file_name}: "
                f"expected {expected_bytes}, got {actual_bytes}"
            )
        expected_hash = str(item.get("sha256", ""))
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise BundleIntegrityError(
                f"SHA-256 mismatch for {file_name}: "
                f"expected {expected_hash}, got {actual_hash}"
            )

    if not report_path.is_file():
        raise BundleIntegrityError("Missing 23-validation-report.json")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleIntegrityError(f"Invalid validation report JSON: {exc}") from exc

    manifest_hash = sha256_file(manifest_path)
    report_manifest_hash = str(
        report.get("manifest_sha256")
        or (report.get("manifest") or {}).get("sha256")
        or ""
    )
    if report_manifest_hash != manifest_hash:
        raise BundleIntegrityError(
            "Validation report does not match 00-manifest.json: "
            f"expected {report_manifest_hash}, got {manifest_hash}"
        )

    workspace_root = generated_dir.parent.parent
    raw_inputs = manifest.get("raw_inputs") or manifest.get("input_sources") or []
    raw_checked = 0
    for item in raw_inputs:
        if not isinstance(item, dict):
            raise BundleIntegrityError("manifest.raw_inputs contains a non-object entry")
        relative = Path(str(item.get("path", "")))
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            raise BundleIntegrityError(f"Unsafe raw input path: {relative}")
        path = (workspace_root / relative).resolve()
        try:
            path.relative_to(workspace_root)
        except ValueError as exc:
            raise BundleIntegrityError(f"Raw input escapes workspace: {relative}") from exc
        if not path.is_file():
            raise BundleIntegrityError(f"Missing raw input: {relative}")
        expected_bytes = int(item.get("bytes", -1))
        if path.stat().st_size != expected_bytes:
            raise BundleIntegrityError(f"Raw input byte-count mismatch: {relative}")
        if sha256_file(path) != str(item.get("sha256", "")):
            raise BundleIntegrityError(f"Raw input SHA-256 mismatch: {relative}")
        raw_checked += 1

    return BundleIntegrityResult(
        bundle_version=str(manifest.get("bundle_version", "unknown")),
        manifest_sha256=manifest_hash,
        files_checked=len(declared_files),
        raw_inputs_checked=raw_checked,
        exact_file_set=True,
    )
