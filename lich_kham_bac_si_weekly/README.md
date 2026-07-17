# Lịch khám bác sĩ tuần 2026-06-08 đến 2026-06-14

Nguồn: https://benhvientimhanoi.vn/vi/chi-tiet-lich-kham/lich-lam-viec-cua-bac-sy/lich-kham-benh-cua-cac-bac-si-benh-vien-tim-ha-noi-tuan-tu-08d06d2026-14d06d2026

## Files

- `lich_kham_bac_si_2026-06-08_to_2026-06-14.csv`: CSV gộp toàn bộ 35 dòng lịch.
- `lich_kham_bac_si_2026-06-08_to_2026-06-14.json`: JSON gộp kèm metadata nguồn.
- `co_so_1__khu_kham_benh_tu_nguyen_1.csv`: bảng TN1 cơ sở 1.
- `co_so_1__khu_kham_benh_tu_nguyen_3.csv`: bảng TN3 cơ sở 1.
- `co_so_2__khu_kham_benh_tu_nguyen.csv`: bảng TN cơ sở 2.
- `co_so_2__phong_kham_da_khoa.csv`: bảng Đa khoa cơ sở 2.
- `source_images/`: ảnh gốc tải từ website.
- `build_schedule_data.py`: script tái sinh CSV/JSON từ dữ liệu đã trích xuất.

## Schema CSV

- `source_url`: trang nguồn.
- `source_image`: ảnh nguồn trong `source_images/`.
- `co_so`: cơ sở bệnh viện.
- `khu`: khu/phòng khám trong bảng.
- `phong_kham`: phòng khám.
- `thoi_gian`: thời gian làm việc trong ảnh.
- `thu_2_2026_06_08` ... `chu_nhat_2026_06_14`: nội dung trực từng ngày.
- `ghi_chu`: ghi chú khi ảnh gốc có điểm cần giữ nguyên hoặc làm rõ.

Các ô nhiều dòng trong ảnh được nối bằng dấu `;`.
