# Dich Vu Ky Thuat Data

Folder này gom toàn bộ dữ liệu giá/dịch vụ kỹ thuật dùng cho RAG.

## Bảng giá 2025

- `gia_dich_vu_ky_thuat_2025.json`: JSON sạch dạng cây, giữ để tương thích generator hiện tại.
- `gia_dich_vu_ky_thuat_2025_clean.json`: JSON sạch dạng cây, có giá số, `item_type`, `availability`, `full_name`.
- `gia_dich_vu_ky_thuat_2025_rag.json`: RAG payload dạng JSON array.
- `gia_dich_vu_ky_thuat_2025_rag.jsonl`: RAG payload dạng JSONL.
- `clean_json_summary.json`, `rag_json_summary.json`: summary của pipeline.

## Bảng giá PDF khác

Hai bảng giá PDF scan được tách riêng để tránh trộn loại giá:

- `data/gia_bhyt/`
- `data/gia_kthuat_theo_yeu_cau/`

Khi nạp RAG, embed `retrieval_text` và giữ nguyên object JSON làm metadata/payload.
Không để model tự suy luận giá từ text tự do; backend nên đọc giá từ `prices`.
