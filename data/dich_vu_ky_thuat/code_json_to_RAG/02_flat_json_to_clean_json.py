#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1]
DEFAULT_FLAT_JSON = DEFAULT_DATA_DIR / "gia_dich_vu_ky_thuat_2025_flat.json"
DEFAULT_CLEAN_JSON = DEFAULT_DATA_DIR / "gia_dich_vu_ky_thuat_2025_clean.json"
DEFAULT_COMPAT_JSON = DEFAULT_DATA_DIR / "gia_dich_vu_ky_thuat_2025.json"
DEFAULT_SUMMARY = DEFAULT_DATA_DIR / "clean_json_summary.json"


def clean_text(value: Any, single_line: bool = False) -> str:
    if value is None:
        return ""
    text = str(value).replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if single_line:
        text = re.sub(r"\s+", " ", text).strip()
    return text


def stt_parent(value: str) -> str:
    match = re.fullmatch(r"(\d+)[,.]\d+", clean_text(value, single_line=True))
    return match.group(1) if match else ""


def stt_sort_key(value: str) -> list[int]:
    parts = re.split(r"[,.]", clean_text(value, single_line=True))
    key = []
    for part in parts:
        key.append(int(part) if part.isdigit() else 0)
    return key


def price_to_int(value: str) -> int | None:
    value = clean_text(value, single_line=True)
    if not value:
        return None
    if not re.fullmatch(r"\d{1,3}(?:\.\d{3})+", value):
        raise ValueError(f"Invalid price format: {value}")
    return int(value.replace(".", ""))


def compact_id_part(value: str) -> str:
    value = clean_text(value, single_line=True).lower()
    value = value.replace(",", "_").replace(".", "_")
    value = re.sub(r"[^a-z0-9_]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_")


def service_id(section: str, stt: str, code: str) -> str:
    section_slug = compact_id_part(section)[:80]
    stt_slug = compact_id_part(stt)
    code_slug = compact_id_part(code) if code else "no_code"
    return f"hht_2025__{section_slug}__stt_{stt_slug}__{code_slug}"


def combine_parent_child_name(parent_name: str, child_name: str) -> str:
    parent_name = clean_text(parent_name, single_line=True)
    child_name = clean_text(child_name, single_line=True)
    if not parent_name:
        return child_name
    if not child_name:
        return parent_name
    if parent_name.endswith(":"):
        return f"{parent_name} {child_name}"
    return f"{parent_name} - {child_name}"


def normalize_record(raw: dict[str, Any]) -> dict[str, Any]:
    co_so_1 = clean_text(raw.get("co_so_1", ""), single_line=True)
    co_so_2 = clean_text(raw.get("co_so_2", ""), single_line=True)
    co_so_1_vnd = price_to_int(co_so_1)
    co_so_2_vnd = price_to_int(co_so_2)
    has_price = co_so_1_vnd is not None or co_so_2_vnd is not None

    section = clean_text(raw.get("section", ""), single_line=True)
    stt = clean_text(raw.get("stt", ""), single_line=True)
    code = clean_text(raw.get("ma_tuong_duong", ""), single_line=True)
    service_name = clean_text(raw.get("dich_vu_ky_thuat", ""))
    note = clean_text(raw.get("ghi_chu", ""))

    return {
        "id": service_id(section, stt, code),
        "page": int(clean_text(raw.get("page", "0"), single_line=True) or 0),
        "section": section,
        "stt": stt,
        "parent_stt": stt_parent(stt),
        "ma_tuong_duong": code,
        "service_name": service_name,
        "service_name_single_line": clean_text(service_name, single_line=True),
        "co_so_1": co_so_1,
        "co_so_1_vnd": co_so_1_vnd,
        "co_so_2": co_so_2,
        "co_so_2_vnd": co_so_2_vnd,
        "has_price": has_price,
        "availability": {
            "co_so_1": "published" if co_so_1_vnd is not None else "not_listed_in_source",
            "co_so_2": "published" if co_so_2_vnd is not None else "not_listed_in_source",
        },
        "ghi_chu": note,
        "ghi_chu_single_line": clean_text(note, single_line=True),
        "children": [],
    }


def attach_full_names(items: list[dict[str, Any]], parent_name: str = "") -> None:
    for item in items:
        item["parent_name"] = parent_name
        item["full_name"] = combine_parent_child_name(parent_name, item["service_name_single_line"])
        attach_full_names(item["children"], item["full_name"])
        item["item_type"] = "group" if item["children"] and not item["has_price"] else "service"


def build_hierarchy(flat_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    roots: list[dict[str, Any]] = []
    parents_by_section: dict[tuple[str, str], dict[str, Any]] = {}

    for raw in flat_records:
        item = normalize_record(raw)
        parent_key = (item["section"], item["parent_stt"])
        if item["parent_stt"] and parent_key in parents_by_section:
            parents_by_section[parent_key]["children"].append(item)
        else:
            roots.append(item)

        if re.fullmatch(r"\d+", item["stt"]):
            parents_by_section[(item["section"], item["stt"])] = item

    attach_full_names(roots)
    return roots


def flatten_tree(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for item in items:
        output.append(item)
        output.extend(flatten_tree(item["children"]))
    return output


def validate_clean(items: list[dict[str, Any]], flat_count: int) -> dict[str, Any]:
    all_items = flatten_tree(items)
    if len(all_items) != flat_count:
        raise ValueError(f"Tree item count {len(all_items)} does not match flat count {flat_count}")

    section_counts = Counter(item["section"] for item in all_items)
    child_count = sum(len(item["children"]) for item in all_items)
    group_count = sum(item["item_type"] == "group" for item in all_items)
    service_count = sum(item["item_type"] == "service" for item in all_items)
    price_format_errors = [
        item["id"]
        for item in all_items
        if (item["co_so_1"] and item["co_so_1_vnd"] is None) or (item["co_so_2"] and item["co_so_2_vnd"] is None)
    ]
    if price_format_errors:
        raise ValueError(f"Invalid prices in {len(price_format_errors)} items")

    return {
        "flat_record_count": flat_count,
        "tree_root_count": len(items),
        "tree_total_count": len(all_items),
        "tree_child_count": child_count,
        "group_count": group_count,
        "service_count": service_count,
        "section_counts": dict(section_counts),
    }


def convert_flat_to_clean(flat_json: Path, clean_json: Path, compat_json: Path | None, summary_path: Path) -> dict[str, Any]:
    flat_records = json.loads(flat_json.read_text(encoding="utf-8"))
    if not isinstance(flat_records, list):
        raise TypeError("Flat JSON must be a list of row objects")

    clean_tree = build_hierarchy(flat_records)
    summary = validate_clean(clean_tree, len(flat_records))
    summary["input"] = str(flat_json)
    summary["outputs"] = {"clean_json": str(clean_json)}
    clean_json.write_text(json.dumps(clean_tree, ensure_ascii=False, indent=2), encoding="utf-8")
    if compat_json is not None:
        compat_json.write_text(json.dumps(clean_tree, ensure_ascii=False, indent=2), encoding="utf-8")
        summary["outputs"]["compat_json"] = str(compat_json)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert flat service-price JSON to clean hierarchical JSON.")
    parser.add_argument("--flat-json", type=Path, default=DEFAULT_FLAT_JSON)
    parser.add_argument("--clean-json", type=Path, default=DEFAULT_CLEAN_JSON)
    parser.add_argument("--compat-json", type=Path, default=DEFAULT_COMPAT_JSON, help="Also write this compatibility JSON path. Use empty string to disable.")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    compat_json = None if str(args.compat_json) == "" else args.compat_json
    summary = convert_flat_to_clean(args.flat_json, args.clean_json, compat_json, args.summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
