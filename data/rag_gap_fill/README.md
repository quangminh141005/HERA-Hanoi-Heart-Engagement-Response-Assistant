# HERA RAG Gap Fill Bundle

Bundle này bổ sung dữ liệu thật cho các gap trong `docs/DATA_GAP_SOURCES.md`.

Nguồn đã tải/audit:

- `data/source/raw/hanoi-heart-hospital-booking-guide-2026-07-18.html`
- `data/source/raw/hanoi-heart-hospital-voluntary-clinic-2026-07-18.html`

Output RAG-useable:

- `hospital_gap_sources.json`
- `hospital_gap_facts.json`
- `hospital_gap_rag.json`
- `hospital_gap_rag.jsonl`
- `hospital_gap_summary.json`

Các fact trong bundle này đều giữ `source_url`, `source_title`, `verified_at` và
`approval_status`. PDF bảng giá không nằm trong bundle gap-fill; dữ liệu giá được
tách sang `data/gia_bhyt/` và `data/gia_kthuat_theo_yeu_cau/` để tránh trộn loại giá.
