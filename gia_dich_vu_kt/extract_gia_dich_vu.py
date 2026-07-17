#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pdfplumber
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent
PDF_PATH = ROOT / "GiaDVBV_tim_HN.pdf"
RAW_TEXT_DIR = ROOT / "raw_pages_text"
RAW_TABLES_JSONL = ROOT / "raw_tables.jsonl"
NORMALIZED_CSV = ROOT / "gia_dich_vu_ky_thuat_2025.csv"
NORMALIZED_JSON = ROOT / "gia_dich_vu_ky_thuat_2025.json"
NORMALIZED_XLSX = ROOT / "gia_dich_vu_ky_thuat_2025.xlsx"
SUMMARY_JSON = ROOT / "extraction_summary.json"
SOURCE_INFO_JSON = ROOT / "source_info.json"

SOURCE_URL = (
    "https://benhvientimhanoi.vn/vi/chi-tiet-lich-kham/bang-gia-dich-vu/"
    "gia-dich-vu-ky-thuat-ap-dung-tai-benh-vien-tim-ha-noi-2025"
)
DRIVE_FILE_ID = "12jH3KovC3PHNoXQn9KekZkJXMcxtb2_S"
DRIVE_DOWNLOAD_URL = (
    "https://drive.usercontent.google.com/uc?"
    f"id={DRIVE_FILE_ID}&export=download"
)


def clean(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[ \t]+", " ", str(value).replace("\r", "\n")).strip()


def join_cells(cells: list[Any]) -> str:
    parts = [clean(cell) for cell in cells if clean(cell)]
    return "\n".join(parts).strip()


def normalize_price(value: str) -> str:
    value = clean(value)
    return value if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", value) else value


def is_stt(value: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:,\d+)?", clean(value)))


def is_code(value: str) -> bool:
    return bool(re.fullmatch(r"\d{2}\.\d{4}\.\d{4}", clean(value)))


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
    blob = " ".join(
        record[key]
        for key in ("stt", "ma_tuong_duong", "dich_vu_ky_thuat", "co_so_1", "co_so_2", "ghi_chu")
    ).upper()
    if not any(record[k] for k in ("stt", "ma_tuong_duong", "dich_vu_ky_thuat", "co_so_1", "co_so_2", "ghi_chu")):
        return True
    header_terms = ("STT", "MÃ TƯƠNG", "ĐƯƠNG", "DỊCH VỤ KỸ THUẬT", "CƠ SỞ 1", "CƠ SỞ 2", "GHI CHÚ")
    if any(term in blob for term in header_terms) and not is_stt(record["stt"]):
        return True
    if blob in {"ĐƠN VỊ TÍNH: ĐỒNG", "SỞ Y TẾ HÀ NỘI BỆNH VIỆN TIM HÀ NỘI"}:
        return True
    return False


def append_continuation(records: list[dict[str, str]], continuation: dict[str, str]) -> None:
    if not records:
        return
    previous = records[-1]
    for key in ("dich_vu_ky_thuat", "ghi_chu"):
        extra = continuation[key]
        if extra:
            previous[key] = (previous[key] + "\n" + extra).strip() if previous[key] else extra
    for key in ("co_so_1", "co_so_2", "ma_tuong_duong"):
        if continuation[key] and not previous[key]:
            previous[key] = continuation[key]


def extract() -> None:
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"Missing PDF: {PDF_PATH}")

    RAW_TEXT_DIR.mkdir(exist_ok=True)
    reader = PdfReader(str(PDF_PATH))
    page_count = len(reader.pages)

    raw_table_count = 0
    records: list[dict[str, str]] = []
    section = ""

    with RAW_TABLES_JSONL.open("w", encoding="utf-8") as raw_out, pdfplumber.open(PDF_PATH) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            (RAW_TEXT_DIR / f"page_{page_index:03d}.txt").write_text(text, encoding="utf-8")
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

    fieldnames = [
        "page",
        "section",
        "stt",
        "ma_tuong_duong",
        "dich_vu_ky_thuat",
        "co_so_1",
        "co_so_2",
        "ghi_chu",
    ]
    with NORMALIZED_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    NORMALIZED_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        import pandas as pd

        pd.DataFrame(records, columns=fieldnames).to_excel(NORMALIZED_XLSX, index=False)
    except Exception as exc:
        print(f"Could not write XLSX: {exc}")

    numeric_stt = []
    duplicate_stt = []
    seen = set()
    for record in records:
        stt = record["stt"]
        if stt.isdigit():
            num = int(stt)
            numeric_stt.append(num)
            if num in seen:
                duplicate_stt.append(num)
            seen.add(num)

    missing_stt = []
    if numeric_stt:
        all_expected = set(range(min(numeric_stt), max(numeric_stt) + 1))
        missing_stt = sorted(all_expected - set(numeric_stt))

    section_stats = {}
    for section_name, section_records in defaultdict(list, {
        section_name: [r for r in records if r["section"] == section_name]
        for section_name in sorted({r["section"] for r in records})
    }).items():
        section_numeric = [int(r["stt"]) for r in section_records if r["stt"].isdigit()]
        section_seen = set()
        section_dupes = []
        for number in section_numeric:
            if number in section_seen:
                section_dupes.append(number)
            section_seen.add(number)
        if section_numeric:
            expected = set(range(min(section_numeric), max(section_numeric) + 1))
            section_missing = sorted(expected - set(section_numeric))
        else:
            section_missing = []
        section_stats[section_name] = {
            "record_count": len(section_records),
            "numeric_record_count": len(section_numeric),
            "non_integer_stt_count": len(section_records) - len(section_numeric),
            "first_numeric_stt": min(section_numeric) if section_numeric else None,
            "last_numeric_stt": max(section_numeric) if section_numeric else None,
            "missing_numeric_stt": section_missing,
            "duplicate_numeric_stt": section_dupes,
        }

    source_info = {
        "source_url": SOURCE_URL,
        "drive_file_id": DRIVE_FILE_ID,
        "drive_download_url": DRIVE_DOWNLOAD_URL,
        "pdf_file": PDF_PATH.name,
        "downloaded_from_article_iframe": f"https://drive.google.com/file/d/{DRIVE_FILE_ID}/preview",
    }
    SOURCE_INFO_JSON.write_text(json.dumps(source_info, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "source_url": SOURCE_URL,
        "drive_file_id": DRIVE_FILE_ID,
        "drive_download_url": DRIVE_DOWNLOAD_URL,
        "pdf_file": PDF_PATH.name,
        "pdf_pages": page_count,
        "raw_table_count": raw_table_count,
        "normalized_record_count": len(records),
        "first_numeric_stt": min(numeric_stt) if numeric_stt else None,
        "last_numeric_stt": max(numeric_stt) if numeric_stt else None,
        "missing_numeric_stt": missing_stt,
        "duplicate_numeric_stt": duplicate_stt,
        "section_counts": dict(Counter(record["section"] for record in records)),
        "section_stats": section_stats,
        "notes": [
            "CSV/JSON are extracted from the downloaded source PDF text layer.",
            "raw_tables.jsonl preserves pdfplumber table rows by page for audit.",
            "raw_pages_text/page_*.txt preserves extracted page text for audit.",
        ],
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    extract()
