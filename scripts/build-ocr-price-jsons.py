#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "source" / "raw"
VERIFIED_AT = "2026-07-18T00:00:00+07:00"


@dataclass(frozen=True)
class OcrSpec:
    key: str
    out_dir: Path
    pdf_path: Path
    document_type: str
    price_kind: str
    source_id: str
    source_title: str
    source_url: str
    legal_basis: str
    first_data_page: int
    columns: dict[str, tuple[int, int]]
    price_fields: tuple[str, ...]


SPECS = [
    OcrSpec(
        key="gia_bhyt",
        out_dir=DATA_DIR / "gia_bhyt",
        pdf_path=RAW_DIR / "hanoi-heart-hospital-bhyt-price-2024.pdf",
        document_type="hospital_service_price_bhyt",
        price_kind="bhyt",
        source_id="SRC-HHH-BHYT-PRICE-PDF-2024",
        source_title="Bảng giá Bảo Hiểm Y Tế tại Bệnh Viện Tim Hà Nội",
        source_url="https://benhvientimhanoi.vn/vi/chi-tiet/bang-gia-dich-vu/bang-gia-bao-hiem-y-te-tai-benh-vien-tim-ha-noi.",
        legal_basis="Thông tư 22/2023/TT-BYT của Bộ Y tế theo mô tả trang nguồn",
        first_data_page=3,
        columns={
            "stt": (120, 245),
            "ma_tuong_duong": (245, 455),
            "dich_vu_ky_thuat": (455, 990),
            "gia_bhyt": (990, 1195),
            "ghi_chu": (1195, 1405),
        },
        price_fields=("gia_bhyt",),
    ),
    OcrSpec(
        key="gia_kthuat_theo_yeu_cau",
        out_dir=DATA_DIR / "gia_kthuat_theo_yeu_cau",
        pdf_path=RAW_DIR / "hanoi-heart-hospital-on-demand-price-2024.pdf",
        document_type="hospital_service_price_on_demand",
        price_kind="on_demand",
        source_id="SRC-HHH-ON-DEMAND-PRICE-PDF-2024",
        source_title="Bảng báo giá Dịch vụ kỹ thuật theo yêu cầu tại Bệnh viện Tim Hà Nội",
        source_url="https://benhvientimhanoi.vn/vi/chi-tiet-lich-kham/bang-gia-dich-vu/bang-bao-gia-dich-vu-ky-thuat-theo-yeu-cau-tai-benh-vien-tim-ha-noi.",
        legal_basis="Quyết định số 2823/QĐ-BVT ngày 14/08/2023 theo mô tả trang nguồn",
        first_data_page=3,
        columns={
            "stt": (120, 220),
            "ghi_chu": (220, 350),
            "dich_vu_ky_thuat": (350, 710),
            "gia_dich_vu_y_te": (710, 940),
            "gia_kham_benh": (940, 1145),
            "gia_dich_vu_theo_yeu_cau": (1145, 1395),
        },
        price_fields=("gia_dich_vu_y_te", "gia_kham_benh", "gia_dich_vu_theo_yeu_cau"),
    ),
]


def one_line(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_vnd(value: str) -> int | None:
    text = one_line(value)
    if not re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+|\d{4,}", text):
        return None
    return int(re.sub(r"[,.]", "", text))


def is_stt(value: str) -> bool:
    return bool(re.fullmatch(r"\d{1,4}|[IVX]{1,6}", one_line(value), flags=re.I))


def slug(value: str) -> str:
    text = one_line(value).lower().replace(",", "_").replace(".", "_")
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_") or "unknown"


def bbox_center(box: list[list[float]]) -> tuple[float, float]:
    xs = [point[0] for point in box]
    ys = [point[1] for point in box]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def normalize_ocr_item(item: list[Any], page: int) -> dict[str, Any]:
    box, text, score = item
    cx, cy = bbox_center(box)
    return {
        "page": page,
        "text": one_line(text),
        "score": float(score),
        "box": box,
        "cx": cx,
        "cy": cy,
        "xmin": min(point[0] for point in box),
        "xmax": max(point[0] for point in box),
        "ymin": min(point[1] for point in box),
        "ymax": max(point[1] for point in box),
    }


def column_for(token: dict[str, Any], spec: OcrSpec) -> str | None:
    for name, (left, right) in spec.columns.items():
        if left <= token["cx"] < right:
            return name
    return None


def extract_ocr(spec: OcrSpec, scale: float = 2.5) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    import pypdfium2 as pdfium
    from rapidocr_onnxruntime import RapidOCR

    pdf = pdfium.PdfDocument(str(spec.pdf_path))
    ocr = RapidOCR()
    all_tokens: list[dict[str, Any]] = []
    raw_ocr_path = spec.out_dir / "raw_ocr.jsonl"
    with raw_ocr_path.open("w", encoding="utf-8") as raw_out:
        with tempfile.TemporaryDirectory(prefix=f"hera_{spec.key}_ocr_") as tmpdir:
            rendered_dir = Path(tmpdir)
            for page_index in range(spec.first_data_page, len(pdf) + 1):
                page = pdf[page_index - 1]
                image_path = rendered_dir / f"page_{page_index:03d}.png"
                page.render(scale=scale).to_pil().save(image_path)
                result, elapsed = ocr(str(image_path))
                tokens = [normalize_ocr_item(item, page_index) for item in (result or []) if one_line(item[1])]
                all_tokens.extend(tokens)
                raw_out.write(json.dumps({
                    "page": page_index,
                    "elapsed": elapsed,
                    "tokens": tokens,
                }, ensure_ascii=False) + "\n")

    return all_tokens, {
        "pdf_pages": len(pdf),
        "first_data_page": spec.first_data_page,
        "render_scale": scale,
        "rendered_pages_dir": None,
        "raw_ocr_jsonl": str(raw_ocr_path.relative_to(ROOT)),
        "ocr_token_count": len(all_tokens),
    }


def page_records(tokens: list[dict[str, Any]], spec: OcrSpec) -> list[dict[str, Any]]:
    tokens = sorted(tokens, key=lambda token: (token["cy"], token["cx"]))
    price_tokens = [
        token for token in tokens
        if column_for(token, spec) in spec.price_fields and parse_vnd(token["text"]) is not None and token["cy"] > 420
    ]
    price_tokens = sorted(price_tokens, key=lambda token: token["cy"])
    clusters: list[list[dict[str, Any]]] = []
    for token in price_tokens:
        if not clusters or abs(token["cy"] - sum(item["cy"] for item in clusters[-1]) / len(clusters[-1])) > 36:
            clusters.append([token])
        else:
            clusters[-1].append(token)

    centers = [sum(token["cy"] for token in cluster) / len(cluster) for cluster in clusters]
    records = []
    last_stt = ""
    last_note = ""

    for idx, cluster in enumerate(clusters):
        center = centers[idx]
        top = (centers[idx - 1] + center) / 2 if idx else center - 52
        bottom = (center + centers[idx + 1]) / 2 if idx + 1 < len(centers) else center + 52
        row_tokens = [
            token for token in tokens
            if top <= token["cy"] < bottom and token["cy"] > 420
        ]
        cols: dict[str, list[dict[str, Any]]] = {name: [] for name in spec.columns}
        for token in row_tokens:
            col = column_for(token, spec)
            if col:
                cols[col].append(token)

        values = {
            name: one_line(" ".join(token["text"] for token in sorted(col_tokens, key=lambda item: (item["cy"], item["cx"]))))
            for name, col_tokens in cols.items()
        }
        stt_value = values.get("stt", "")
        if is_stt(stt_value):
            last_stt = stt_value
        else:
            values["stt"] = last_stt or f"page-{cluster[0]['page']}-row-{idx + 1}"

        if values.get("ghi_chu"):
            last_note = values["ghi_chu"]
        elif spec.price_kind == "on_demand" and last_note:
            values["ghi_chu"] = last_note

        price_points = []
        for field in spec.price_fields:
            amount = parse_vnd(values.get(field, ""))
            if amount is not None:
                price_points.append({
                    "field": field,
                    "label": field.replace("_", " "),
                    "display": values[field],
                    "amount_vnd": amount,
                })

        service = values.get("dich_vu_ky_thuat", "")
        if not service or not price_points:
            continue

        scores = [token["score"] for token in row_tokens]
        records.append({
            "page": cluster[0]["page"],
            "stt": values["stt"],
            "ma_tuong_duong": values.get("ma_tuong_duong", ""),
            "dich_vu_ky_thuat": service,
            "ghi_chu": values.get("ghi_chu", ""),
            "price_kind": spec.price_kind,
            "price_points": price_points,
            "ocr_confidence_min": min(scores) if scores else None,
            "ocr_confidence_avg": sum(scores) / len(scores) if scores else None,
            "ocr_token_count": len(row_tokens),
            "raw_columns": values,
        })
    return records


def build_flat(tokens: list[dict[str, Any]], spec: OcrSpec) -> list[dict[str, Any]]:
    records = []
    pages = sorted({token["page"] for token in tokens})
    for page in pages:
        records.extend(page_records([token for token in tokens if token["page"] == page], spec))
    return records


def make_clean(record: dict[str, Any], spec: OcrSpec, index: int) -> dict[str, Any]:
    primary = record["price_points"][0]
    record_id = f"hht_{spec.price_kind}_ocr_2024__{index:04d}__stt_{slug(record['stt'])}__{slug(record['dich_vu_ky_thuat'])[:80]}"
    prices = {
        point["field"]: {
            "label": point["label"],
            "display": point["display"],
            "amount_vnd": point["amount_vnd"],
            "status": "published_ocr_review",
        }
        for point in record["price_points"]
    }
    return {
        "id": record_id,
        "document_type": spec.document_type,
        "price_kind": spec.price_kind,
        "page": record["page"],
        "stt": record["stt"],
        "ma_tuong_duong": record.get("ma_tuong_duong", ""),
        "service_name": record["dich_vu_ky_thuat"],
        "service_name_single_line": one_line(record["dich_vu_ky_thuat"]),
        "ghi_chu": record.get("ghi_chu", ""),
        "ghi_chu_single_line": one_line(record.get("ghi_chu", "")),
        "has_price": True,
        "prices": {
            "primary": {
                "field": primary["field"],
                "label": primary["label"],
                "display": primary["display"],
                "amount_vnd": primary["amount_vnd"],
                "status": "published_ocr_review",
            },
            **prices,
            "all": record["price_points"],
        },
        "ocr": {
            "confidence_min": record["ocr_confidence_min"],
            "confidence_avg": record["ocr_confidence_avg"],
            "token_count": record["ocr_token_count"],
            "requires_human_review": True,
        },
        "approval_status": "review_only",
        "verified_at": VERIFIED_AT,
        "raw_columns": record["raw_columns"],
    }


def make_rag(item: dict[str, Any], spec: OcrSpec) -> dict[str, Any]:
    primary = item["prices"]["primary"]
    code_text = f" Mã tương đương: {item['ma_tuong_duong']}." if item.get("ma_tuong_duong") else ""
    note_text = f" Ghi chú: {item['ghi_chu_single_line']}." if item.get("ghi_chu_single_line") else ""
    canonical = (
        f"STT {item['stt']} - {item['service_name_single_line']}.{code_text} "
        f"{primary['label']}: {primary['display']} đồng.{note_text}"
    )
    variants = {
        item["service_name_single_line"],
        f"giá {item['service_name_single_line']}",
        f"{spec.price_kind} {item['service_name_single_line']}",
        f"stt {item['stt']} {item['service_name_single_line']}",
    }
    if item.get("ma_tuong_duong"):
        variants.add(item["ma_tuong_duong"])
        variants.add(f"giá mã {item['ma_tuong_duong']}")

    retrieval_lines = [
        f"Nguồn: {spec.source_title}.",
        f"Căn cứ: {spec.legal_basis}.",
        f"Loại giá: {spec.price_kind}.",
        f"Trang PDF: {item['page']}.",
        f"STT: {item['stt']}.",
        f"Tên dịch vụ: {item['service_name_single_line']}.",
    ]
    if item.get("ma_tuong_duong"):
        retrieval_lines.append(f"Mã tương đương: {item['ma_tuong_duong']}.")
    for point in item["prices"]["all"]:
        retrieval_lines.append(f"{point['label']}: {point['display']} đồng.")
    if item.get("ghi_chu_single_line"):
        retrieval_lines.append(f"Ghi chú: {item['ghi_chu_single_line']}.")
    retrieval_lines.append(
        "Quy tắc trả lời: đây là dữ liệu OCR review_only; chỉ trả đúng giá trong payload, không trộn loại giá BHYT và theo yêu cầu, không tự sửa số tiền."
    )

    return {
        "rag_id": f"rag__{item['id']}",
        "document_type": "hospital_service_price",
        "price_kind": spec.price_kind,
        "source": {
            "hospital": "Bệnh viện Tim Hà Nội",
            "source_id": spec.source_id,
            "title": spec.source_title,
            "url": spec.source_url,
            "pdf_file": str(spec.pdf_path.relative_to(ROOT)),
            "page": item["page"],
            "legal_basis": spec.legal_basis,
            "extraction_method": "rapidocr_onnxruntime_layout_grouping",
        },
        "metadata": {
            "id": item["id"],
            "stt": item["stt"],
            "ma_tuong_duong": item.get("ma_tuong_duong", ""),
            "price_kind": spec.price_kind,
            "approval_status": item["approval_status"],
            "verified_at": item["verified_at"],
            "ocr_confidence_avg": item["ocr"]["confidence_avg"],
            "requires_human_review": True,
        },
        "service": {
            "name": item["service_name_single_line"],
            "full_name": item["service_name_single_line"],
            "note": item.get("ghi_chu_single_line", ""),
        },
        "prices": item["prices"],
        "answer_policy": {
            "must_not_infer_missing_price": True,
            "must_not_mix_price_kinds": True,
            "must_check_price_kind": spec.price_kind,
            "ocr_review_only": True,
        },
        "canonical_answer_vi": canonical,
        "query_variants": sorted(value for value in variants if value),
        "retrieval_text": "\n".join(retrieval_lines),
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(spec: OcrSpec) -> dict[str, Any]:
    spec.out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(spec.pdf_path, spec.out_dir / "source.pdf")
    tokens, ocr_summary = extract_ocr(spec)
    flat = build_flat(tokens, spec)
    clean = [make_clean(record, spec, idx) for idx, record in enumerate(flat, start=1)]
    rag = [make_rag(record, spec) for record in clean]

    write_json(spec.out_dir / "flat.json", flat)
    write_json(spec.out_dir / "clean.json", clean)
    write_json(spec.out_dir / "rag.json", rag)
    with (spec.out_dir / "rag.jsonl").open("w", encoding="utf-8") as handle:
        for record in rag:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary = {
        "dataset": spec.key,
        "document_type": spec.document_type,
        "price_kind": spec.price_kind,
        "source_id": spec.source_id,
        "source_title": spec.source_title,
        "source_url": spec.source_url,
        "pdf_file": str(spec.pdf_path.relative_to(ROOT)),
        "generated_at": VERIFIED_AT,
        "approval_status": "review_only",
        "extraction_method": "rapidocr_onnxruntime_layout_grouping",
        "flat_record_count": len(flat),
        "clean_record_count": len(clean),
        "rag_record_count": len(rag),
        "recommended_embedding_field": "retrieval_text",
        "recommended_answer_field": "canonical_answer_vi",
        "warning": "OCR output can contain Vietnamese accent/name errors. Keep approval_status=review_only until manually QA'd.",
        **ocr_summary,
    }
    write_json(spec.out_dir / "summary.json", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build OCR-based price JSONs for Hanoi Heart Hospital PDFs.")
    parser.add_argument("--only", choices=[spec.key for spec in SPECS])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summaries = [build(spec) for spec in SPECS if args.only in (None, spec.key)]
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
