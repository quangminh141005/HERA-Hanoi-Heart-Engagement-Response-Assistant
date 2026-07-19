#!/usr/bin/env python3
"""Run HERA's strongest local RAG accuracy audit and write a bug markdown.

The audit uses only the public chat API so it measures the same path the UI uses.
It combines:

* the 100-case golden evaluation plus 24 conversation scenarios;
* the first 500 hard RAG/structured cases;
* the disjoint second 500 harder RAG/structured cases.

The hard reports include full answers and are converted into ``thong_tin_sai.md``
so bad answers can be reviewed and fixed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8080"
GOLDEN_REPORT = REPO_ROOT / "reports" / "super-rag-golden-evaluation.json"
HARD_REPORT = REPO_ROOT / "reports" / "super-rag-hard-500.json"
HARDER_REPORT = REPO_ROOT / "reports" / "super-rag-harder-500.json"
SUMMARY_REPORT = REPO_ROOT / "reports" / "super-rag-accuracy-summary.json"
WRONG_INFO_MD = REPO_ROOT / "thong_tin_sai.md"


@dataclass(frozen=True)
class Suite:
    name: str
    report_path: Path
    command: list[str]
    required_to_pass: bool = True


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    reports_dir = REPO_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    suites = _build_suites(args)
    suite_results: list[dict[str, Any]] = []
    exit_code = 0
    for suite in suites:
        print(json.dumps({"event": "suite_start", "suite": suite.name}, ensure_ascii=False))
        completed = subprocess.run(
            suite.command,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if completed.stdout:
            print(completed.stdout, end="")
        report = _read_report_if_exists(suite.report_path)
        suite_result = {
            "suite": suite.name,
            "command": suite.command,
            "exit_code": completed.returncode,
            "report": str(suite.report_path.relative_to(REPO_ROOT)),
            "summary": _suite_summary(report),
        }
        suite_results.append(suite_result)
        print(json.dumps({"event": "suite_done", **suite_result}, ensure_ascii=False))
        if suite.required_to_pass and completed.returncode != 0:
            exit_code = 1

    summary = _build_summary(suite_results, args=args)
    SUMMARY_REPORT.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_wrong_info_markdown(summary, args=args)
    print(
        json.dumps(
            {
                "status": "done",
                "summary_report": str(SUMMARY_REPORT.relative_to(REPO_ROOT)),
                "wrong_info_markdown": str(WRONG_INFO_MD.relative_to(REPO_ROOT)),
                "exit_code": exit_code,
            },
            ensure_ascii=False,
        )
    )
    return exit_code


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--hard-limit",
        type=int,
        default=0,
        help="0 means run all 500 cases per hard fixture.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument("--skip-golden", action="store_true")
    parser.add_argument("--skip-hard", action="store_true")
    parser.add_argument("--skip-harder", action="store_true")
    parser.add_argument(
        "--live-judge",
        action="store_true",
        help="Also call the configured judge model for failed/hard cases.",
    )
    parser.add_argument(
        "--judge-all",
        action="store_true",
        help="With --live-judge, judge every hard case, not only failures/risky cases.",
    )
    return parser.parse_args(argv)


def _build_suites(args: argparse.Namespace) -> list[Suite]:
    python = sys.executable
    suites: list[Suite] = []
    if not args.skip_golden:
        suites.append(
            Suite(
                name="golden_100_plus_conversations",
                report_path=GOLDEN_REPORT,
                command=[
                    python,
                    "scripts/run_evaluation.py",
                    "--base-url",
                    args.base_url,
                    "--timeout",
                    str(args.timeout_seconds),
                    "--output",
                    str(GOLDEN_REPORT),
                ],
                required_to_pass=False,
            )
        )
    hard_limit = "500" if args.hard_limit == 0 else str(args.hard_limit)
    hard_base = [
        python,
        "scripts/hard_live_eval.py",
        "--confirm",
        "YES",
        "--base-url",
        args.base_url,
        "--limit",
        hard_limit,
        "--timeout-seconds",
        str(args.timeout_seconds),
        "--delay-seconds",
        str(args.delay_seconds),
    ]
    if args.live_judge:
        hard_base.append("--live-judge")
    if args.judge_all:
        hard_base.append("--judge-all")
    hard_case_file = "data/test-fixtures/24-hard-rag-evaluation-500.json"
    harder_case_file = "data/test-fixtures/25-harder-rag-evaluation-500.json"
    if args.hard_limit > 0:
        hard_case_file = str(
            _write_stratified_case_file(
                Path(hard_case_file),
                limit=args.hard_limit,
                output=REPO_ROOT / "reports" / "super-rag-hard-stratified.json",
            ).relative_to(REPO_ROOT)
        )
        harder_case_file = str(
            _write_stratified_case_file(
                Path(harder_case_file),
                limit=args.hard_limit,
                output=REPO_ROOT / "reports" / "super-rag-harder-stratified.json",
            ).relative_to(REPO_ROOT)
        )
    if not args.skip_hard:
        suites.append(
            Suite(
                name="hard_rag_500",
                report_path=HARD_REPORT,
                command=[
                    *hard_base,
                    "--case-file",
                    hard_case_file,
                    "--output",
                    str(HARD_REPORT),
                ],
            )
        )
    if not args.skip_harder:
        suites.append(
            Suite(
                name="harder_rag_500_disjoint",
                report_path=HARDER_REPORT,
                command=[
                    *hard_base,
                    "--case-file",
                    harder_case_file,
                    "--output",
                    str(HARDER_REPORT),
                ],
            )
        )
    return suites


def _write_stratified_case_file(path: Path, *, limit: int, output: Path) -> Path:
    source_path = path if path.is_absolute() else REPO_ROOT / path
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError(f"Case file has no records array: {source_path}")
    by_category: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        by_category.setdefault(str(record.get("category") or "uncategorized"), []).append(record)
    selected: list[dict[str, Any]] = []
    while len(selected) < limit and any(by_category.values()):
        for category in sorted(by_category):
            if by_category[category]:
                selected.append(by_category[category].pop(0))
                if len(selected) >= limit:
                    break
    sampled = dict(payload)
    sampled["case_count"] = len(selected)
    sampled["records"] = selected
    sampled["sampling"] = {
        "method": "round_robin_by_category",
        "source_file": str(path),
        "source_case_count": len(records),
        "limit": limit,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(sampled, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def _read_report_if_exists(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _suite_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return {}
    if "cases" in summary:
        return {
            "samples": summary.get("cases"),
            "passed": summary.get("passed"),
            "failed": summary.get("failed"),
            "pass_rate": summary.get("pass_rate"),
            "by_category": summary.get("by_category"),
            "live_judge": summary.get("live_judge"),
            "judge_pass_rate": summary.get("judge_pass_rate"),
            "judge_mean_score": summary.get("judge_mean_score"),
        }
    return {
        "samples": summary.get("total_sample_count"),
        "failed": summary.get("failure_count"),
        "automated_passed": summary.get("automated_passed"),
        "evaluation_cases": summary.get("evaluation_cases"),
        "conversation_scenarios": summary.get("conversation_scenarios"),
    }


def _build_summary(
    suite_results: list[dict[str, Any]],
    *,
    args: argparse.Namespace,
) -> dict[str, Any]:
    reports = {
        name: _read_report_if_exists(path)
        for name, path in {
            "golden": GOLDEN_REPORT,
            "hard": HARD_REPORT,
            "harder": HARDER_REPORT,
        }.items()
    }
    hard_failures = []
    for suite_name in ("hard", "harder"):
        report = reports[suite_name]
        for failure in report.get("failures", []) if isinstance(report, dict) else []:
            if isinstance(failure, dict):
                hard_failures.append({"suite": suite_name, **failure})
    golden_failures = []
    golden_report = reports["golden"]
    for failure in golden_report.get("failures", []) if isinstance(golden_report, dict) else []:
        if isinstance(failure, dict):
            golden_failures.append({"suite": "golden", **failure})

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": args.base_url,
        "hard_limit_per_fixture": 500 if args.hard_limit == 0 else args.hard_limit,
        "suite_results": suite_results,
        "reports": {
            "golden": str(GOLDEN_REPORT.relative_to(REPO_ROOT)),
            "hard": str(HARD_REPORT.relative_to(REPO_ROOT)),
            "harder": str(HARDER_REPORT.relative_to(REPO_ROOT)),
        },
        "failure_counts": {
            "golden": len(golden_failures),
            "hard_plus_harder": len(hard_failures),
            "total": len(golden_failures) + len(hard_failures),
        },
        "golden_failures": golden_failures,
        "hard_failures": hard_failures,
    }


def _write_wrong_info_markdown(summary: dict[str, Any], *, args: argparse.Namespace) -> None:
    hard_failures = summary.get("hard_failures", [])
    golden_failures = summary.get("golden_failures", [])
    lines = [
        "# Thông tin sai / case cần sửa",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Base URL: `{args.base_url}`",
        f"- Hard limit per fixture: `{summary['hard_limit_per_fixture']}`",
        f"- Tổng failure: `{summary['failure_counts']['total']}`",
        "",
        "## Summary",
        "",
    ]
    for suite in summary.get("suite_results", []):
        suite_summary = suite.get("summary") or {}
        lines.append(
            f"- `{suite.get('suite')}`: exit `{suite.get('exit_code')}`, "
            f"samples `{suite_summary.get('samples')}`, "
            f"failed `{suite_summary.get('failed')}`, "
            f"pass_rate `{suite_summary.get('pass_rate')}`"
        )

    lines.extend(["", "## Hard/Harder failures có câu trả lời", ""])
    if not hard_failures:
        lines.append("Không có failure hard/harder theo assertion tự động.")
    for index, failure in enumerate(hard_failures, 1):
        lines.extend(_format_hard_failure(index, failure))

    lines.extend(["", "## Golden/conversation failures", ""])
    if not golden_failures:
        lines.append("Không có failure golden/conversation.")
    for index, failure in enumerate(golden_failures, 1):
        lines.extend(
            [
                f"### G{index}. `{failure.get('sample_id')}`",
                "",
                f"- Suite: `{failure.get('suite')}`",
                f"- Kind: `{failure.get('sample_kind')}`",
                f"- Category: `{failure.get('category')}`",
                f"- Errors: `{failure.get('errors')}`",
                "",
            ]
        )

    WRONG_INFO_MD.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _format_hard_failure(index: int, failure: dict[str, Any]) -> list[str]:
    metadata = failure.get("metadata") if isinstance(failure.get("metadata"), dict) else {}
    judge = failure.get("judge")
    return [
        f"### H{index}. `{failure.get('case_id')}`",
        "",
        f"- Suite: `{failure.get('suite')}`",
        f"- Category: `{failure.get('category')}`",
        f"- Failures: `{failure.get('failures')}`",
        f"- Intent: `{failure.get('intent')}`",
        f"- Response type: `{failure.get('response_type')}`",
        f"- Decision/generation: `{_short_json(metadata)}`",
        f"- Judge: `{_short_json(judge)}`",
        "",
        "**Câu hỏi**",
        "",
        str(failure.get("message") or "").strip(),
        "",
        "**Câu trả lời thực tế**",
        "",
        str(failure.get("answer_vi") or failure.get("error") or "").strip(),
        "",
    ]


def _short_json(value: Any) -> str:
    if value is None:
        return ""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)[:600]
    except TypeError:
        return str(value)[:600]


if __name__ == "__main__":
    raise SystemExit(main())
