# Gia BHYT

Nguồn: `https://benhvientimhanoi.vn/vi/chi-tiet/bang-gia-dich-vu/bang-gia-bao-hiem-y-te-tai-benh-vien-tim-ha-noi.`

Folder này chứa bảng giá BHYT được OCR từ PDF scan của Bệnh viện Tim Hà Nội.

- `source.pdf`: PDF nguồn đã tải từ iframe Google Drive trên website bệnh viện.
- `raw_ocr.jsonl`: token OCR kèm tọa độ/confidence theo trang.
- `flat.json`: dòng giá phẳng sau khi nhóm token OCR theo layout bảng.
- `clean.json`: JSON sạch có `prices`, `ocr`, `approval_status`.
- `rag.json` / `rag.jsonl`: payload RAG; embed `retrieval_text`, giữ `prices` làm structured payload.
- `summary.json`: thống kê extract.

Tất cả record hiện để `approval_status: review_only` vì OCR có thể sai dấu/tên dịch vụ.
Không dùng để production trước khi QA thủ công.
