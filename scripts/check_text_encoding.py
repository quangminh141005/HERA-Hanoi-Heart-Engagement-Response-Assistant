"""Fail CI when source text is not UTF-8 or contains mojibake.

Vietnamese text in JSON, Markdown, Python and TypeScript is valid when files are
UTF-8. This script does not ban Vietnamese diacritics. It catches broken text
that was decoded or saved with the wrong codepage.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

TEXT_SUFFIXES = {
    "",
    ".conf",
    ".css",
    ".env",
    ".example",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

SKIP_DIR_NAMES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tmp",
    ".venv",
    "__pycache__",
    "artifacts",
    "backups",
    "data",
    "dist",
    "node_modules",
    "reports",
}

SKIP_PATH_PARTS = {
    ("apps", "backend", "data", "hera_postgres_seed.json.gz"),
    ("apps", "backend", "data", "hera_postgres_seed.json.gz.sha256"),
    ("apps", "frontend", "package-lock.json"),
    ("uv.lock",),
}

MOJIBAKE_MARKERS = (
    "\ufffd",
    "\u00c3",
    "\u00c4",
    "\u00c5",
    "\u00c6",
    "\u00d0",
    "\u00d1",
    "\u00e1\u00ba",
    "\u00e1\u00bb",
    "\u00c2 ",
    "\u00c2.",
    "\u00c2,",
    "\u00c2:",
    "\u00c2;",
    "\u00c2)",
    "\u00c2(",
)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = args.root.resolve()
    failures: list[str] = []
    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            failures.append(f"{path.relative_to(root)}: invalid UTF-8: {exc}")
            continue
        if "\r\n" in text:
            failures.append(f"{path.relative_to(root)}: CRLF line ending; use LF")
        for line_no, line in enumerate(text.splitlines(), 1):
            marker = _first_mojibake_marker(line)
            if marker is None:
                continue
            preview = line.strip()[:160]
            failures.append(
                f"{path.relative_to(root)}:{line_no}: possible mojibake "
                f"marker {marker!r}: {preview}"
            )
            break
    if failures:
        print("Text encoding check failed:", file=sys.stderr)
        for failure in failures[:80]:
            print(f"  - {failure}", file=sys.stderr)
        remaining = len(failures) - 80
        if remaining > 0:
            print(f"  ... {remaining} more", file=sys.stderr)
        return 1
    print("Text encoding check passed.")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to scan.",
    )
    return parser.parse_args(argv)


def _iter_text_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        relative_parts = path.relative_to(root).parts
        if any(part in SKIP_DIR_NAMES for part in relative_parts):
            continue
        if tuple(relative_parts) in SKIP_PATH_PARTS:
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {
            ".env.example",
            ".gitattributes",
            ".gitignore",
            "Dockerfile",
            "Makefile",
        }:
            yield path


def _first_mojibake_marker(line: str) -> str | None:
    for marker in MOJIBAKE_MARKERS:
        if marker in line:
            return marker
    return None


if __name__ == "__main__":
    raise SystemExit(main())
