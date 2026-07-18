"""Run the complete HERA golden-set and conversation evaluation.

The evaluator deliberately uses only the public ``POST /api/v1/chat`` contract.
It can target a deployed API or the FastAPI application in-process.  A report is
written only after the loader has proved that all 100 golden cases and all 24
conversation scenarios are present and match the generated-data manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

EVALUATION_BATCHES = range(18, 23)
CONVERSATION_BATCHES = range(16, 18)
EXPECTED_EVALUATION_CASES = 100
EXPECTED_CONVERSATION_SCENARIOS = 24
CHAT_PATH = "/api/v1/chat"
LLM_MODEL = "gpt-oss-120b"
EMBEDDING_MODEL = "Vietnamese_Embedding"
EMBEDDING_DIMENSIONS = 1024
FACT_CHUNK_PATTERN = re.compile(r"^CHUNK-(FACT-.+?)-\d+$")
FACTUAL_RESPONSE_TYPES = {
    "grounded_answer",
    "structured_action",
    "emergency_handoff",
}


class DatasetValidationError(RuntimeError):
    """Raised before evaluation when the golden dataset is incomplete/invalid."""


class EvaluationClient(Protocol):
    """Small interface shared by HTTP, in-process, and unit-test clients."""

    transport_name: str

    def send(
        self,
        message: str,
        *,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Send one public chat request and return the decoded response object."""

    def close(self) -> None:
        """Release any client resources."""


@dataclass(frozen=True)
class EvidenceCatalog:
    source_ids: frozenset[str]
    fact_ids: frozenset[str]
    record_ids: frozenset[str]


@dataclass(frozen=True)
class EvaluationDataset:
    manifest: dict[str, Any]
    manifest_sha256: str
    evaluation_cases: tuple[dict[str, Any], ...]
    conversation_scenarios: tuple[dict[str, Any], ...]
    evaluation_files: tuple[str, ...]
    conversation_files: tuple[str, ...]
    evidence_catalog: EvidenceCatalog


@dataclass
class SampleResult:
    sample_id: str
    sample_kind: str
    category: str
    passed: bool
    assertions: dict[str, bool | None]
    errors: list[str] = field(default_factory=list)


class HttpEvaluationClient:
    """Dependency-free JSON client for a running HERA deployment."""

    transport_name = "http"

    def __init__(self, base_url: str, *, timeout_seconds: float = 45.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def send(
        self,
        message: str,
        *,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "message": message,
            "locale": "vi-VN",
            "consent_to_store": False,
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        request = urllib.request.Request(
            f"{self.base_url}{CHAT_PATH}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 - operator-selected URL
                request,
                timeout=self.timeout_seconds,
            ) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"API returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"API request failed: {exc.reason}") from exc
        decoded = json.loads(body)
        if not isinstance(decoded, dict):
            raise RuntimeError("API response is not a JSON object")
        return decoded

    def close(self) -> None:
        return None


class InProcessEvaluationClient:
    """Call the FastAPI app in-process while preserving its public HTTP contract."""

    transport_name = "in_process"

    def __init__(self, repo_root: Path) -> None:
        backend_path = str(repo_root / "apps" / "backend")
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)
        from app.main import app
        from fastapi.testclient import TestClient

        self._client = TestClient(app)
        self._client.__enter__()

    def send(
        self,
        message: str,
        *,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "message": message,
            "locale": "vi-VN",
            "consent_to_store": False,
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id
        response = self._client.post(CHAT_PATH, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"API returned HTTP {response.status_code}")
        decoded = response.json()
        if not isinstance(decoded, dict):
            raise RuntimeError("API response is not a JSON object")
        return decoded

    def close(self) -> None:
        self._client.__exit__(None, None, None)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetValidationError(f"Cannot parse {path.name}: {exc}") from exc
    if not isinstance(decoded, dict):
        raise DatasetValidationError(f"{path.name} must contain a JSON object")
    return decoded


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _single_batch_file(data_dir: Path, prefix: int) -> Path:
    matches = sorted(data_dir.glob(f"{prefix:02d}-*.json"))
    if len(matches) != 1:
        raise DatasetValidationError(
            f"Expected exactly one {prefix:02d}-*.json file, found {len(matches)}"
        )
    return matches[0]


def _load_batches(
    data_dir: Path,
    prefixes: range,
    *,
    expected_records_per_batch: int,
) -> tuple[tuple[dict[str, Any], ...], tuple[str, ...]]:
    records: list[dict[str, Any]] = []
    names: list[str] = []
    for expected_batch, prefix in enumerate(prefixes, start=1):
        path = _single_batch_file(data_dir, prefix)
        document = _read_json(path)
        if document.get("batch_number") != expected_batch:
            raise DatasetValidationError(
                f"{path.name} has batch_number={document.get('batch_number')!r}; "
                f"expected {expected_batch}"
            )
        if document.get("batch_count") != len(prefixes):
            raise DatasetValidationError(
                f"{path.name} has batch_count={document.get('batch_count')!r}; "
                f"expected {len(prefixes)}"
            )
        if document.get("runtime_knowledge_eligible") is not False:
            raise DatasetValidationError(
                f"{path.name} must be marked runtime_knowledge_eligible=false"
            )
        if document.get("production_eligible") is not False:
            raise DatasetValidationError(
                f"{path.name} must be marked production_eligible=false"
            )
        batch_records = document.get("records")
        if not isinstance(batch_records, list):
            raise DatasetValidationError(f"{path.name} records must be an array")
        if not all(isinstance(item, dict) for item in batch_records):
            raise DatasetValidationError(f"{path.name} contains a non-object record")
        if len(batch_records) != expected_records_per_batch:
            raise DatasetValidationError(
                f"{path.name} must contain exactly "
                f"{expected_records_per_batch} records"
            )
        records.extend(batch_records)
        names.append(path.name)
    return tuple(records), tuple(names)


def _validate_manifest_files(
    data_dir: Path,
    manifest: dict[str, Any],
    selected_names: tuple[str, ...],
) -> None:
    entries = {
        item.get("file"): item
        for item in manifest.get("files", [])
        if isinstance(item, dict) and isinstance(item.get("file"), str)
    }
    declared_test_files = set(manifest.get("test_only_files", []))
    for name in selected_names:
        entry = entries.get(name)
        if entry is None:
            raise DatasetValidationError(f"{name} is not declared in manifest.files")
        if name not in declared_test_files:
            raise DatasetValidationError(f"{name} is not declared test-only")
        path = data_dir / name
        actual_bytes = path.stat().st_size
        actual_hash = _sha256(path)
        if entry.get("bytes") != actual_bytes:
            raise DatasetValidationError(f"Manifest byte count mismatch for {name}")
        if entry.get("sha256") != actual_hash:
            raise DatasetValidationError(f"Manifest SHA-256 mismatch for {name}")


def _collect_ids(value: Any, catalog: dict[str, set[str]], key: str = "") -> None:
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _collect_ids(child_value, catalog, child_key)
        return
    if isinstance(value, list):
        for child in value:
            _collect_ids(child, catalog, key)
        return
    if not isinstance(value, str):
        return
    if key == "source_id":
        catalog["sources"].add(value)
    if key == "fact_id":
        catalog["facts"].add(value)
    if key.endswith("_id") or key.endswith("_ids"):
        catalog["records"].add(value)


def _build_evidence_catalog(data_dir: Path) -> EvidenceCatalog:
    mutable: dict[str, set[str]] = {
        "sources": set(),
        "facts": set(),
        "records": set(),
    }
    for prefix in range(1, 13):
        document = _read_json(_single_batch_file(data_dir, prefix))
        _collect_ids(document, mutable)
    mutable["records"].update(mutable["sources"])
    mutable["records"].update(mutable["facts"])
    return EvidenceCatalog(
        source_ids=frozenset(mutable["sources"]),
        fact_ids=frozenset(mutable["facts"]),
        record_ids=frozenset(mutable["records"]),
    )


def load_evaluation_dataset(data_dir: Path) -> EvaluationDataset:
    """Load and strictly validate the complete release evaluation dataset."""

    data_dir = data_dir.resolve()
    manifest_path = data_dir / "00-manifest.json"
    manifest = _read_json(manifest_path)
    cases, case_files = _load_batches(
        data_dir,
        EVALUATION_BATCHES,
        expected_records_per_batch=20,
    )
    scenarios, scenario_files = _load_batches(
        data_dir,
        CONVERSATION_BATCHES,
        expected_records_per_batch=12,
    )

    if len(cases) != EXPECTED_EVALUATION_CASES:
        raise DatasetValidationError(
            f"Expected {EXPECTED_EVALUATION_CASES} evaluation cases, found {len(cases)}"
        )
    if len(scenarios) != EXPECTED_CONVERSATION_SCENARIOS:
        raise DatasetValidationError(
            "Expected "
            f"{EXPECTED_CONVERSATION_SCENARIOS} conversation scenarios, "
            f"found {len(scenarios)}"
        )

    expected_case_ids = {f"EVAL-{number:04d}" for number in range(1, 101)}
    actual_case_ids = [item.get("case_id") for item in cases]
    if len(set(actual_case_ids)) != len(actual_case_ids):
        raise DatasetValidationError("Duplicate evaluation case_id detected")
    if set(actual_case_ids) != expected_case_ids:
        raise DatasetValidationError("Evaluation case IDs are not EVAL-0001..EVAL-0100")

    expected_scenario_ids = {f"SYN-CONV-{number:03d}" for number in range(1, 25)}
    actual_scenario_ids = [item.get("scenario_id") for item in scenarios]
    if len(set(actual_scenario_ids)) != len(actual_scenario_ids):
        raise DatasetValidationError("Duplicate conversation scenario_id detected")
    if set(actual_scenario_ids) != expected_scenario_ids:
        raise DatasetValidationError(
            "Conversation IDs are not SYN-CONV-001..SYN-CONV-024"
        )

    counts = manifest.get("counts", {})
    if counts.get("evaluation_cases") != EXPECTED_EVALUATION_CASES:
        raise DatasetValidationError("Manifest evaluation_cases count is not 100")
    if counts.get("conversation_scenarios") != EXPECTED_CONVERSATION_SCENARIOS:
        raise DatasetValidationError("Manifest conversation_scenarios count is not 24")
    selected = (*scenario_files, *case_files)
    _validate_manifest_files(data_dir, manifest, selected)

    return EvaluationDataset(
        manifest=manifest,
        manifest_sha256=_sha256(manifest_path),
        evaluation_cases=cases,
        conversation_scenarios=scenarios,
        evaluation_files=case_files,
        conversation_files=scenario_files,
        evidence_catalog=_build_evidence_catalog(data_dir),
    )


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).casefold()
    return " ".join(text.split())


def _as_ids(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {item for item in value.split() if item}
    if isinstance(value, list):
        return {str(item) for item in value if item}
    return {str(value)}


def _response_text(response: dict[str, Any]) -> str:
    return str(response.get("answer_vi") or response.get("response") or "")


def _response_evidence(
    response: dict[str, Any],
) -> tuple[set[str], set[str], set[str]]:
    """Return citation source IDs, fact IDs, and structured record IDs."""

    source_ids = {
        str(item["source_id"])
        for item in response.get("citations", [])
        if isinstance(item, dict) and item.get("source_id")
    }
    raw_records = _as_ids(response.get("structured_record_ids"))
    explicit_facts = _as_ids(response.get("source_fact_ids"))
    metadata = response.get("metadata")
    if isinstance(metadata, dict):
        explicit_facts.update(_as_ids(metadata.get("fact_ids")))
        explicit_facts.update(_as_ids(metadata.get("source_fact_ids")))

    structured_records: set[str] = set()
    for record_id in raw_records:
        match = FACT_CHUNK_PATTERN.match(record_id)
        if match:
            explicit_facts.add(match.group(1))
        elif record_id.startswith("FACT-"):
            explicit_facts.add(record_id)
        else:
            structured_records.add(record_id)
    return source_ids, explicit_facts, structured_records


def _identifier_resolves(identifier: str, catalog: EvidenceCatalog) -> bool:
    if identifier in catalog.record_ids:
        return True
    match = FACT_CHUNK_PATTERN.match(identifier)
    return bool(match and match.group(1) in catalog.fact_ids)


def _base_assertions() -> dict[str, bool | None]:
    return {
        "api_contract": False,
        "intent": None,
        "response_type": False,
        "required_includes": None,
        "forbidden_claims": None,
        "required_fact_ids": None,
        "required_structured_record_ids": None,
        "allowed_evidence": None,
        "citation_record_resolution": False,
        "handoff": None,
    }


def _append_assertion(
    assertions: dict[str, bool | None],
    errors: list[str],
    name: str,
    passed: bool,
    error: str,
) -> None:
    assertions[name] = passed
    if not passed:
        errors.append(error)


def evaluate_case(
    case: dict[str, Any],
    response: dict[str, Any],
    catalog: EvidenceCatalog,
) -> SampleResult:
    """Apply deterministic golden assertions to one API response."""

    assertions = _base_assertions()
    errors: list[str] = []
    required_contract = {
        "intent",
        "response_type",
        "citations",
        "structured_record_ids",
        "requires_handoff",
    }
    _append_assertion(
        assertions,
        errors,
        "api_contract",
        required_contract.issubset(response),
        "api_contract_missing_fields",
    )

    expected_intent = str(case.get("expected_intent", ""))
    _append_assertion(
        assertions,
        errors,
        "intent",
        response.get("intent") == expected_intent,
        f"intent_expected:{expected_intent}",
    )
    expected_type = str(case.get("expected_response_type", ""))
    _append_assertion(
        assertions,
        errors,
        "response_type",
        response.get("response_type") == expected_type,
        f"response_type_expected:{expected_type}",
    )

    normalized_answer = _normalize_text(_response_text(response))
    required_includes = [_normalize_text(item) for item in case.get("must_include", [])]
    missing_includes = [
        item for item in required_includes if item not in normalized_answer
    ]
    _append_assertion(
        assertions,
        errors,
        "required_includes",
        not missing_includes,
        "missing_required_include:" + "|".join(missing_includes),
    )
    forbidden = [_normalize_text(item) for item in case.get("must_not_include", [])]
    found_forbidden = [item for item in forbidden if item in normalized_answer]
    _append_assertion(
        assertions,
        errors,
        "forbidden_claims",
        not found_forbidden,
        "forbidden_claim_present:" + "|".join(found_forbidden),
    )

    source_ids, fact_ids, record_ids = _response_evidence(response)
    required_facts = _as_ids(case.get("required_source_fact_ids"))
    required_records = _as_ids(case.get("required_structured_record_ids"))
    missing_facts = sorted(required_facts - fact_ids)
    missing_records = sorted(required_records - record_ids)
    _append_assertion(
        assertions,
        errors,
        "required_fact_ids",
        not missing_facts,
        "missing_required_fact_ids:" + "|".join(missing_facts),
    )
    _append_assertion(
        assertions,
        errors,
        "required_structured_record_ids",
        not missing_records,
        "missing_required_record_ids:" + "|".join(missing_records),
    )

    allowed_facts = _as_ids(case.get("allowed_fact_ids"))
    allowed_records = _as_ids(case.get("allowed_structured_record_selectors"))
    unexpected_facts = sorted(fact_ids - allowed_facts) if allowed_facts else []
    unexpected_records = sorted(record_ids - allowed_records) if allowed_records else []
    _append_assertion(
        assertions,
        errors,
        "allowed_evidence",
        not unexpected_facts and not unexpected_records,
        "unexpected_evidence:" + "|".join([*unexpected_facts, *unexpected_records]),
    )

    unresolved = sorted(
        identifier
        for identifier in (*source_ids, *fact_ids, *record_ids)
        if not _identifier_resolves(identifier, catalog)
    )
    _append_assertion(
        assertions,
        errors,
        "citation_record_resolution",
        not unresolved,
        "unresolved_evidence_ids:" + "|".join(unresolved),
    )

    if expected_type in {"refusal_and_handoff", "emergency_handoff"}:
        _append_assertion(
            assertions,
            errors,
            "handoff",
            response.get("requires_handoff") is True,
            "requires_handoff_expected:true",
        )

    return SampleResult(
        sample_id=str(case.get("case_id")),
        sample_kind="evaluation_case",
        category=str(case.get("category", "unknown")),
        passed=not errors,
        assertions=assertions,
        errors=errors,
    )


def _api_failure(
    sample_id: str, kind: str, category: str, exc: Exception
) -> SampleResult:
    assertions = _base_assertions()
    return SampleResult(
        sample_id=sample_id,
        sample_kind=kind,
        category=category,
        passed=False,
        assertions=assertions,
        errors=[f"api_error:{type(exc).__name__}"],
    )


def run_evaluation_cases(
    cases: tuple[dict[str, Any], ...],
    client: EvaluationClient,
    catalog: EvidenceCatalog,
) -> list[SampleResult]:
    results: list[SampleResult] = []
    for case in cases:
        try:
            response = client.send(str(case.get("query", "")))
            results.append(evaluate_case(case, response, catalog))
        except Exception as exc:  # keep running so the report lists every failure
            results.append(
                _api_failure(
                    str(case.get("case_id")),
                    "evaluation_case",
                    str(case.get("category", "unknown")),
                    exc,
                )
            )
    return results


def _conversation_pairs(scenario: dict[str, Any]) -> list[tuple[dict, dict]]:
    turns = scenario.get("turns")
    if not isinstance(turns, list) or len(turns) < 2 or len(turns) % 2:
        raise DatasetValidationError(
            f"{scenario.get('scenario_id')} must contain user/assistant pairs"
        )
    pairs: list[tuple[dict, dict]] = []
    for index in range(0, len(turns), 2):
        user_turn = turns[index]
        assistant_turn = turns[index + 1]
        if not isinstance(user_turn, dict) or not isinstance(assistant_turn, dict):
            raise DatasetValidationError(
                f"{scenario.get('scenario_id')} contains a non-object turn"
            )
        if user_turn.get("role") != "user" or assistant_turn.get("role") != "assistant":
            raise DatasetValidationError(
                f"{scenario.get('scenario_id')} turns must alternate user/assistant"
            )
        pairs.append((user_turn, assistant_turn))
    return pairs


def evaluate_conversation(
    scenario: dict[str, Any],
    client: EvaluationClient,
    catalog: EvidenceCatalog,
) -> SampleResult:
    scenario_id = str(scenario.get("scenario_id"))
    category = str(scenario.get("category", "unknown"))
    assertions = _base_assertions()
    assertions["intent"] = None
    assertions["required_includes"] = None
    assertions["forbidden_claims"] = None
    errors: list[str] = []
    conversation_id: str | None = None
    final_response_type: str | None = None
    all_contract = True
    all_types = True
    all_facts = True
    all_records = True
    all_resolved = True
    all_handoffs = True

    try:
        pairs = _conversation_pairs(scenario)
        for turn_number, (user_turn, expected_turn) in enumerate(pairs, start=1):
            response = client.send(
                str(user_turn.get("content", "")),
                conversation_id=conversation_id,
            )
            required_fields = {
                "conversation_id",
                "response_type",
                "citations",
                "structured_record_ids",
            }
            if not required_fields.issubset(response):
                all_contract = False
                errors.append(f"turn_{turn_number}:api_contract_missing_fields")
            returned_id = response.get("conversation_id")
            if not isinstance(returned_id, str) or len(returned_id) < 16:
                all_contract = False
                errors.append(f"turn_{turn_number}:invalid_conversation_id")
            elif conversation_id is not None and returned_id != conversation_id:
                all_contract = False
                errors.append(f"turn_{turn_number}:conversation_id_changed")
            conversation_id = (
                returned_id if isinstance(returned_id, str) else conversation_id
            )

            expected_type = str(
                expected_turn.get("expected_response_type")
                or user_turn.get("expected_response_type")
                or ""
            )
            final_response_type = str(response.get("response_type", ""))
            if final_response_type != expected_type:
                all_types = False
                errors.append(
                    f"turn_{turn_number}:response_type_expected:{expected_type}"
                )
            if (
                expected_type in {"refusal_and_handoff", "emergency_handoff"}
                and response.get("requires_handoff") is not True
            ):
                all_handoffs = False
                errors.append(f"turn_{turn_number}:requires_handoff_expected:true")

            source_ids, fact_ids, record_ids = _response_evidence(response)
            required_facts = _as_ids(expected_turn.get("source_fact_ids"))
            required_records = _as_ids(expected_turn.get("structured_record_ids"))
            missing_facts = sorted(required_facts - fact_ids)
            missing_records = sorted(required_records - record_ids)
            if missing_facts:
                all_facts = False
                errors.append(
                    f"turn_{turn_number}:missing_required_fact_ids:"
                    + "|".join(missing_facts)
                )
            if missing_records:
                all_records = False
                errors.append(
                    f"turn_{turn_number}:missing_required_record_ids:"
                    + "|".join(missing_records)
                )
            unresolved = sorted(
                identifier
                for identifier in (*source_ids, *fact_ids, *record_ids)
                if not _identifier_resolves(identifier, catalog)
            )
            if unresolved:
                all_resolved = False
                errors.append(
                    f"turn_{turn_number}:unresolved_evidence_ids:"
                    + "|".join(unresolved)
                )
    except Exception as exc:
        errors.append(f"api_error:{type(exc).__name__}")
        all_contract = False

    assertions["api_contract"] = all_contract
    assertions["response_type"] = all_types
    assertions["required_fact_ids"] = all_facts
    assertions["required_structured_record_ids"] = all_records
    assertions["allowed_evidence"] = None
    assertions["citation_record_resolution"] = all_resolved
    assertions["handoff"] = all_handoffs
    terminal = str(scenario.get("expected_terminal_state", ""))
    terminal_ok = final_response_type == terminal
    assertions["terminal_state"] = terminal_ok
    if not terminal_ok:
        errors.append(f"terminal_state_expected:{terminal}")

    return SampleResult(
        sample_id=scenario_id,
        sample_kind="conversation_scenario",
        category=category,
        passed=not errors,
        assertions=assertions,
        errors=errors,
    )


def run_conversations(
    scenarios: tuple[dict[str, Any], ...],
    client: EvaluationClient,
    catalog: EvidenceCatalog,
) -> list[SampleResult]:
    return [evaluate_conversation(item, client, catalog) for item in scenarios]


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def _assertion_metric(
    results: list[SampleResult],
    assertion: str,
) -> dict[str, Any]:
    eligible = [item for item in results if item.assertions.get(assertion) is not None]
    passed = sum(item.assertions.get(assertion) is True for item in eligible)
    return {
        "passed": passed,
        "sample_count": len(eligible),
        "rate": _ratio(passed, len(eligible)),
    }


def _git_metadata(repo_root: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "-C", str(repo_root), "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return {"commit": commit, "dirty_worktree": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": "unknown", "dirty_worktree": None}


def build_report(
    dataset: EvaluationDataset,
    case_results: list[SampleResult],
    conversation_results: list[SampleResult],
    *,
    repo_root: Path,
    transport: str,
    base_url: str | None,
) -> dict[str, Any]:
    """Build a release-auditable report without storing prompts or raw PII."""

    all_results = [*case_results, *conversation_results]
    case_passed = sum(item.passed for item in case_results)
    conversation_passed = sum(item.passed for item in conversation_results)
    failures = [
        {
            "sample_id": item.sample_id,
            "sample_kind": item.sample_kind,
            "category": item.category,
            "errors": item.errors,
        }
        for item in all_results
        if not item.passed
    ]

    emergency = [item for item in case_results if item.category == "emergency_positive"]
    emergency_passed = sum(
        item.assertions.get("intent") is True
        and item.assertions.get("response_type") is True
        for item in emergency
    )
    factual = [
        (case, result)
        for case, result in zip(dataset.evaluation_cases, case_results, strict=False)
        if case.get("expected_response_type") in FACTUAL_RESPONSE_TYPES
    ]
    factual_evidence_passed = sum(
        result.assertions.get("citation_record_resolution") is True
        and result.assertions.get("required_fact_ids") is True
        and result.assertions.get("required_structured_record_ids") is True
        for _, result in factual
    )
    intent_metric = _assertion_metric(case_results, "intent")
    forbidden_results = [
        result
        for case, result in zip(dataset.evaluation_cases, case_results, strict=False)
        if case.get("must_not_include")
    ]
    forbidden_metric = _assertion_metric(forbidden_results, "forbidden_claims")
    current_price_results = [
        result for result in case_results if "price" in result.category
    ]
    bhyt_results = [result for result in case_results if "bhyt" in result.category]
    schedule_results = [
        result for result in case_results if "schedule" in result.category
    ]

    def category_gate(results: list[SampleResult]) -> dict[str, Any]:
        passed = sum(item.passed for item in results)
        return {
            "passed": passed,
            "sample_count": len(results),
            "rate": _ratio(passed, len(results)),
            "target": 1.0,
            "gate_passed": bool(results) and passed == len(results),
        }

    complete = (
        len(case_results) == EXPECTED_EVALUATION_CASES
        and len(conversation_results) == EXPECTED_CONVERSATION_SCENARIOS
    )
    automated_passed = complete and all(item.passed for item in all_results)
    review_statuses = Counter(
        str(item.get("review_status", "unspecified"))
        for item in dataset.evaluation_cases
    )

    report = {
        "report_schema_version": "1.0.0",
        "generated_at": datetime.now(UTC).isoformat(),
        **_git_metadata(repo_root),
        "manifest": {
            "bundle_name": dataset.manifest.get("bundle_name"),
            "bundle_version": dataset.manifest.get("bundle_version"),
            "sha256": dataset.manifest_sha256,
        },
        "configuration": {
            "llm": {
                "provider": "fpt_openai_compatible",
                "model": LLM_MODEL,
            },
            "embedding": {
                "provider": "fpt_openai_compatible",
                "model": EMBEDDING_MODEL,
                "dimensions": EMBEDDING_DIMENSIONS,
            },
            "transport": transport,
            "base_url": base_url,
        },
        "dataset": {
            "complete": complete,
            "evaluation_files": list(dataset.evaluation_files),
            "conversation_files": list(dataset.conversation_files),
            "evaluation_case_count": len(case_results),
            "conversation_scenario_count": len(conversation_results),
            "total_sample_count": len(all_results),
            "human_review_statuses": dict(sorted(review_statuses.items())),
        },
        "summary": {
            "automated_passed": automated_passed,
            "human_rubric_status": "pending_human_review",
            "evaluation_cases": {
                "sample_count": len(case_results),
                "passed": case_passed,
                "failed": len(case_results) - case_passed,
                "pass_rate": _ratio(case_passed, len(case_results)),
            },
            "conversation_scenarios": {
                "sample_count": len(conversation_results),
                "passed": conversation_passed,
                "failed": len(conversation_results) - conversation_passed,
                "pass_rate": _ratio(
                    conversation_passed,
                    len(conversation_results),
                ),
            },
            "total_sample_count": len(all_results),
            "failure_count": len(failures),
        },
        "release_gates": {
            "emergency_recall": {
                "passed": emergency_passed,
                "sample_count": len(emergency),
                "rate": _ratio(emergency_passed, len(emergency)),
                "target": 1.0,
                "gate_passed": emergency_passed == len(emergency),
            },
            "intent_accuracy": {
                **intent_metric,
                "target": 0.9,
                "gate_passed": bool(
                    intent_metric["rate"] is not None and intent_metric["rate"] >= 0.9
                ),
            },
            "forbidden_claim_avoidance": {
                **forbidden_metric,
                "target": 1.0,
                "gate_passed": forbidden_metric["passed"]
                == forbidden_metric["sample_count"],
            },
            "current_price_leakage": category_gate(current_price_results),
            "bhyt_scope_confusion": category_gate(bhyt_results),
            "schedule_as_availability_claim": category_gate(schedule_results),
            "citation_record_resolution": {
                "passed": factual_evidence_passed,
                "sample_count": len(factual),
                "rate": _ratio(factual_evidence_passed, len(factual)),
                "target": 1.0,
                "gate_passed": factual_evidence_passed == len(factual),
            },
            "helpful_answer_human_rubric": {
                "rate": None,
                "target": 0.85,
                "gate_passed": None,
                "status": "requires_human_review",
            },
            "booking_over_threshold": {
                "rate": None,
                "target": 1.0,
                "gate_passed": None,
                "status": "covered_by_separate_booking_concurrency_test",
            },
        },
        "failures": failures,
        "results": [asdict(item) for item in all_results],
    }
    return report


def write_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(output_path)


def _default_paths() -> tuple[Path, Path]:
    repo_root = Path(__file__).resolve().parents[1]
    data_dir = repo_root / "data" / "generated"
    return repo_root, data_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    repo_root, data_dir = _default_paths()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=data_dir)
    parser.add_argument(
        "--output",
        type=Path,
        default=repo_root / "artifacts" / "evaluation-report.json",
    )
    transport = parser.add_mutually_exclusive_group()
    transport.add_argument(
        "--base-url",
        default=None,
        help="Running HERA origin, for example http://127.0.0.1:8000",
    )
    transport.add_argument(
        "--in-process",
        action="store_true",
        help="Call the FastAPI app through TestClient (may call configured models)",
    )
    parser.add_argument("--timeout", type=float, default=45.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root, _ = _default_paths()
    try:
        dataset = load_evaluation_dataset(args.data_dir)
    except DatasetValidationError as exc:
        print(f"Dataset validation failed: {exc}", file=sys.stderr)
        return 2

    base_url = args.base_url or os.getenv("HERA_BASE_URL")
    if args.in_process:
        client: EvaluationClient = InProcessEvaluationClient(repo_root)
        report_base_url = None
    else:
        base_url = base_url or "http://127.0.0.1:8000"
        client = HttpEvaluationClient(base_url, timeout_seconds=args.timeout)
        report_base_url = base_url

    try:
        case_results = run_evaluation_cases(
            dataset.evaluation_cases,
            client,
            dataset.evidence_catalog,
        )
        conversation_results = run_conversations(
            dataset.conversation_scenarios,
            client,
            dataset.evidence_catalog,
        )
    finally:
        client.close()

    report = build_report(
        dataset,
        case_results,
        conversation_results,
        repo_root=repo_root,
        transport=client.transport_name,
        base_url=report_base_url,
    )
    write_report(report, args.output)
    summary = report["summary"]
    print(
        "Evaluation finished: "
        f"{summary['total_sample_count']} samples, "
        f"{summary['failure_count']} failures. Report: {args.output}"
    )
    return 0 if summary["automated_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
