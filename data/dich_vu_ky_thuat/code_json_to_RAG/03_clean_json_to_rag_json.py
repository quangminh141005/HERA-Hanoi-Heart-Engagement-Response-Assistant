#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CLEAN_JSON = DEFAULT_DATA_DIR / "gia_dich_vu_ky_thuat_2025_clean.json"
DEFAULT_RAG_JSONL = DEFAULT_DATA_DIR / "gia_dich_vu_ky_thuat_2025_rag.jsonl"
DEFAULT_RAG_JSON = DEFAULT_DATA_DIR / "gia_dich_vu_ky_thuat_2025_rag.json"
DEFAULT_SUMMARY = DEFAULT_DATA_DIR / "rag_json_summary.json"

SOURCE_URL = (
    "https://benhvientimhanoi.vn/vi/chi-tiet-lich-kham/bang-gia-dich-vu/"
    "gia-dich-vu-ky-thuat-ap-dung-tai-benh-vien-tim-ha-noi-2025"
)
PDF_FILE = "GiaDVBV_tim_HN.pdf"
LEGAL_BASIS = "Phụ lục số 06 Nghị quyết số 45/2024/NQ-HĐND ngày 10/12/2024 của Hội đồng nhân dân Thành phố Hà Nội"


def one_line(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def display_price(value: str | None, amount: int | None) -> str:
    if amount is None:
        return "không có giá được công bố trong bảng nguồn"
    return value or f"{amount:,}".replace(",", ".")


def sentence(value: str) -> str:
    value = one_line(value)
    if not value:
        return ""
    return value if value.endswith((".", "!", "?", ":", ";")) else f"{value}."


def price_status(amount: int | None) -> str:
    return "published" if amount is not None else "not_listed_in_source"


def flatten_tree(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for item in items:
        output.append(item)
        output.extend(flatten_tree(item.get("children", [])))
    return output


def child_price_line(child: dict[str, Any]) -> str:
    return (
        f"- STT {child['stt']}: {sentence(child['full_name'])} "
        f"Cơ sở 1: {display_price(child.get('co_so_1'), child.get('co_so_1_vnd'))}; "
        f"Cơ sở 2: {display_price(child.get('co_so_2'), child.get('co_so_2_vnd'))}."
        + (f" Ghi chú: {child['ghi_chu_single_line']}." if child.get("ghi_chu_single_line") else "")
    )


def canonical_answer(item: dict[str, Any]) -> str:
    if item.get("children") and item.get("item_type") == "group":
        child_lines = "\n".join(child_price_line(child) for child in item["children"])
        return (
            f"STT {item['stt']} - {item['full_name']} là mục nhóm, không có giá chung trong bảng nguồn. "
            f"Các giá nằm ở mục con:\n{child_lines}"
        )

    note = f" Ghi chú: {item['ghi_chu_single_line']}." if item.get("ghi_chu_single_line") else ""
    return (
        f"STT {item['stt']} - {sentence(item['full_name'])} "
        f"Cơ sở 1: {display_price(item.get('co_so_1'), item.get('co_so_1_vnd'))}; "
        f"Cơ sở 2: {display_price(item.get('co_so_2'), item.get('co_so_2_vnd'))}."
        f"{note}"
    )


def query_variants(item: dict[str, Any]) -> list[str]:
    variants = {
        one_line(item.get("service_name_single_line")),
        one_line(item.get("full_name")),
        f"giá {one_line(item.get('full_name'))}",
        f"bảng giá {one_line(item.get('full_name'))}",
        f"stt {item.get('stt')} {one_line(item.get('full_name'))}",
    }
    if item.get("ma_tuong_duong"):
        variants.add(item["ma_tuong_duong"])
        variants.add(f"mã {item['ma_tuong_duong']}")
        variants.add(f"giá mã {item['ma_tuong_duong']}")
    if item.get("parent_name"):
        variants.add(one_line(item["parent_name"]))
        variants.add(f"{one_line(item['parent_name'])} {one_line(item['service_name_single_line'])}")
    return sorted(v for v in variants if v)


def retrieval_text(item: dict[str, Any]) -> str:
    lines = [
        f"Nguồn: Bảng giá dịch vụ kỹ thuật áp dụng tại Bệnh viện Tim Hà Nội 2025.",
        f"Căn cứ: {LEGAL_BASIS}.",
        f"Phần: {item['section']}.",
        f"STT: {item['stt']}.",
        f"Tên dịch vụ đầy đủ: {item['full_name']}.",
    ]
    if item.get("parent_stt"):
        lines.append(f"Mục cha: STT {item['parent_stt']} - {item.get('parent_name', '')}.")
    if item.get("ma_tuong_duong"):
        lines.append(f"Mã tương đương: {item['ma_tuong_duong']}.")

    lines.extend([
        f"Loại bản ghi: {item['item_type']}.",
        f"Cơ sở 1: {display_price(item.get('co_so_1'), item.get('co_so_1_vnd'))}.",
        f"Cơ sở 2: {display_price(item.get('co_so_2'), item.get('co_so_2_vnd'))}.",
    ])
    if item.get("ghi_chu_single_line"):
        lines.append(f"Ghi chú: {item['ghi_chu_single_line']}.")
    if item.get("children") and item.get("item_type") == "group":
        lines.append("Mục này là mục nhóm, không được trả giá chung cho mục nhóm; phải dùng giá của các mục con.")
        lines.append("Các mục con:")
        lines.extend(child_price_line(child) for child in item["children"])
    lines.append(
        "Quy tắc trả lời: không tự suy luận giá; nếu một cơ sở trống thì nói không có giá được công bố trong bảng nguồn; "
        "không lấy giá của cơ sở này gán sang cơ sở khác."
    )
    return "\n".join(lines)


def make_rag_record(item: dict[str, Any]) -> dict[str, Any]:
    children = item.get("children", [])
    return {
        "rag_id": f"rag__{item['id']}",
        "document_type": "hospital_service_price",
        "source": {
            "hospital": "Bệnh viện Tim Hà Nội",
            "title": "Giá dịch vụ kỹ thuật áp dụng tại Bệnh viện Tim Hà Nội 2025",
            "url": SOURCE_URL,
            "pdf_file": PDF_FILE,
            "page": item["page"],
            "legal_basis": LEGAL_BASIS,
        },
        "metadata": {
            "id": item["id"],
            "section": item["section"],
            "stt": item["stt"],
            "parent_stt": item.get("parent_stt", ""),
            "parent_name": item.get("parent_name", ""),
            "ma_tuong_duong": item.get("ma_tuong_duong", ""),
            "item_type": item["item_type"],
            "has_price": item["has_price"],
            "child_count": len(children),
        },
        "service": {
            "name": item["service_name_single_line"],
            "full_name": item["full_name"],
            "note": item.get("ghi_chu_single_line", ""),
            "children": [
                {
                    "stt": child["stt"],
                    "name": child["service_name_single_line"],
                    "full_name": child["full_name"],
                    "co_so_1_vnd": child.get("co_so_1_vnd"),
                    "co_so_2_vnd": child.get("co_so_2_vnd"),
                    "note": child.get("ghi_chu_single_line", ""),
                }
                for child in children
            ],
        },
        "prices": {
            "co_so_1": {
                "display": display_price(item.get("co_so_1"), item.get("co_so_1_vnd")),
                "amount_vnd": item.get("co_so_1_vnd"),
                "status": price_status(item.get("co_so_1_vnd")),
            },
            "co_so_2": {
                "display": display_price(item.get("co_so_2"), item.get("co_so_2_vnd")),
                "amount_vnd": item.get("co_so_2_vnd"),
                "status": price_status(item.get("co_so_2_vnd")),
            },
        },
        "answer_policy": {
            "must_not_infer_missing_price": True,
            "must_not_copy_price_between_facilities": True,
            "group_items_have_no_general_price": item["item_type"] == "group",
            "use_children_for_group_price": item["item_type"] == "group",
        },
        "canonical_answer_vi": canonical_answer(item),
        "query_variants": query_variants(item),
        "retrieval_text": retrieval_text(item),
    }


def convert_clean_to_rag(clean_json: Path, rag_jsonl: Path, rag_json: Path, summary_path: Path) -> dict[str, Any]:
    clean_tree = json.loads(clean_json.read_text(encoding="utf-8"))
    if not isinstance(clean_tree, list):
        raise TypeError("Clean JSON must be a list of hierarchical objects")

    clean_items = flatten_tree(clean_tree)
    rag_records = [make_rag_record(item) for item in clean_items]

    rag_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with rag_jsonl.open("w", encoding="utf-8") as f:
        for record in rag_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    rag_json.write_text(json.dumps(rag_records, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "input": str(clean_json),
        "outputs": {
            "rag_jsonl": str(rag_jsonl),
            "rag_json": str(rag_json),
        },
        "rag_record_count": len(rag_records),
        "group_record_count": sum(record["metadata"]["item_type"] == "group" for record in rag_records),
        "service_record_count": sum(record["metadata"]["item_type"] == "service" for record in rag_records),
        "records_with_any_price": sum(record["metadata"]["has_price"] for record in rag_records),
        "records_with_children": sum(record["metadata"]["child_count"] > 0 for record in rag_records),
        "recommended_embedding_field": "retrieval_text",
        "recommended_answer_field": "canonical_answer_vi",
        "warning": "Do not embed only raw JSON keys. Embed retrieval_text and keep prices/metadata as structured payload.",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert clean hierarchical service-price JSON to RAG-ready JSON/JSONL.")
    parser.add_argument("--clean-json", type=Path, default=DEFAULT_CLEAN_JSON)
    parser.add_argument("--rag-jsonl", type=Path, default=DEFAULT_RAG_JSONL)
    parser.add_argument("--rag-json", type=Path, default=DEFAULT_RAG_JSON)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = convert_clean_to_rag(args.clean_json, args.rag_jsonl, args.rag_json, args.summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
