#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PDF = DEFAULT_DATA_DIR / "GiaDVBV_tim_HN.pdf"
DEFAULT_FLAT_JSON = DEFAULT_DATA_DIR / "gia_dich_vu_ky_thuat_2025_flat.json"
DEFAULT_CSV = DEFAULT_DATA_DIR / "gia_dich_vu_ky_thuat_2025.csv"
DEFAULT_XLSX = DEFAULT_DATA_DIR / "gia_dich_vu_ky_thuat_2025.xlsx"
DEFAULT_RAW_TEXT_DIR = DEFAULT_DATA_DIR / "raw_pages_text"
DEFAULT_RAW_TABLES = DEFAULT_DATA_DIR / "raw_tables.jsonl"
DEFAULT_SUMMARY = DEFAULT_DATA_DIR / "extract_pdf_to_flat_summary.json"


SOURCE_URL = (
    "https://benhvientimhanoi.vn/vi/chi-tiet-lich-kham/bang-gia-dich-vu/"
    "gia-dich-vu-ky-thuat-ap-dung-tai-benh-vien-tim-ha-noi-2025"
)
DRIVE_FILE_ID = "12jH3KovC3PHNoXQn9KekZkJXMcxtb2_S"


def clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[ \t]+", " ", str(value).replace("\r", "\n")).strip()


def join_cells(cells: list[Any]) -> str:
    return "\n".join(clean(cell) for cell in cells if clean(cell)).strip()


def is_stt(value: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:[,.]\d+)?", clean(value)))


def is_code(value: str) -> bool:
    return bool(re.fullmatch(r"\d{2}\.\d{4}\.\d{4}", clean(value)))


def normalize_price(value: str) -> str:
    value = clean(value)
    return value if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", value) else value


def current_section(page_text: str, previous: str) -> str:
    text = " ".join(page_text.split())
    if "KHÁM BỆNH VÀ NGÀY GIƯỜNG ĐIỀU TRỊ" in text:
        return "KHÁM BỆNH VÀ NGÀY GIƯỜNG ĐIỀU TRỊ"
    if "DỊCH VỤ KỸ THUẬT VÀ XÉT NGHIỆM" in text:
        return "DỊCH VỤ KỸ THUẬT VÀ XÉT NGHIỆM"
    if "KHÁM SỨC KHỎE TOÀN DIỆN" in text:
        return "KHÁM SỨC KHỎE TOÀN DIỆN LAO ĐỘNG, LÁI XE, KHÁM SỨC KHỎE ĐỊNH KỲ"
    if "DỊCH VỤ KỸ THUẬT THỰC HIỆN BẰNG PHƯƠNG PHÁP VÔ CẢM GÂY TÊ" in text:
        return "DỊCH VỤ KỸ THUẬT THỰC HIỆN BẰNG PHƯƠNG PHÁP VÔ CẢM GÂY TÊ"
    return previous


def row_to_record(row: list[Any], page: int, section: str) -> dict[str, str]:
    cells = list(row)
    if len(cells) >= 18:
        stt = join_cells(cells[0:3])
        code = join_cells(cells[3:6])
        service = join_cells(cells[6:9])
        cs1 = join_cells(cells[9:12])
        cs2 = join_cells(cells[12:15])
        note = join_cells(cells[15:18])
    elif len(cells) >= 15:
        stt = join_cells(cells[0:3])
        code = ""
        service = join_cells(cells[3:6])
        cs1 = join_cells(cells[6:9])
        cs2 = join_cells(cells[9:12])
        note = join_cells(cells[12:15])
    else:
        padded = cells + [""] * (6 - len(cells))
        stt, code, service, cs1, cs2, note = [clean(x) for x in padded[:6]]

    return {
        "page": str(page),
        "section": section,
        "stt": clean(stt),
        "ma_tuong_duong": clean(code),
        "dich_vu_ky_thuat": clean(service),
        "co_so_1": normalize_price(cs1),
        "co_so_2": normalize_price(cs2),
        "ghi_chu": clean(note),
    }


def is_header_or_empty(record: dict[str, str]) -> bool:
    data_keys = ("stt", "ma_tuong_duong", "dich_vu_ky_thuat", "co_so_1", "co_so_2", "ghi_chu")
    blob = " ".join(record[key] for key in data_keys).upper()
    if not any(record[key] for key in data_keys):
        return True
    header_terms = ("STT", "MÃ TƯƠNG", "ĐƯƠNG", "DỊCH VỤ KỸ THUẬT", "CƠ SỞ 1", "CƠ SỞ 2", "GHI CHÚ")
    if any(term in blob for term in header_terms) and not is_stt(record["stt"]):
        return True
    return blob in {"ĐƠN VỊ TÍNH: ĐỒNG", "SỞ Y TẾ HÀ NỘI BỆNH VIỆN TIM HÀ NỘI"}


def append_continuation(records: list[dict[str, str]], continuation: dict[str, str]) -> None:
    if not records:
        return
    previous = records[-1]
    for key in ("dich_vu_ky_thuat", "ghi_chu"):
        extra = continuation[key]
        if extra:
            previous[key] = f"{previous[key]}\n{extra}".strip() if previous[key] else extra
    for key in ("co_so_1", "co_so_2", "ma_tuong_duong"):
        if continuation[key] and not previous[key]:
            previous[key] = continuation[key]


def extract_pdf_to_flat(
    pdf_path: Path,
    flat_json_path: Path,
    csv_path: Path,
    xlsx_path: Path,
    raw_text_dir: Path,
    raw_tables_path: Path,
    summary_path: Path,
) -> dict[str, Any]:
    if not pdf_path.exists():
        raise FileNotFoundError(f"Missing PDF: {pdf_path}")

    import pdfplumber
    from pypdf import PdfReader

    raw_text_dir.mkdir(parents=True, exist_ok=True)
    flat_json_path.parent.mkdir(parents=True, exist_ok=True)
    page_count = len(PdfReader(str(pdf_path)).pages)

    records: list[dict[str, str]] = []
    raw_table_count = 0
    section = ""

    with raw_tables_path.open("w", encoding="utf-8") as raw_out, pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            (raw_text_dir / f"page_{page_index:03d}.txt").write_text(text, encoding="utf-8")
            section = current_section(text, section)

            for table_index, table in enumerate(page.extract_tables(), start=1):
                raw_table_count += 1
                raw_out.write(json.dumps({
                    "page": page_index,
                    "table_index": table_index,
                    "rows": table,
                }, ensure_ascii=False) + "\n")

                for row in table:
                    record = row_to_record(row, page_index, section)
                    if is_header_or_empty(record):
                        continue

                    has_new_stt = is_stt(record["stt"])
                    has_code = is_code(record["ma_tuong_duong"])
                    has_price = bool(record["co_so_1"] or record["co_so_2"])
                    has_service = bool(record["dich_vu_ky_thuat"])
                    if has_new_stt and (has_service or has_code or has_price):
                        records.append(record)
                    else:
                        append_continuation(records, record)

    flat_json_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    fieldnames = ["page", "section", "stt", "ma_tuong_duong", "dich_vu_ky_thuat", "co_so_1", "co_so_2", "ghi_chu"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    try:
        import pandas as pd

        pd.DataFrame(records, columns=fieldnames).to_excel(xlsx_path, index=False)
    except Exception as exc:
        print(f"Could not write XLSX: {exc}")

    summary = {
        "source_url": SOURCE_URL,
        "drive_file_id": DRIVE_FILE_ID,
        "pdf_file": str(pdf_path),
        "pdf_pages": page_count,
        "raw_table_count": raw_table_count,
        "flat_record_count": len(records),
        "section_counts": dict(Counter(record["section"] for record in records)),
        "outputs": {
            "flat_json": str(flat_json_path),
            "csv": str(csv_path),
            "xlsx": str(xlsx_path),
            "raw_text_dir": str(raw_text_dir),
            "raw_tables": str(raw_tables_path),
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract Hanoi Heart Hospital price PDF into flat JSON.")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--flat-json", type=Path, default=DEFAULT_FLAT_JSON)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    parser.add_argument("--raw-text-dir", type=Path, default=DEFAULT_RAW_TEXT_DIR)
    parser.add_argument("--raw-tables", type=Path, default=DEFAULT_RAW_TABLES)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = extract_pdf_to_flat(
        args.pdf,
        args.flat_json,
        args.csv,
        args.xlsx,
        args.raw_text_dir,
        args.raw_tables,
        args.summary,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
