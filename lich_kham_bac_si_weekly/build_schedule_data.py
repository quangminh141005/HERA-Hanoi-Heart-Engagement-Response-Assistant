#!/usr/bin/env python3
import csv
import json
from pathlib import Path


OUT_DIR = Path(__file__).resolve().parent
SOURCE_URL = (
    "https://benhvientimhanoi.vn/vi/chi-tiet-lich-kham/lich-lam-viec-cua-bac-sy/"
    "lich-kham-benh-cua-cac-bac-si-benh-vien-tim-ha-noi-tuan-tu-08d06d2026-14d06d2026"
)

DAYS = [
    ("thu_2_2026_06_08", "Thứ 2", "2026-06-08"),
    ("thu_3_2026_06_09", "Thứ 3", "2026-06-09"),
    ("thu_4_2026_06_10", "Thứ 4", "2026-06-10"),
    ("thu_5_2026_06_11", "Thứ 5", "2026-06-11"),
    ("thu_6_2026_06_12", "Thứ 6", "2026-06-12"),
    ("thu_7_2026_06_13", "Thứ 7", "2026-06-13"),
    ("chu_nhat_2026_06_14", "Chủ nhật", "2026-06-14"),
]

BASE_FIELDS = [
    "source_url",
    "source_image",
    "co_so",
    "khu",
    "phong_kham",
    "thoi_gian",
]
DAY_FIELDS = [key for key, _, _ in DAYS]
FIELDS = BASE_FIELDS + DAY_FIELDS + ["ghi_chu"]


def row(source_image, co_so, khu, phong_kham, thoi_gian, days, ghi_chu=""):
    if len(days) != len(DAY_FIELDS):
        raise ValueError(f"{phong_kham}: expected {len(DAY_FIELDS)} day cells")
    item = {
        "source_url": SOURCE_URL,
        "source_image": source_image,
        "co_so": co_so,
        "khu": khu,
        "phong_kham": phong_kham,
        "thoi_gian": thoi_gian,
        "ghi_chu": ghi_chu,
    }
    item.update(dict(zip(DAY_FIELDS, days)))
    return item


records = [
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 1", "Phòng khám số 1", "7.30 - 16.30", [
        "TS.BS Phạm Như Hùng",
        "TS.BS Phạm Như Hùng",
        "TS.BS Phạm Như Hùng",
        "TS.BS Phạm Như Hùng",
        "TS.BS Phạm Như Hùng",
        "Nghỉ",
        "ThS.BS Nguyễn Danh Sen",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 1", "Phòng khám số 2", "7.30 - 16.30", [
        "TS.BS Vũ Quỳnh Nga",
        "TS.BS Vũ Quỳnh Nga",
        "TS.BS Vũ Quỳnh Nga",
        "TS.BS Vũ Quỳnh Nga",
        "TS.BS Vũ Quỳnh Nga",
        "Nghỉ",
        "SAT: BSCKII Vũ Thị Trang",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 1", "Phòng khám số 3", "7.00 - 16.30", [
        "TS.BS Bùi Thị Thanh Hà",
        "TS.BS Nguyễn Xuân Tuấn",
        "TS.BS Bùi Thị Thanh Hà",
        "TS.BS Đinh Quang Huy",
        "TS.BS Bùi Thị Thanh Hà",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 1", "Phòng khám số 4", "7.30 - 16.30", [
        "Sáng: TS.BS Hoàng Văn Chiêu; BSCKII Nguyễn Văn Dần",
        "TS.BS Hà Mai Hương",
        "Sáng: TS.BS Hoàng Văn Chiêu; Chiều: ThS.BS Nguyễn Thị Quỳnh Trang",
        "TS.BS Hà Mai Hương",
        "Sáng: TS.BS Hoàng Văn Chiêu; Chiều: TS.BS Nguyễn Thị Thu Thủy",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 1", "Phòng khám số 5", "7.00 - 16.30", [
        "TS.BS Trần Thị Ngọc Lan",
        "Sáng: ThS.BS Nguyễn Thị Việt Nga; Chiều: BSCKII Vũ Thị Trang",
        "BSCKII Nguyễn Văn Dần",
        "Sáng: ThS.BS Nguyễn Thị Việt Nga; Chiều: TS.BS Ngọ Văn Thanh",
        "ThS.BS Nguyễn Xuân Từ",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 1", "Phòng khám số 6", "7.30 - 16.30", [
        "ThS.BS Nguyễn Thị Việt Nga",
        "BSCKII Phạm Thị An",
        "TS.BS Nguyễn Thị Thu Thủy",
        "BSCKII Nguyễn Văn Thực",
        "ThS.BS Nguyễn Thị Quỳnh Trang",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 1", "Phòng khám số 7", "7.00 - 16.00", [
        "TS.BS Nguyễn Xuân Tuấn",
        "TS.BS Trần Thị An",
        "ThS.BS Nguyễn Xuân Từ",
        "TS.BS Trần Thị Ngọc Lan",
        "BSCKII Vũ Thị Trang",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 1", "Phòng khám số 8", "7.00 - 16.00", [
        "TS.BS Đinh Quang Huy",
        "TS.BS Nguyễn Thị Thu Thủy",
        "Sáng: TS.BS Trần Thị An; Chiều: BSCKII Phạm Thị An",
        "BS CKII Phạm Quang Huy",
        "TS.BS Trần Thị Ngọc Lan",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 3", "Phòng khám số 1", "7.30 - 16.30", [
        "ThS.BS Võ Thị Ngọc Anh",
        "ThS.BS Nguyễn Danh Sen",
        "ThS.BS Võ Thị Ngọc Anh",
        "ThS.BS Nguyễn Danh Sen",
        "BS CKII Trần Thị Thanh Hà",
        "BSCKII Nguyễn Văn Thực",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 3", "Phòng khám số 2", "7.30 - 16.30", [
        "Sáng: ThS.BS Nguyễn Xuân Từ; Chiều: BS Đinh Hải Nam",
        "ThS.BS Nguyễn Xuân Từ",
        "Sáng: ThS.BS Nguyễn Đình Hồng Phúc; Chiều: ThS.BS Phạm Đăng Anh",
        "ThS.BS Lê Thị Thảo",
        "BS Đinh Hải Nam",
        "ThS.BS Đỗ Thị Vân Anh",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 3", "Phòng khám số 3", "7.30 - 16.30", [
        "ThS.BS Trần Đắc Long",
        "BSCKI Đào Thị Thu Hà",
        "ThS.BS Nguyễn Quốc Hùng",
        "ThS.BS Nguyễn Toàn Thắng",
        "BSCKI Đào Thị Thu Hà",
        "SAT: BS Trần Thanh Hoa",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 3", "Phòng khám số 4", "7.30 - 16.30", [
        "Sáng: BS Trần Thanh Hoa; Chiều: BSCKII Vũ Thị Trang",
        "ThS.BS Trần Sinh Cường",
        "Sáng: ThS.BS Nguyễn Thị Minh Nguyệt; Chiều: BS CKII Trần Thị Thanh Hà",
        "Sáng: ThS.BS Lê Thế Kiên; Chiều: BSCKII Vũ Thị Trang",
        "Sáng: ThS.BS Nguyễn Phương Liên; Chiều: BS Trần Thanh Hoa",
        "Khám TC; ThS.BS Nguyễn Đình Hồng Phúc",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 3", "Phòng khám số 5", "6.30 - 16.30", [
        "BSCKII Nguyễn Văn Thực",
        "ThS.BS Nguyễn Thế Nam Huy",
        "Sáng: BS Trần Thanh Hoa; Chiều: ThS.BS Nguyễn Đình Hồng Phúc",
        "Sáng: ThS.BS Nguyễn Đình Hồng Phúc; Chiều: BS Phạm Thị Hoa",
        "ThS.BS Nguyễn Thế Nam Huy",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 3", "Phòng khám số 6", "6.30 - 16.30", [
        "Sáng: ThS.BS Nguyễn Mai Hương; Chiều: TS.BS Ngọ Văn Thanh",
        "ThS.BS Phạm Văn Tùng",
        "ThS.BS Lê Thế Kiên",
        "ThS.BS Đỗ Thị Vân Anh",
        "Sáng: ThS.BS Trần Sinh Cường; Chiều: ThS.BS Phạm Văn Tùng",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 3", "Phòng khám số 7", "6.30 - 16.30", [
        "ThS.BS Lê Quang Huy",
        "BS Đinh Hải Nam",
        "Sáng: ThS.BS Nguyễn Phương Liên; Chiều: BS Đinh Hải Nam",
        "ThS.BS Nguyễn Xuân Từ",
        "ThS.BS Hoàng Minh Lợi",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 3", "Phòng khám số 8", "7.30 - 16.30", [
        "ThS.BS Nguyễn Thị Minh Nguyệt",
        "Sáng: BSCKII Nguyễn Văn Dần; Chiều: BS Trần Thanh Hoa",
        "Sáng: BSCKI Nguyễn Trung Hiếu; Chiều: BS Nguyễn Ngọc Tân",
        "Sáng: ThS.BS Hoàng Minh Lợi; Chiều: BSCKII Phạm Thị An",
        "TS.BS Nguyễn Xuân Tuấn",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 3", "Phòng khám số 9", "7.30 - 16.30", [
        "ThS.BS Hoàng Minh Lợi",
        "Sáng: ThS.BS Nguyễn Phương Liên; Chiều: ThS.BS Lê Thị Thảo",
        "ThS.BS Nguyễn Mai Hương",
        "Sáng: BSCKI Nguyễn Trung Hiếu; Chiều: ThS.BS Nguyễn Thị Minh Nguyệt",
        "Sáng: BSCKI Nguyễn Trung Hiếu; Chiều: ThS.BS Lê Thị Thảo",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 3", "Phòng khám tăng cường 1 (HC)", "7.30 - 16.30", [
        "Sáng: ThS.BS Trần Sinh Cường; Chiều: BS Nguyễn Ngọc Tân",
        "Sáng: BSCKI Nguyễn Trung Hiếu",
        "",
        "BS Trần Thanh Hoa",
        "Sáng: BSCKII Nguyễn Văn Dần",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t21.jpg", "Cơ sở 1", "Khu khám bệnh Tự nguyện 3", "Phòng khám tăng cường 2 (PK 4)", "7.30 - 16.30", [
        "Sáng: ThS.BS Đỗ Thị Vân Anh",
        "Sáng: ThS.BS Hoàng Minh Lợi",
        "",
        "BS Đinh Hải Nam",
        "",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t22.jpg", "Cơ sở 2", "Khu khám bệnh Tự nguyện", "Phòng khám số 306", "7.00 - 16.30", [
        "BS.CKII Lê Thị Hoài Thu",
        "BS.CKII Lê Thị Hoài Thu",
        "BS.CKII Lê Thị Hoài Thu",
        "BS.CKII Lê Thị Hoài Thu",
        "BS.CKII Lê Thị Hoài Thu",
        "Bs Trần Đình Tiến",
        "NGHỈ",
    ]),
    row("source_images/t22.jpg", "Cơ sở 2", "Khu khám bệnh Tự nguyện", "Phòng khám số 309", "7.00 - 16.30", [
        "ThS.Bs Nguyễn Duy Chinh",
        "ThS.Bs Nguyễn Duy Chinh",
        "ThS.Bs Nguyễn Duy Chinh",
        "ThS.Bs Nguyễn Duy Chinh",
        "ThS.Bs Nguyễn Duy Chinh",
        "Bs Trần Đình Tiến",
        "NGHỈ",
    ]),
    row("source_images/t22.jpg", "Cơ sở 2", "Khu khám bệnh Tự nguyện", "Phòng khám số 308", "7.00 - 16.30", [
        "Ts.Bs Trần Thị Linh Tú",
        "Ts.Bs Trần Thị Linh Tú",
        "Ts.Bs Trần Thị Linh Tú",
        "Ts.Bs Trần Thị Linh Tú",
        "Ts.Bs Trần Thị Linh Tú",
        "Bs Trần Đình Tiến",
        "NGHỈ",
    ]),
    row("source_images/t22.jpg", "Cơ sở 2", "Khu khám bệnh Tự nguyện", "Phòng khám số 310", "7.00 - 16.30", [
        "TC",
        "TC",
        "TC",
        "TC",
        "TC",
        "Bs Trần Đình Tiến",
        "NGHỈ",
    ]),
    row("source_images/t22.jpg", "Cơ sở 2", "Khu khám bệnh Tự nguyện", "Phòng khám số 311", "7.30 - 16.30", [
        "ThS.Bs Lê Thùy Ngọc",
        "ThS.Bs Lê Thùy Ngọc",
        "ThS.Bs Lê Thùy Ngọc",
        "ThS.Bs Lê Thùy Ngọc",
        "ThS.Bs Lê Thùy Ngọc",
        "Bs Trần Đình Tiến",
        "NGHỈ",
    ]),
    row("source_images/t23.png", "Cơ sở 2", "Phòng khám Đa khoa", "RHM (P401)", "7.30 - 16.30", [
        "BS Nguyễn Thanh Trà",
        "BS Nguyễn Thanh Trà khám tại CS1(15H)",
        "BS Nguyễn Thanh Trà",
        "BS Nguyễn Thanh Trà khám tại CS1(15H)",
        "BS Nguyễn Thanh Trà",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t23.png", "Cơ sở 2", "Phòng khám Đa khoa", "PHCN (P401)", "7.30 - 16.30", [
        "BSNT. Trần Thị Quỳnh Nga",
        "BSNT. Trần Thị Quỳnh Nga",
        "BSNT. Trần Thị Quỳnh Nga",
        "Sáng: BSNT. Trần Thị Quỳnh Nga; Chiều Nghỉ",
        "Sáng: BSNT. Trần Thị Quỳnh Nga; Chiều Nghỉ",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t23.png", "Cơ sở 2", "Phòng khám Đa khoa", "TMH (P402)", "7.30 - 16.30", [
        "/",
        "/",
        "/",
        "/",
        "/",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t23.png", "Cơ sở 2", "Phòng khám Đa khoa", "PK NHI (P402)", "7.30 - 16.30", [
        "ThS.Bs Dương Thị Thùy Nga",
        "ThS.Bs Dương Thị Thùy Nga",
        "ThS.Bs Dương Thị Thùy Nga",
        "ThS.Bs Dương Thị Thùy Nga",
        "ThS.Bs Dương Thị Thùy Nga",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t23.png", "Cơ sở 2", "Phòng khám Đa khoa", "DA LIỄU (P403)", "7.30 - 16.30", [
        "ThS.Bs Nguyễn Thị Minh Hoa",
        "ThS.Bs Nguyễn Thị Minh Hoa",
        "ThS.Bs Nguyễn Thị Minh Hoa",
        "ThS.Bs Nguyễn Thị Minh Hoa",
        "ThS.Bs Nguyễn Thị Minh Hoa",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t23.png", "Cơ sở 2", "Phòng khám Đa khoa", "Sản- phụ khoa (P403)", "7.30 - 16.30", [
        "Sáng: BSCK II Nguyễn Thị Tuyết Mai; Chiều Nghỉ",
        "Sáng: BSCK II Nguyễn Thị Tuyết Mai; Chiều Nghỉ",
        "Sáng: BSCK II Nguyễn Thị Tuyết Mai; Chiều Nghỉ",
        "Sáng: BSCK II Nguyễn Thị Tuyết Mai; Chiều Nghỉ",
        "Sáng: BSCK II Nguyễn Thị Tuyết Mai; Chiều Nghỉ",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t23.png", "Cơ sở 2", "Phòng khám Đa khoa", "YHCT (P404)", "7.30 - 16.30", [
        "BSNT. Nguyễn Thị Thuận",
        "BSNT. Nguyễn Thị Thuận",
        "BSNT. Nguyễn Thị Thuận",
        "BSNT. Nguyễn Thị Thuận",
        "BSNT. Nguyễn Thị Thuận",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t23.png", "Cơ sở 2", "Phòng khám Đa khoa", "Nội chung - Hô Hấp (P405.A)", "7.30 - 16.30", [
        "ThS.BS Lại Thị Bạch Yến",
        "ThS.BS Lại Thị Bạch Yến",
        "ThS.BS Lại Thị Bạch Yến",
        "ThS.BS Lại Thị Bạch Yến",
        "ThS.BS Lại Thị Bạch Yến",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t23.png", "Cơ sở 2", "Phòng khám Đa khoa", "Nội chung - CXK (P405.B)", "7.30 - 16.31", [
        "ThS.BSNT Phạm Thị Oanh",
        "ThS.BSNT Phạm Thị Oanh",
        "ThS.BSNT Phạm Thị Oanh",
        "ThS.BSNT Phạm Thị Oanh",
        "ThS.BSNT Phạm Thị Oanh",
        "Nghỉ",
        "Nghỉ",
    ], "Thời gian trong ảnh gốc hiển thị 16.31."),
    row("source_images/t23.png", "Cơ sở 2", "Phòng khám Đa khoa", "PK NTM - NT (P405.C)", "7.30 - 16.30", [
        "BS TMCH",
        "BS TMCH",
        "BS TMCH",
        "BS TMCH",
        "BS TMCH",
        "Nghỉ",
        "Nghỉ",
    ]),
    row("source_images/t23.png", "Cơ sở 2", "Phòng khám Đa khoa", "MẮT (P405.D)", "7.30 - 16.30", [
        "BSCKI Nguyễn Thị Huyền",
        "BSCKI Nguyễn Thị Huyền",
        "BSCKI Nguyễn Thị Huyền",
        "BSCKI Nguyễn Thị Huyền",
        "BSCKI Nguyễn Thị Huyền",
        "Nghỉ",
        "Nghỉ",
    ]),
]


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def slugify(value):
    mapping = {
        "ơ": "o",
        "ở": "o",
        "ờ": "o",
        "ợ": "o",
        "ỡ": "o",
        "ớ": "o",
        "ô": "o",
        "ố": "o",
        "ồ": "o",
        "ộ": "o",
        "ỗ": "o",
        "ổ": "o",
        "ă": "a",
        "ằ": "a",
        "ắ": "a",
        "ẵ": "a",
        "ặ": "a",
        "ẳ": "a",
        "â": "a",
        "ầ": "a",
        "ấ": "a",
        "ẫ": "a",
        "ậ": "a",
        "ẩ": "a",
        "ê": "e",
        "ề": "e",
        "ế": "e",
        "ễ": "e",
        "ệ": "e",
        "ể": "e",
        "ư": "u",
        "ừ": "u",
        "ứ": "u",
        "ữ": "u",
        "ự": "u",
        "ử": "u",
        "đ": "d",
        "ị": "i",
        "í": "i",
        "ì": "i",
        "ỉ": "i",
        "ĩ": "i",
        "ụ": "u",
        "ú": "u",
        "ù": "u",
        "ủ": "u",
        "ũ": "u",
        "ạ": "a",
        "á": "a",
        "à": "a",
        "ả": "a",
        "ã": "a",
        "ẹ": "e",
        "é": "e",
        "è": "e",
        "ẻ": "e",
        "ẽ": "e",
        "ọ": "o",
        "ó": "o",
        "ò": "o",
        "ỏ": "o",
        "õ": "o",
        "ý": "y",
        "ỳ": "y",
        "ỷ": "y",
        "ỹ": "y",
        "ỵ": "y",
    }
    s = value.lower()
    for src, dst in mapping.items():
        s = s.replace(src, dst)
    return "".join(ch if ch.isalnum() else "_" for ch in s).strip("_")


def main():
    write_csv(OUT_DIR / "lich_kham_bac_si_2026-06-08_to_2026-06-14.csv", records)

    by_table = {}
    for item in records:
        key = (item["co_so"], item["khu"], item["source_image"])
        by_table.setdefault(key, []).append(item)

    for (co_so, khu, _source_image), rows in by_table.items():
        write_csv(OUT_DIR / f"{slugify(co_so)}__{slugify(khu)}.csv", rows)

    payload = {
        "metadata": {
            "title": "Lịch khám bệnh của các bác sĩ Bệnh viện Tim Hà Nội tuần từ 08/06/2026 - 14/06/2026",
            "source_url": SOURCE_URL,
            "week_start": "2026-06-08",
            "week_end": "2026-06-14",
            "days": [
                {"field": field, "label": label, "date": date}
                for field, label, date in DAYS
            ],
            "record_count": len(records),
            "source_images": sorted({item["source_image"] for item in records}),
            "notes": [
                "Dữ liệu được trích xuất thủ công từ ảnh bảng lịch trên trang nguồn.",
                "Các ô có nhiều dòng trong ảnh được nối bằng dấu ';'.",
                "Bảng Đa khoa cơ sở 2 trong ảnh ghi tiêu đề đến 12/06/2026 nhưng vẫn có cột Thứ 7 và Chủ nhật.",
            ],
        },
        "records": records,
    }
    (OUT_DIR / "lich_kham_bac_si_2026-06-08_to_2026-06-14.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(records)} records to {OUT_DIR}")


if __name__ == "__main__":
    main()
