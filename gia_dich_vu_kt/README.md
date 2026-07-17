# Gia dich vu ky thuat Benh vien Tim Ha Noi 2025

Nguon chinh: trang "Gia dich vu ky thuat ap dung tai Benh vien Tim Ha Noi 2025" tren website Benh vien Tim Ha Noi.

- Trang bai viet: https://benhvientimhanoi.vn/vi/chi-tiet-lich-kham/bang-gia-dich-vu/gia-dich-vu-ky-thuat-ap-dung-tai-benh-vien-tim-ha-noi-2025
- File Google Drive trong iframe cua bai viet: `12jH3KovC3PHNoXQn9KekZkJXMcxtb2_S`
- PDF goc da tai: `GiaDVBV_tim_HN.pdf`

Ket qua trich xuat:

- `gia_dich_vu_ky_thuat_2025.csv`: bang chuan hoa UTF-8 BOM, dung de nap vao Excel/database.
- `gia_dich_vu_ky_thuat_2025.xlsx`: bang Excel.
- `gia_dich_vu_ky_thuat_2025.json`: bang chuan hoa dang JSON.
- `raw_tables.jsonl`: bang tho theo tung trang de doi chieu.
- `raw_pages_text/page_*.txt`: text tho cua day du 200 trang PDF.
- `source.html`, `drive_preview.html`, `source_info.json`: thong tin nguon va HTML da luu.
- `extraction_summary.json`: thong ke trich xuat.

Thong ke chinh:

- PDF: 200 trang.
- Bang tho: 198 bang.
- Ban ghi chuan hoa: 2.946 dong.
- Phan "DICH VU KY THUAT VA XET NGHIEM": STT 1-2898, khong thieu, khong trung.
- Phan "DICH VU KY THUAT THUC HIEN BANG PHUONG PHAP VO CAM GAY TE": STT 1-35, khong thieu, khong trung.

Lenh tai tao sau khi cai thu vien `pypdf`, `pdfplumber`, `pandas`, `openpyxl`:

```bash
python gia_dich_vu_kt/extract_gia_dich_vu.py
```
