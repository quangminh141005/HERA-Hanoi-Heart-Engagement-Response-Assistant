# HERA RAG Gap Fill Bundle

Bundle này bổ sung dữ liệu thật cho các gap trong `docs/DATA_GAP_SOURCES.md`.

Nguồn đã tải/audit:

- `data/source/raw/hanoi-heart-hospital-booking-guide-2026-07-18.html`
- `data/source/raw/hanoi-heart-hospital-voluntary-clinic-2026-07-18.html`
- `data/source/raw/hanoi-heart-hospital-general-introduction-2026-07-18.html`
- `data/source/raw/hanoi-heart-hospital-leadership-2026-07-18.html`
- `data/source/raw/hanoi-heart-hospital-zalo-guide-2026-07-18.html`
- `data/source/raw/bhxh-bhyt-outpatient-crosstier-2026-06-26.html`

Output RAG-useable:

- `hospital_gap_sources.json`
- `hospital_gap_facts.json`
- `hospital_gap_rag.json`
- `hospital_gap_rag.jsonl`
- `hospital_gap_summary.json`

Các fact trong bundle này đều giữ `source_url`, `source_title`, `verified_at` và
`approval_status`. PDF bảng giá không nằm trong bundle gap-fill; dữ liệu giá được
tách sang `data/gia_bhyt/` và `data/gia_kthuat_theo_yeu_cau/` để tránh trộn loại giá.

Một số gap chưa có nguồn chính thức đủ chi tiết được giữ dưới dạng
`unresolved_data_gap` hoặc `review_only` để RAG biết phải từ chối/redirect thay vì
tự suy luận, ví dụ thủ tục nhập viện, hướng dẫn tái khám, và quy trình cấp cứu chi tiết.
