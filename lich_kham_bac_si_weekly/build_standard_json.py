#!/usr/bin/env python3
import json
import shutil
from pathlib import Path

from build_schedule_data import records as june_records


BASE_DIR = Path(__file__).resolve().parent

FILE_TN1_CS1 = "Lịch khám bệnh Bác sĩ khu TN1 Cơ Sở 1.json"
FILE_TN_CS2 = "Lịch khám bệnh Bác sĩ khu TN Cơ Sở 2.json"
FILE_DA_KHOA_CS2 = "Lịch khám bệnh Bác sĩ Đa Khoa Cơ Sở 2.json"


def clean_cell(value):
    return value.replace("; Chiều:", "\nChiều:").replace("; ", "\n")


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def standard_room(item, saturday_key="thu_7"):
    return {
        "phong_kham": item["phong_kham"],
        "thoi_gian": item["thoi_gian"],
        "thu_2": clean_cell(item["thu_2_2026_06_08"]),
        "thu_3": clean_cell(item["thu_3_2026_06_09"]),
        "thu_4": clean_cell(item["thu_4_2026_06_10"]),
        "thu_5": clean_cell(item["thu_5_2026_06_11"]),
        "thu_6": clean_cell(item["thu_6_2026_06_12"]),
        saturday_key: clean_cell(item["thu_7_2026_06_13"]),
        "chu_nhat": clean_cell(item["chu_nhat_2026_06_14"]),
    }


def da_khoa_room_from_june(item):
    return {
        "phong": item["phong_kham"],
        "thoi_gian": item["thoi_gian"],
        "thu_2": clean_cell(item["thu_2_2026_06_08"]),
        "thu_3": clean_cell(item["thu_3_2026_06_09"]),
        "thu_4": clean_cell(item["thu_4_2026_06_10"]),
        "thu_5": clean_cell(item["thu_5_2026_06_11"]),
        "thu_6": clean_cell(item["thu_6_2026_06_12"]),
        "thu_7": clean_cell(item["thu_7_2026_06_13"]),
        "chu_nhat": clean_cell(item["chu_nhat_2026_06_14"]),
    }


def export_june_08_14():
    out = BASE_DIR / "lich_kham_08-14_thang_6_2026"
    by_khu = {}
    for item in june_records:
        by_khu.setdefault(item["khu"], []).append(item)

    tn1_payload = {
        "tieu_de": "LỊCH KHÁM BỆNH CỦA CÁC BÁC SỸ KHOA KHÁM BỆNH TỰ NGUYỆN",
        "dia_diem": "TẠI BỆNH VIỆN TIM HÀ NỘI - CƠ SỞ 1 - 92 TRẦN HƯNG ĐẠO, HOÀN KIẾM, HÀ NỘI",
        "thoi_gian": "Tuần từ ngày 8-14.6.2026",
        "thong_tin_lien_he": {
            "dat_lich_va_tu_van_24_24": "1900.1082",
            "tu_van_hanh_chinh": "0869032338",
            "website": ["benhvientimhanoi.vn", "benhvientimhanoi.com.vn"],
            "fanpage": "fb.com/BenhVienTimHaNoi.vn",
        },
        "lich_kham": [
            {
                "khoa": "Khoa khám bệnh Tự nguyện 1",
                "danh_sach_phong": [
                    standard_room(item)
                    for item in by_khu["Khu khám bệnh Tự nguyện 1"]
                ],
            },
            {
                "khoa": "Khoa khám bệnh Tự nguyện 3",
                "danh_sach_phong": [
                    standard_room(item)
                    for item in by_khu["Khu khám bệnh Tự nguyện 3"]
                ],
            },
        ],
    }
    write_json(out / FILE_TN1_CS1, tn1_payload)

    tn_cs2_payload = {
        "tieu_de": "LỊCH LÀM VIỆC CỦA CÁC BÁC SỸ KHU KHÁM BỆNH TỰ NGUYỆN",
        "dia_diem": "TẠI BỆNH VIỆN TIM HÀ NỘI - CƠ SỞ 2 - 695 LẠC LONG QUÂN - PHƯỜNG TÂY HỒ - HÀ NỘI",
        "thoi_gian": "Tuần từ ngày 08/06/2026 đến ngày 14/06/2026",
        "thong_tin_lien_he": {
            "dat_lich": "19001082",
            "tu_van_hanh_chinh": "02439427791",
            "tu_van_24_24h": "0969655335",
            "website": "benhvientimhanoi.vn",
            "fanpage": "fb.com/BenhVienTimHaNoi.vn",
        },
        "dich_vu": "Dịch vụ khám bệnh theo yêu cầu",
        "lich_kham": [
            standard_room(item, saturday_key="thu_7_tn_muc_3")
            for item in by_khu["Khu khám bệnh Tự nguyện"]
        ],
    }
    write_json(out / FILE_TN_CS2, tn_cs2_payload)

    da_khoa_payload = {
        "tieu_de": "LỊCH LÀM VIỆC CỦA CÁC BÁC SỸ PHÒNG KHÁM ĐA KHOA",
        "dia_diem": "TẠI BỆNH VIỆN TIM HÀ NỘI - CƠ SỞ 2 - 695 LẠC LONG QUÂN, TÂY HỒ, HÀ NỘI",
        "thoi_gian": "Tuần từ ngày 8/6/2026 đến ngày 12/6/2026",
        "thong_tin_lien_he": {
            "so_dien_thoai": "0961.972.097",
            "ghi_chu": "(Giờ hành chính các ngày trong tuần từ thứ 2 đến thứ 6)",
        },
        "lich_kham": [
            da_khoa_room_from_june(item)
            for item in by_khu["Phòng khám Đa khoa"]
        ],
    }
    write_json(out / FILE_DA_KHOA_CS2, da_khoa_payload)

    image_dir = out / "source_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    for image_name in ["t21.jpg", "t22.jpg", "t23.png"]:
        src = BASE_DIR / "source_images" / image_name
        if src.exists():
            shutil.copy2(src, image_dir / image_name)


def july_room(phong_kham, thoi_gian, thu_2, thu_3, thu_4, thu_5, thu_6, thu_7, chu_nhat):
    return {
        "phong_kham": phong_kham,
        "thoi_gian": thoi_gian,
        "thu_2": thu_2,
        "thu_3": thu_3,
        "thu_4": thu_4,
        "thu_5": thu_5,
        "thu_6": thu_6,
        "thu_7": thu_7,
        "chu_nhat": chu_nhat,
    }


def july_da_khoa_room(phong, thoi_gian, thu_2, thu_3, thu_4, thu_5, thu_6, thu_7, chu_nhat):
    return {
        "phong": phong,
        "thoi_gian": thoi_gian,
        "thu_2": thu_2,
        "thu_3": thu_3,
        "thu_4": thu_4,
        "thu_5": thu_5,
        "thu_6": thu_6,
        "thu_7": thu_7,
        "chu_nhat": chu_nhat,
    }


def export_july_06_12():
    out = BASE_DIR / "lich_kham_06-12_thang_7_2026"
    tn1_payload = {
        "tieu_de": "LỊCH KHÁM BỆNH CỦA CÁC BÁC SỸ KHOA KHÁM BỆNH TỰ NGUYỆN",
        "dia_diem": "TẠI BỆNH VIỆN TIM HÀ NỘI - CƠ SỞ 1 - 92 TRẦN HƯNG ĐẠO, HOÀN KIẾM, HÀ NỘI",
        "thoi_gian": "Tuần từ ngày 6.7-12.7.2026",
        "thong_tin_lien_he": {
            "dat_lich_va_tu_van_24_24": "1900.1082",
            "tu_van_hanh_chinh": "0869032338",
            "website": ["benhvientimhanoi.vn", "benhvientimhanoi.com.vn"],
            "fanpage": "fb.com/BenhVienTimHaNoi.vn",
        },
        "lich_kham": [
            {
                "khoa": "Khoa khám bệnh Tự nguyện 1",
                "danh_sach_phong": [
                    july_room("Phòng khám số 1", "7.30 - 16.30", "TS.BS Phạm Như Hùng", "TS.BS Phạm Như Hùng", "Sáng: ThS.BS Nguyễn Thị Việt Nga\nChiều: BSCKII Vũ Thị Trang", "TS.BS Phạm Như Hùng", "Sáng: BSCKII Phạm Thị An\nChiều: BSCKII Nguyễn Văn Thực", "Nghỉ", "ThS.BS Nguyễn Đình Hồng Phúc"),
                    july_room("Phòng khám số 2", "7.30 - 16.30", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "Nghỉ", "SAT: ThS.BS Nguyễn Thị Quỳnh Trang"),
                    july_room("Phòng khám số 3", "7.00 - 16.30", "TS.BS Bùi Thị Thanh Hà", "TS.BS Nguyễn Xuân Tuấn", "TS.BS Bùi Thị Thanh Hà", "TS.BS Đinh Quang Huy", "TS.BS Bùi Thị Thanh Hà", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 4", "7.30 - 16.30", "Sáng: TS.BS Hoàng Văn Chiêu\nBSCKII Nguyễn Văn Dần", "TS.BS Hà Mai Hương", "Sáng: TS.BS Hoàng Văn Chiêu\nChiều: TS.BS Nguyễn Thị Quỳnh Trang", "TS.BS Hà Mai Hương", "Sáng: TS.BS Hoàng Văn Chiêu\nChiều: TS.BS Nguyễn Thị Thu Thủy", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 5", "7.00 - 16.30", "TS.BS Trần Thị Ngọc Lan", "ThS.BS Nguyễn Xuân Tú", "BSCKII Nguyễn Văn Dần", "Sáng: ThS.BS Nguyễn Thị Việt Nga\nChiều: TS.BS Ngô Văn Thanh", "TS.BS Hà Mai Hương", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 6", "7.30 - 16.30", "ThS.BS Nguyễn Thị Việt Nga", "BSCKII Phạm Thị An", "TS.BS Nguyễn Thị Thu Thủy", "BSCKII Nguyễn Văn Thực", "BSCKII Vũ Thị Trang", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 7", "7.00 - 16.00", "TS.BS Nguyễn Xuân Tuấn", "Sáng: TS.BS Trần Thị An\nChiều: TS.BS Trần Thị Ngọc Lan", "ThS.BS Nguyễn Xuân Tú", "TS.BS Trần Thị Ngọc Lan", "ThS.BS Nguyễn Thị Quỳnh Trang", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 8", "7.00 - 16.00", "TS.BS Đinh Quang Huy", "TS.BS Nguyễn Thị Thu Thủy", "Sáng: TS.BS Trần Thị An\nChiều: TS.BS Nguyễn Xuân Tuấn", "TS.BS Nguyễn Thị Thu Thủy", "TS.BS Trần Thị An", "Nghỉ", "Nghỉ"),
                ],
            },
            {
                "khoa": "Khoa khám bệnh Tự nguyện 3",
                "danh_sach_phong": [
                    july_room("Phòng khám số 1", "7.30 - 16.30", "ThS.BS Võ Thị Ngọc Anh", "ThS.BS Nguyễn Danh Sen", "ThS.BS Phạm Văn Tùng", "ThS.BS Nguyễn Danh Sen", "BS CKII Trần Thị Thanh Hà", "ThS.BS Nguyễn Đăng Dương", "Nghỉ"),
                    july_room("Phòng khám số 2", "7.30 - 16.30", "Sáng: ThS.BS Nguyễn Xuân Tú\nChiều: BS CKII Trần Thị Thanh Hà", "Sáng: BSCKII Nguyễn Văn Dần\nChiều: ThS.BS Nguyễn Đình Hồng Phúc", "ThS.BS. Phạm Đăng Anh", "Sáng: BSCKI Nguyễn Trung Hiếu\nChiều: ThS.BS Nguyễn Phương Liên", "Sáng: ThS.BS Nguyễn Mai Hương\nChiều: ThS.BS Nguyễn Đình Hồng Phúc", "ThS.BS Lê Thế Kiên", "Nghỉ"),
                    july_room("Phòng khám số 3", "7.30 - 16.30", "ThS.BS Nguyễn Quốc Hùng", "BSCKI Đào Thị Thu Hà", "ThS. Bs Trần Đắc Long", "TS.BS Nguyễn Toàn Thắng", "BSCKI Đào Thị Thu Hà", "SAT: ThS.BS Trần Sinh Cường", "Nghỉ"),
                    july_room("Phòng khám số 4", "7.30 - 16.30", "Sáng: ThS.BS Trần Sinh Cường\nChiều: BS Nguyễn Ngọc Tân", "ThS.BS Nguyễn Mai Hương", "BS Đinh Hải Nam", "BS Trần Thanh Hoa", "Sáng: ThS.BS Phạm Văn Tùng\nChiều: BS Trần Thanh Hoa", "Khám TC\nThS.BS Lê Thị Thảo", "Nghỉ"),
                    july_room("Phòng khám số 5", "6.30 - 16.30", "BSCKII Nguyễn Văn Thực", "ThS.BS Nguyễn Thế Nam Huy", "ThS.BS Hoàng Minh Lợi", "Sáng: ThS.BS Trần Sinh Cường\nChiều: ThS.BS Lê Quang Huy", "ThS.BS Nguyễn Thế Nam Huy", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 6", "6.30 - 16.30", "ThS.BS Nguyễn Đình Hồng Phúc", "BS Đinh Hải Nam", "ThS.BS Đỗ Thị Vân Anh", "ThS.BS Nguyễn Đình Hồng Phúc", "Sáng: ThS.BS Lê Thế Kiên\nChiều: ThS.BS Nguyễn Phương Liên", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 7", "6.30 - 16.30", "ThS.BS Phạm Văn Tùng", "BS Trần Thanh Hoa", "ThS.BS Lê Thế Kiên", "ThS.BS Lê Thị Thảo", "BS Đinh Hải Nam", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 8", "7.30 - 16.30", "Sáng: ThS.BS Lê Quang Huy\nChiều: TS.BS Ngô Văn Thanh", "Sáng: BSCKII Vũ Thị Trang\nChiều: ThS.BS Trần Sinh Cường", "ThS.BS Trần Sinh Cường", "Sáng: ThS.BS Nguyễn Thị Minh Nguyệt\nChiều: BS. Nguyễn Ngọc Tân", "TS.BS Nguyễn Xuân Tuấn", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 9", "7.30 - 16.30", "ThS.BS Lê Thị Thảo", "ThS.BS Đỗ Thị Vân Anh", "Sáng: ThS.BS Nguyễn Phương Liên\nChiều: BS Chu Thị Hằng", "BSCKII Nguyễn Văn Dần", "Sáng: BSCKII Nguyễn Văn Dần\nChiều: ThS.BS Phạm Đăng Anh", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám tăng cường 1 (HC)", "7.30 - 16.30", "Sáng: BS Trần Thanh Hoa", "Sáng: ThS.BS Hoàng Minh Lợi", "Sáng: ThS.BS Nguyễn Đình Hồng Phúc", "Sáng: ThS.BS Lê Thế Kiên", "Sáng: ThS.BS Hoàng Minh Lợi", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám tăng cường 2 (PK 4)", "7.30 - 16.30", "Sáng: ThS.BS Nguyễn Phương Liên", "Sáng: ThS.BS Lê Thế Kiên", "", "", "Sáng: ThS.BS Trần Sinh Cường", "Nghỉ", "Nghỉ"),
                ],
            },
        ],
    }
    write_json(out / FILE_TN1_CS1, tn1_payload)

    tn_cs2_payload = {
        "tieu_de": "LỊCH LÀM VIỆC CỦA CÁC BÁC SỸ KHU KHÁM BỆNH TỰ NGUYỆN",
        "dia_diem": "TẠI BỆNH VIỆN TIM HÀ NỘI - CƠ SỞ 2 - 695 LẠC LONG QUÂN - PHƯỜNG TÂY HỒ - HÀ NỘI",
        "thoi_gian": "Tuần từ ngày 06/07/2026 đến ngày 12/07/2026",
        "thong_tin_lien_he": {
            "dat_lich": "19001082",
            "tu_van_hanh_chinh": "02439427791",
            "tu_van_24_24h": "0969655335",
            "website": "benhvientimhanoi.vn",
            "fanpage": "fb.com/BenhVienTimHaNoi.vn",
        },
        "dich_vu": "Dịch vụ khám bệnh theo yêu cầu",
        "lich_kham": [
            {
                "phong_kham": "Phòng khám số 306",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "BS.CKII Lê Thị Hoài Thu",
                "thu_3": "BS.CKII Lê Thị Hoài Thu",
                "thu_4": "BS.CKII Lê Thị Hoài Thu",
                "thu_5": "BS.CKII Lê Thị Hoài Thu",
                "thu_6": "BS.CKII Lê Thị Hoài Thu",
                "thu_7_tn_muc_3": "Bs Phan Thành Nam",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 309",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "Ths.Bs Nguyễn Duy Chinh",
                "thu_3": "Ths.Bs Nguyễn Duy Chinh",
                "thu_4": "Ths.Bs Nguyễn Duy Chinh",
                "thu_5": "Ths.Bs Nguyễn Duy Chinh",
                "thu_6": "Ths.Bs Nguyễn Duy Chinh",
                "thu_7_tn_muc_3": "Bs Phan Thành Nam",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 308",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "Ts.Bs Trần Thị Linh Tú",
                "thu_3": "Ts.Bs Trần Thị Linh Tú",
                "thu_4": "Ts.Bs Trần Thị Linh Tú",
                "thu_5": "Ts.Bs Trần Thị Linh Tú",
                "thu_6": "Ts.Bs Trần Thị Linh Tú",
                "thu_7_tn_muc_3": "Bs Phan Thành Nam",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 310",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "TC",
                "thu_3": "TC",
                "thu_4": "TC",
                "thu_5": "TC",
                "thu_6": "TC",
                "thu_7_tn_muc_3": "Bs Phan Thành Nam",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 311",
                "thoi_gian": "7.30 - 16.30",
                "thu_2": "Ths.Bs Lê Thùy Ngọc",
                "thu_3": "Ths.Bs Lê Thùy Ngọc",
                "thu_4": "Ths.Bs Lê Thùy Ngọc",
                "thu_5": "Ths.Bs Lê Thùy Ngọc",
                "thu_6": "Ths.Bs Lê Thùy Ngọc",
                "thu_7_tn_muc_3": "Bs Phan Thành Nam",
                "chu_nhat": "NGHỈ",
            },
        ],
    }
    write_json(out / FILE_TN_CS2, tn_cs2_payload)

    da_khoa_payload = {
        "tieu_de": "LỊCH LÀM VIỆC CỦA CÁC BÁC SỸ PHÒNG KHÁM ĐA KHOA",
        "dia_diem": "TẠI BỆNH VIỆN TIM HÀ NỘI - CƠ SỞ 2 - 695 LẠC LONG QUÂN, TÂY HỒ, HÀ NỘI",
        "thoi_gian": "Tuần từ ngày 6/7/2026 đến ngày 10/7/2026",
        "thong_tin_lien_he": {
            "so_dien_thoai": "0961.972.097",
            "ghi_chu": "(Giờ hành chính các ngày trong tuần từ thứ 2 đến thứ 6)",
        },
        "lich_kham": [
            july_da_khoa_room("RHM (P401)", "7.30 - 16.30", "BS Nguyễn Thanh Trà", "BS Nguyễn Thanh Trà\nkhám tại CS1(15H)", "BS Nguyễn Thanh Trà", "BS Nguyễn Thanh Trà\nkhám tại CS1(15H)", "BS Nguyễn Thanh Trà", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("PHCN (P401)", "7.30 - 16.30", "BSNT. Trần Thị Quỳnh Nga", "BSNT. Trần Thị Quỳnh Nga", "BSNT. Trần Thị Quỳnh Nga", "BSNT. Trần Thị Quỳnh Nga", "Sáng\nBSNT. Trần Thị Quỳnh Nga\nChiều nghỉ", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("TMH (P402)", "7.30 - 16.30", "Nghỉ", "Nghỉ", "Nghỉ", "Nghỉ", "Nghỉ", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("PK NHI (P402)", "7.30 - 16.30", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("DA LIỄU (P403)", "7.30 - 16.30", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("Sản- phụ khoa (P403)", "7.30 - 16.30", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("YHCT (P404)", "7.30 - 16.30", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("Nội chung - Hô Hấp (P405.A)", "7.30 - 16.30", "Ths.BS Lại Thị Bạch Yến", "Ths.BS Lại Thị Bạch Yến", "Ths.BS Lại Thị Bạch Yến", "Ths.BS Lại Thị Bạch Yến", "Nghỉ", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("Nội chung - CXK (P405.B)", "7.30 - 16.31", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("PK NTM - NT (P405.C)", "7.30 - 16.30", "BS TMCH", "BS TMCH", "BS TMCH", "BS TMCH", "BS TMCH", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("MẮT (P405.D)", "7.30 - 16.30", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "Nghỉ", "Nghỉ"),
        ],
    }
    write_json(out / FILE_DA_KHOA_CS2, da_khoa_payload)


def export_june29_july05():
    out = BASE_DIR / "lich_kham_29-05_thang_6_7_2026"
    tn1_payload = {
        "tieu_de": "LỊCH KHÁM BỆNH CỦA CÁC BÁC SỸ KHOA KHÁM BỆNH TỰ NGUYỆN",
        "dia_diem": "TẠI BỆNH VIỆN TIM HÀ NỘI - CƠ SỞ 1 - 92 TRẦN HƯNG ĐẠO, HOÀN KIẾM, HÀ NỘI",
        "thoi_gian": "Tuần từ ngày 29.6-5.7.2026",
        "thong_tin_lien_he": {
            "dat_lich_va_tu_van_24_24": "1900.1082",
            "tu_van_hanh_chinh": "0869032338",
            "website": ["benhvientimhanoi.vn", "benhvientimhanoi.com.vn"],
            "fanpage": "fb.com/BenhVienTimHaNoi.vn",
        },
        "lich_kham": [
            {
                "khoa": "Khoa khám bệnh Tự nguyện 1",
                "danh_sach_phong": [
                    july_room("Phòng khám số 1", "7.30 - 16.30", "TS.BS Phạm Như Hùng", "TS.BS Phạm Như Hùng", "TS.BS Phạm Như Hùng", "TS.BS Phạm Như Hùng", "TS.BS Phạm Như Hùng", "Nghỉ", "ThS.BS Trần Ngọc Dũng"),
                    july_room("Phòng khám số 2", "7.30 - 16.30", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "Nghỉ", "SAT: ThS.BS Trần Sinh Cường"),
                    july_room("Phòng khám số 3", "7.00 - 16.30", "TS.BS Bùi Thị Thanh Hà", "TS.BS Nguyễn Xuân Tuấn", "TS.BS Bùi Thị Thanh Hà", "TS.BS Đinh Quang Huy", "TS.BS Bùi Thị Thanh Hà", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 4", "7.30 - 16.30", "Sáng: TS.BS Hoàng Văn\nChiều: BSCKII Phạm Thị An", "TS.BS Hà Mai Hương", "Sáng: TS.BS Hoàng Văn\nChiều: ThS.BS Nguyễn Thị Quỳnh Trang", "TS.BS Hà Mai Hương", "Sáng: TS.BS Hoàng Văn\nChiều: TS.BS Trần Thị Ngọc Lan", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 5", "7.00 - 16.30", "TS.BS Trần Thị Ngọc Lan", "ThS.BS Nguyễn Xuân Từ", "BSCKII Nguyễn Văn Dần", "Sáng: ThS.BS Nguyễn Thị Việt Nga\nChiều: TS.BS Ngô Văn Thanh", "TS.BS Hà Mai Hương", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 6", "7.30 - 16.30", "ThS.BS Nguyễn Thị Việt Nga", "BSCKII Phạm Thị An", "TS.BS Nguyễn Thị Thu Thủy", "BSCKII Nguyễn Văn Thực", "ThS.BS Nguyễn Thị Quỳnh Trang", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 7", "7.00 - 16.00", "TS.BS Nguyễn Xuân Tuấn", "TS.BS Trần Thị An", "ThS.BS Nguyễn Xuân Từ", "TS.BS Trần Thị Ngọc Lan", "BSCKII Vũ Thị Trang", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 8", "7.00 - 16.00", "TS.BS Đinh Quang Huy", "TS.BS Nguyễn Thị Thu Thủy", "Sáng: TS.BS Trần Thị An\nChiều: BSCKII Vũ Thị Trang", "Sáng: BS CKII Phạm Quang Huy\nChiều: ThS.BS Nguyễn Thị Quỳnh Trang", "TS.BS Trần Thị An", "Nghỉ", "Nghỉ"),
                ],
            },
            {
                "khoa": "Khoa khám bệnh Tự nguyện 3",
                "danh_sach_phong": [
                    july_room("Phòng khám số 1", "7.30 - 16.30", "ThS.BS Võ Thị Ngọc Anh", "ThS.BS Nguyễn Danh Sen", "ThS.BS Võ Thị Ngọc Anh", "ThS.BS Lê Thế Kiên", "BS CKII Trần Thị Thanh Hà", "ThS.BS Nguyễn Thế Nam Huy", "Nghỉ"),
                    july_room("Phòng khám số 2", "7.30 - 16.30", "ThS.BS Nguyễn Xuân Từ", "BS Đinh Hải Nam", "ThS.BS. Phạm Đăng Anh", "Sáng: ThS.BS Trần Sinh Cường\nChiều: ThS.BS. Phạm Đăng Anh", "Sáng: BSCKII Phạm Thị An\nChiều: ThS.BS. Phạm Đăng Anh", "BSCKI Nguyễn Trung Hiếu", "Nghỉ"),
                    july_room("Phòng khám số 3", "7.30 - 16.30", "ThS.BS Nguyễn Toàn Thắng", "ThS. Bs Trần Đắc Long", "ThS.BS Nguyễn Quốc Hùng", "ThS.BS Nguyễn Toàn Thắng", "BSCKI Đào Thị Thu Hà", "SAT: TS.BS Trần Thị Ngọc Lan", "Nghỉ"),
                    july_room("Phòng khám số 4", "7.30 - 16.30", "Sáng: ThS.BS Trần Sinh Cường\nChiều: BS Trần Thanh Hoa", "BS Trần Thanh Hoa", "Sáng: BSCKII Vũ Thị Trang\nChiều: ThS.BS Nguyễn Đình Hồng Phúc", "Sáng: ThS.BS Lê Thị Thảo\nChiều: ThS.BS Nguyễn Thị Minh Nguyệt", "Sáng: ThS.BS Nguyễn Phương Liên\nChiều: ThS.BS Lê Thị Thảo", "Khám TC\nThS.BS Lê Thế Kiên", "Nghỉ"),
                    july_room("Phòng khám số 5", "6.30 - 16.30", "BSCKII Nguyễn Văn Thực", "ThS.BS Nguyễn Thế Nam Huy", "ThS.BS Lê Quang Huy", "Sáng: ThS.BS Nguyễn Đình Hồng Phúc\nChiều: BS. Nguyễn Ngọc Tân", "ThS.BS Nguyễn Thế Nam Huy", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 6", "6.30 - 16.30", "Sáng: ThS.BS Lê Thị Thảo\nChiều: BS CKII Trần Thị Thanh Hà", "Sáng: ThS.BS Hoàng Minh Lợi\nChiều: ThS.BS Đỗ Thị Vân Anh", "Sáng: BS Trần Thanh Hoa\nChiều: BS Đinh Hải Nam", "Sáng: ThS.BS Nguyễn Danh Sen\nChiều: BSCKII Vũ Thị Trang", "BS Đinh Hải Nam", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 7", "6.30 - 16.30", "ThS.BS Phạm Văn Tùng", "ThS.BS Trần Sinh Cường", "Sáng: ThS.BS Lê Thị Thảo\nChiều: ThS.BS Nguyễn Phương Liên", "ThS.BS Nguyễn Xuân Từ", "ThS.BS Lê Thế Kiên", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 8", "7.30 - 16.30", "Sáng: ThS.BS Hoàng Minh Lợi\nChiều: ThS.BS Nguyễn Mai Hương", "ThS.BS Nguyễn Thị Minh Nguyệt", "Sáng: ThS.BS Phạm Văn Tùng\nChiều: BS Phạm Thị Hoa", "Sáng: ThS.BS Nguyễn Thị Quỳnh Trang\nChiều: ThS.BS Lê Quang Huy", "TS.BS Nguyễn Xuân Tuấn", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 9", "7.30 - 16.30", "Sáng: ThS.BS Nguyễn Phương Liên\nChiều: TS.BS Ngô Văn Thanh", "ThS.BS Nguyễn Mai Hương", "Sáng: ThS.BS Nguyễn Thị Minh Nguyệt\nChiều: ThS.BS Phạm Văn Tùng", "ThS.BS Nguyễn Phương Liên", "Sáng: ThS.BS Nguyễn Thị Minh Nguyệt\nChiều: ThS.BS Trần Sinh Cường", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám tăng cường 1 (HC)", "7.30 - 16.30", "Sáng: ThS.BS Nguyễn Đình Hồng Phúc", "Sáng: ThS.BS Phạm Văn Tùng", "Sáng: BS Đinh Hải Nam", "ThS.BS Đỗ Thị Vân Anh", "Sáng: BSCKI Nguyễn Trung Hiếu", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám tăng cường 2 (PK 4)", "7.30 - 16.30", "", "Sáng: BSCKI Nguyễn Trung Hiếu", "", "", "", "Nghỉ", "Nghỉ"),
                ],
            },
        ],
    }
    write_json(out / FILE_TN1_CS1, tn1_payload)

    tn_cs2_payload = {
        "tieu_de": "LỊCH LÀM VIỆC CỦA CÁC BÁC SỸ KHU KHÁM BỆNH TỰ NGUYỆN",
        "dia_diem": "TẠI BỆNH VIỆN TIM HÀ NỘI - CƠ SỞ 2 - 695 LẠC LONG QUÂN - PHƯỜNG TÂY HỒ - HÀ NỘI",
        "thoi_gian": "Tuần từ ngày 29/06/2026 đến ngày 05/07/2026",
        "thong_tin_lien_he": {
            "dat_lich": "19001082",
            "tu_van_hanh_chinh": "02439427791",
            "tu_van_24_24h": "0969655335",
            "website": "benhvientimhanoi.vn",
            "fanpage": "fb.com/BenhVienTimHaNoi.vn",
        },
        "dich_vu": "Dịch vụ khám bệnh theo yêu cầu",
        "lich_kham": [
            {
                "phong_kham": "Phòng khám số 306",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "BS.CKII Lê Thị Hoài Thu",
                "thu_3": "BS.CKII Lê Thị Hoài Thu",
                "thu_4": "BS.CKII Lê Thị Hoài Thu",
                "thu_5": "BS.CKII Lê Thị Hoài Thu",
                "thu_6": "BS.CKII Lê Thị Hoài Thu",
                "thu_7_tn_muc_3": "Bs Nguyễn Đình Phúc",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 309",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "Ths.Bs Nguyễn Duy Chinh",
                "thu_3": "Ths.Bs Nguyễn Duy Chinh",
                "thu_4": "Ths.Bs Nguyễn Duy Chinh",
                "thu_5": "Ths.Bs Nguyễn Duy Chinh",
                "thu_6": "Ths.Bs Nguyễn Duy Chinh",
                "thu_7_tn_muc_3": "Bs Nguyễn Đình Phúc",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 308",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "Ts.Bs Trần Thị Linh Tú",
                "thu_3": "Ts.Bs Trần Thị Linh Tú",
                "thu_4": "Ts.Bs Trần Thị Linh Tú",
                "thu_5": "Ts.Bs Trần Thị Linh Tú",
                "thu_6": "Ts.Bs Trần Thị Linh Tú",
                "thu_7_tn_muc_3": "Bs Nguyễn Đình Phúc",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 310",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "TC",
                "thu_3": "TC",
                "thu_4": "TC",
                "thu_5": "TC",
                "thu_6": "TC",
                "thu_7_tn_muc_3": "Bs Nguyễn Đình Phúc",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 311",
                "thoi_gian": "7.30 - 16.30",
                "thu_2": "Ths.Bs Lê Thùy Ngọc",
                "thu_3": "Ths.Bs Lê Thùy Ngọc",
                "thu_4": "Ths.Bs Lê Thùy Ngọc",
                "thu_5": "Ths.Bs Lê Thùy Ngọc",
                "thu_6": "Ths.Bs Lê Thùy Ngọc",
                "thu_7_tn_muc_3": "Bs Nguyễn Đình Phúc",
                "chu_nhat": "NGHỈ",
            },
        ],
    }
    write_json(out / FILE_TN_CS2, tn_cs2_payload)

    da_khoa_payload = {
        "tieu_de": "LỊCH LÀM VIỆC CỦA CÁC BÁC SỸ PHÒNG KHÁM ĐA KHOA",
        "dia_diem": "TẠI BỆNH VIỆN TIM HÀ NỘI - CƠ SỞ 2 - 695 LẠC LONG QUÂN, TÂY HỒ, HÀ NỘI",
        "thoi_gian": "Tuần từ ngày 29/6/2026 đến ngày 03/7/2026",
        "thong_tin_lien_he": {
            "so_dien_thoai": "0961.972.097",
            "ghi_chu": "(Giờ hành chính các ngày trong tuần từ thứ 2 đến thứ 6)",
        },
        "lich_kham": [
            july_da_khoa_room("RHM (P401)", "7.30 - 16.30", "BS Nguyễn Thanh Trà", "BS Nguyễn Thanh Trà\nkhám tại CS1(15H)", "BS Nguyễn Thanh Trà", "BS Nguyễn Thanh Trà\nkhám tại CS1(15H)", "BS Nguyễn Thanh Trà", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("PHCN (P401)", "7.30 - 16.30", "BSNT. Trần Thị Quỳnh Nga", "BSNT. Trần Thị Quỳnh Nga", "BSNT. Trần Thị Quỳnh Nga", "BSNT. Trần Thị Quỳnh Nga", "Sáng\nBSNT. Trần Thị Quỳnh Nga\nChiều nghỉ", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("TMH (P402)", "7.30 - 16.30", "/", "/", "Ths.Bs Linh Thế Cường", "Ths.Bs Linh Thế Cường", "Ths.Bs Linh Thế Cường", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("PK NHI (P402)", "7.30 - 16.30", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("DA LIỄU (P403)", "7.30 - 16.30", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("Sản- phụ khoa (P403)", "7.30 - 16.30", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("YHCT (P404)", "7.30 - 16.30", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("Nội chung - Hô Hấp (P405.A)", "7.30 - 16.30", "Ths.BS Lại Thị Bạch Yến", "Ths.BS Lại Thị Bạch Yến", "Ths.BS Lại Thị Bạch Yến", "Ths.BS Lại Thị Bạch Yến", "Ths.BS Lại Thị Bạch Yến", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("Nội chung - CXK (P405.B)", "7.30 - 16.31", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("PK NTM - NT (P405.C)", "7.30 - 16.30", "BS TMCH", "BS TMCH", "BS TMCH", "BS TMCH", "BS TMCH", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("MẮT (P405.D)", "7.30 - 16.30", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "Nghỉ", "Nghỉ"),
        ],
    }
    write_json(out / FILE_DA_KHOA_CS2, da_khoa_payload)


def export_june22_june28():
    out = BASE_DIR / "lich_kham_22-28_thang_6_2026"
    tn1_payload = {
        "tieu_de": "LỊCH KHÁM BỆNH CỦA CÁC BÁC SỸ KHOA KHÁM BỆNH TỰ NGUYỆN",
        "dia_diem": "TẠI BỆNH VIỆN TIM HÀ NỘI - CƠ SỞ 1 - 92 TRẦN HƯNG ĐẠO, HOÀN KIẾM, HÀ NỘI",
        "thoi_gian": "Tuần từ ngày 22-28.6.2026",
        "thong_tin_lien_he": {
            "dat_lich_va_tu_van_24_24": "1900.1082",
            "tu_van_hanh_chinh": "0869032338",
            "website": ["benhvientimhanoi.vn", "benhvientimhanoi.com.vn"],
            "fanpage": "fb.com/BenhVienTimHaNoi.vn",
        },
        "lich_kham": [
            {
                "khoa": "Khoa khám bệnh Tự nguyện 1",
                "danh_sach_phong": [
                    july_room("Phòng khám số 1", "7.30 - 16.30", "TS.BS Phạm Như Hùng", "TS.BS Phạm Như Hùng", "TS.BS Phạm Như Hùng", "TS.BS Phạm Như Hùng", "TS.BS Phạm Như Hùng", "Nghỉ", "TS.BS Ngọ Văn Thanh"),
                    july_room("Phòng khám số 2", "7.30 - 16.30", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "Nghỉ", "SAT: ThS.BS Lê Quang Huy"),
                    july_room("Phòng khám số 3", "7.00 - 16.30", "TS.BS Bùi Thị Thanh Hà", "TS.BS Nguyễn Xuân Tuấn", "TS.BS Bùi Thị Thanh Hà", "TS.BS Đinh Quang Huy", "Sáng: TS.BS Bùi Thị Thanh Hà\nChiều: TS.BS Nguyễn Thị Thu Thủy", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 4", "7.30 - 16.30", "Sáng: TS.BS Hoàng Văn\nChiều: TS.BS Ngọ Văn Thanh", "TS.BS Hà Mai Hương", "Sáng: TS.BS Hoàng Văn\nChiều: ThS.BS Nguyễn Thị Quỳnh Trang", "TS.BS Hà Mai Hương", "Sáng: TS.BS Hoàng Văn\nChiều: TS.BS Trần Thị Ngọc Lan", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 5", "7.00 - 16.30", "TS.BS Trần Thị Ngọc Lan", "ThS.BS Nguyễn Xuân Từ", "BSCKII Nguyễn Văn Dần", "ThS.BS Nguyễn Thị Việt Nga", "TS.BS Hà Mai Hương", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 6", "7.30 - 16.30", "ThS.BS Nguyễn Thị Việt Nga", "BSCKII Phạm Thị An", "TS.BS Nguyễn Thị Thu Thủy", "BSCKII Nguyễn Văn Thực", "ThS.BS Nguyễn Thị Quỳnh Trang", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 7", "7.00 - 16.00", "TS.BS Nguyễn Xuân Tuấn", "TS.BS Trần Thị An", "ThS.BS Nguyễn Xuân Từ", "TS.BS Trần Thị Ngọc Lan", "BSCKII Vũ Thị Trang", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 8", "7.00 - 16.00", "TS.BS Đinh Quang Huy", "TS.BS Nguyễn Thị Thu Thủy", "Sáng: TS.BS Trần Thị An\nChiều: BSCKII Vũ Thị Trang", "BS CKII Phạm Quang Huy", "Sáng: TS.BS Nguyễn Thị Thu Thủy", "Nghỉ", "Nghỉ"),
                ],
            },
            {
                "khoa": "Khoa khám bệnh Tự nguyện 3",
                "danh_sach_phong": [
                    july_room("Phòng khám số 1", "7.30 - 16.30", "ThS.BS Hoàng Minh Lợi", "BS Đinh Hải Nam", "Sáng: ThS.BS Trần Sinh Cường\nChiều: ThS.BS Nguyễn Đình Hồng Phúc", "ThS.BS Nguyễn Danh Sen", "BS CKII Trần Thị Thanh Hà", "ThS.BS Phạm Hùng Cường", "Nghỉ"),
                    july_room("Phòng khám số 2", "7.30 - 16.30", "Sáng: ThS.BS Nguyễn Thị Minh Nguyệt\nChiều: BS CKII Trần Thị Thanh Hà", "Sáng: ThS.BS Nguyễn Danh Sen\nChiều: ThS.BS Nguyễn Mai Hương", "Sáng: BS Trần Thanh Hoa\nChiều: ThS.BS. Phạm Đăng Anh", "Sáng: ThS.BS Trần Sinh Cường\nChiều: ThS.BS Nguyễn Đình Hồng Phúc", "ThS.BS Hoàng Minh Lợi", "ThS.BS Đỗ Thị Vân Anh", "Nghỉ"),
                    july_room("Phòng khám số 3", "7.30 - 16.30", "ThS. Bs Trần Đắc Long", "BSCKI Đào Thị Thu Hà", "ThS.BS Nguyễn Quốc Hùng", "ThS.BS Nguyễn Toàn Thắng", "BSCKI Đào Thị Thu Hà", "SAT: BSCKII Phạm Thị An", "Nghỉ"),
                    july_room("Phòng khám số 4", "7.30 - 16.30", "BSCKII Vũ Thị Trang", "Sáng: ThS.BS Lê Thị Thảo\nChiều: BSCKI Nguyễn Trung Hiếu", "Sáng: BSCKI Nguyễn Trung Hiếu\nChiều: ThS.BS Hoàng Minh Lợi", "ThS.BS Nguyễn Thị Minh Nguyệt", "Sáng: ThS.BS Nguyễn Phương Liên\nChiều: BS Đinh Hải Nam", "Khám TC\nThS.BS Trần Sinh Cường", "Nghỉ"),
                    july_room("Phòng khám số 5", "6.30 - 16.30", "ThS.BS Nguyễn Xuân Từ", "ThS.BS Nguyễn Thế Nam Huy", "BS Đinh Hải Nam", "Sáng: ThS.BS Lê Quang Huy\nChiều: BS Phạm Thị Hoa", "ThS.BS Nguyễn Thế Nam Huy", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 6", "6.30 - 16.30", "ThS.BS Phạm Văn Tùng", "ThS.BS Lê Quang Huy", "ThS.BS Lê Thế Kiên", "ThS.BS Lê Thị Thảo", "Sáng: ThS.BS Nguyễn Mai Hương\nChiều: BSCKI Nguyễn Trung Hiếu", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 7", "6.30 - 16.30", "ThS.BS Lê Thế Kiên", "Sáng: ThS.BS Đỗ Thị Vân Anh\nChiều: BS Chu Thị Hằng", "ThS.BS Phạm Văn Tùng", "Sáng: ThS.BS Hoàng Minh Lợi\nChiều: TS.BS Ngọ Văn Thanh", "Sáng: ThS.BS Trần Sinh Cường\nChiều: ThS.BS. Phạm Đăng Anh", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 8", "7.30 - 16.30", "Sáng: ThS.BS Nguyễn Mai Hương\nChiều: BS Trần Thanh Hoa", "Sáng: ThS.BS Hoàng Minh Lợi\nChiều: BS. Nguyễn Ngọc Tân", "Sáng: ThS.BS Nguyễn Thị Minh Nguyệt\nChiều: ThS.BS Lê Quang Huy", "Sáng: BSCKII Phạm Thị An\nChiều: ThS.BS Nguyễn Phương Liên", "TS.BS Nguyễn Xuân Tuấn", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 9", "7.30 - 16.30", "Sáng: ThS.BS Đỗ Thị Vân Anh\nChiều: ThS.BS Lê Thị Thảo", "ThS.BS Trần Sinh Cường", "ThS.BS Nguyễn Phương Liên", "Sáng: BSCKII Vũ Thị Trang\nChiều: BS. Nguyễn Ngọc Tân", "BS Trần Thanh Hoa", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám tăng cường 1 (HC)", "7.30 - 16.30", "", "ThS.BS Lê Thế Kiên", "", "", "Sáng: BSCKI Nguyễn Trung Hiếu", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám tăng cường 2 (PK 4)", "7.30 - 16.30", "", "", "", "", "", "Nghỉ", "Nghỉ"),
                ],
            },
        ],
    }
    write_json(out / FILE_TN1_CS1, tn1_payload)

    tn_cs2_payload = {
        "tieu_de": "LỊCH LÀM VIỆC CỦA CÁC BÁC SỸ KHU KHÁM BỆNH TỰ NGUYỆN",
        "dia_diem": "TẠI BỆNH VIỆN TIM HÀ NỘI - CƠ SỞ 2 - 695 LẠC LONG QUÂN - PHƯỜNG TÂY HỒ - HÀ NỘI",
        "thoi_gian": "Tuần từ ngày 22/06/2026 đến ngày 28/06/2026",
        "thong_tin_lien_he": {
            "dat_lich": "19001082",
            "tu_van_hanh_chinh": "02439427791",
            "tu_van_24_24h": "0969655335",
            "website": "benhvientimhanoi.vn",
            "fanpage": "fb.com/BenhVienTimHaNoi.vn",
        },
        "dich_vu": "Dịch vụ khám bệnh theo yêu cầu",
        "lich_kham": [
            {
                "phong_kham": "Phòng khám số 306",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "BS.CKII Lê Thị Hoài Thu",
                "thu_3": "BS.CKII Lê Thị Hoài Thu",
                "thu_4": "BS.CKII Lê Thị Hoài Thu",
                "thu_5": "BS.CKII Lê Thị Hoài Thu",
                "thu_6": "BS.CKII Lê Thị Hoài Thu",
                "thu_7_tn_muc_3": "Bs Nguyễn Gia Phong",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 309",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "Ths.Bs Nguyễn Duy Chinh",
                "thu_3": "Ths.Bs Nguyễn Duy Chinh",
                "thu_4": "Ths.Bs Nguyễn Duy Chinh",
                "thu_5": "Ths.Bs Nguyễn Duy Chinh",
                "thu_6": "Ths.Bs Nguyễn Duy Chinh",
                "thu_7_tn_muc_3": "Bs Nguyễn Gia Phong",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 308",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "Ts.Bs Trần Thị Linh Tú",
                "thu_3": "Ts.Bs Trần Thị Linh Tú",
                "thu_4": "Ts.Bs Trần Thị Linh Tú",
                "thu_5": "Ts.Bs Trần Thị Linh Tú",
                "thu_6": "Ts.Bs Trần Thị Linh Tú",
                "thu_7_tn_muc_3": "Bs Nguyễn Gia Phong",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 310",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "TC",
                "thu_3": "TC",
                "thu_4": "TC",
                "thu_5": "TC",
                "thu_6": "TC",
                "thu_7_tn_muc_3": "Bs Nguyễn Gia Phong",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 311",
                "thoi_gian": "7.30 - 16.30",
                "thu_2": "Ths.Bs Lê Thùy Ngọc",
                "thu_3": "Ths.Bs Lê Thùy Ngọc",
                "thu_4": "Ths.Bs Lê Thùy Ngọc",
                "thu_5": "Ths.Bs Lê Thùy Ngọc",
                "thu_6": "Ths.Bs Lê Thùy Ngọc",
                "thu_7_tn_muc_3": "Bs Nguyễn Gia Phong",
                "chu_nhat": "NGHỈ",
            },
        ],
    }
    write_json(out / FILE_TN_CS2, tn_cs2_payload)

    da_khoa_payload = {
        "tieu_de": "LỊCH LÀM VIỆC CỦA CÁC BÁC SỸ PHÒNG KHÁM ĐA KHOA",
        "dia_diem": "TẠI BỆNH VIỆN TIM HÀ NỘI - CƠ SỞ 2 - 695 LẠC LONG QUÂN, TÂY HỒ, HÀ NỘI",
        "thoi_gian": "Tuần từ ngày 22/6/2026 đến ngày 28/6/2026",
        "thong_tin_lien_he": {
            "so_dien_thoai": "0961.972.097",
            "ghi_chu": "(Giờ hành chính các ngày trong tuần từ thứ 2 đến thứ 6)",
        },
        "lich_kham": [
            july_da_khoa_room("RHM (P401)", "7.30 - 16.30", "BS Nguyễn Thanh Trà", "BS Nguyễn Thanh Trà\nkhám tại CS1(15H)", "BS Nguyễn Thanh Trà", "BS Nguyễn Thanh Trà\nkhám tại CS1(15H)", "BS Nguyễn Thanh Trà", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("PHCN (P401)", "7.30 - 16.30", "BSNT. Trần Thị Quỳnh Nga", "BSNT. Trần Thị Quỳnh Nga", "BSNT. Trần Thị Quỳnh Nga", "BSNT. Trần Thị Quỳnh Nga", "BSNT. Trần Thị Quỳnh Nga", "SHCLBBN COPD (S)", "Nghỉ"),
            july_da_khoa_room("TMH (P402)", "7.30 - 16.30", "/", "/", "/", "/", "/", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("PK NHI (P402)", "7.30 - 16.30", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("DA LIỄU (P403)", "7.30 - 16.30", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("Sản- phụ khoa (P403)", "7.30 - 16.30", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("YHCT (P404)", "7.30 - 16.30", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("Nội chung - Hô Hấp (P405.A)", "7.30 - 16.30", "Ths.BS Lại Thị Bạch Yến", "Ths.BS Lại Thị Bạch Yến", "Ths.BS Lại Thị Bạch Yến", "Ths.BS Lại Thị Bạch Yến", "Ths.BS Lại Thị Bạch Yến", "SHCLBBN COPD(S)", "Nghỉ"),
            july_da_khoa_room("Nội chung - CXK (P405.B)", "7.30 - 16.31", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("PK NTM - NT (P405.C)", "7.30 - 16.30", "BS TMCH", "BS TMCH", "BS TMCH", "BS TMCH", "BS TMCH", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("MẮT (P405.D)", "7.30 - 16.30", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "Nghỉ", "Nghỉ"),
        ],
    }
    write_json(out / FILE_DA_KHOA_CS2, da_khoa_payload)


def export_june15_june21():
    out = BASE_DIR / "lich_kham_15-21_thang_6_2026"
    tn1_payload = {
        "tieu_de": "LỊCH KHÁM BỆNH CỦA CÁC BÁC SỸ KHOA KHÁM BỆNH TỰ NGUYỆN",
        "dia_diem": "TẠI BỆNH VIỆN TIM HÀ NỘI - CƠ SỞ 1 - 92 TRẦN HƯNG ĐẠO, HOÀN KIẾM, HÀ NỘI",
        "thoi_gian": "Tuần từ ngày 15-21.6.2026",
        "thong_tin_lien_he": {
            "dat_lich_va_tu_van_24_24": "1900.1082",
            "tu_van_hanh_chinh": "0869032338",
            "website": ["benhvientimhanoi.vn", "benhvientimhanoi.com.vn"],
            "fanpage": "fb.com/BenhVienTimHaNoi.vn",
        },
        "lich_kham": [
            {
                "khoa": "Khoa khám bệnh Tự nguyện 1",
                "danh_sach_phong": [
                    july_room("Phòng khám số 1", "7.30 - 16.30", "TS.BS Phạm Như Hùng", "TS.BS Phạm Như Hùng", "TS.BS Phạm Như Hùng", "Sáng: TS.BS Nguyễn Thị Thu Thủy\nChiều: TS.BS Ngọ Văn Thanh", "Sáng: BSCKII Phạm Thị An\nChiều: TS.BS Nguyễn Xuân Tuấn", "Nghỉ", "ThS.BS Nguyễn Đình Hồng Phúc"),
                    july_room("Phòng khám số 2", "7.30 - 16.30", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "TS.BS Vũ Quỳnh Nga", "Nghỉ", "SAT: BSCKII Phạm Thị An"),
                    july_room("Phòng khám số 3", "7.00 - 16.30", "TS.BS Bùi Thị Thanh Hà", "TS.BS Nguyễn Xuân Tuấn", "TS.BS Bùi Thị Thanh Hà", "TS.BS Đinh Quang Huy", "TS.BS Bùi Thị Thanh Hà", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 4", "7.30 - 16.30", "Sáng: TS.BS Hoàng Văn\nChiều: BSCKII Nguyễn Văn Dần", "TS.BS Hà Mai Hương", "Sáng: TS.BS Hoàng Văn\nChiều: ThS.BS Nguyễn Thị Quỳnh Trang", "TS.BS Hà Mai Hương", "Sáng: TS.BS Hoàng Văn\nChiều: TS.BS Nguyễn Thị Thu Thủy", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 5", "7.00 - 16.30", "TS.BS Trần Thị Ngọc Lan", "ThS.BS Nguyễn Xuân Từ", "Sáng: BSCKII Nguyễn Văn Dần\nChiều: BSCKII Vũ Thị Trang", "ThS.BS Nguyễn Thị Việt Nga", "TS.BS Hà Mai Hương", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 6", "7.30 - 16.30", "ThS.BS Nguyễn Thị Việt Nga", "BSCKII Phạm Thị An", "TS.BS Nguyễn Thị Thu Thủy", "BSCKII Nguyễn Văn Thực", "ThS.BS Nguyễn Thị Quỳnh Trang", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 7", "7.00 - 16.00", "TS.BS Nguyễn Xuân Tuấn", "TS.BS Trần Thị An", "ThS.BS Nguyễn Xuân Từ", "TS.BS Trần Thị Ngọc Lan", "BSCKII Vũ Thị Trang", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 8", "7.00 - 16.00", "TS.BS Đinh Quang Huy", "TS.BS Nguyễn Thị Thu Thủy", "Sáng: TS.BS Trần Thị An\nChiều: TS.BS Trần Thị Ngọc Lan", "BS CKII Phạm Quang Huy", "TS.BS Trần Thị An", "Nghỉ", "Nghỉ"),
                ],
            },
            {
                "khoa": "Khoa khám bệnh Tự nguyện 3",
                "danh_sach_phong": [
                    july_room("Phòng khám số 1", "7.30 - 16.30", "ThS.BS Võ Thị Ngọc Anh", "ThS.BS Nguyễn Danh Sen", "ThS.BS Võ Thị Ngọc Anh", "ThS.BS Nguyễn Danh Sen", "BS CKII Trần Thị Thanh Hà", "ThS.BS Trần Ngọc Dũng", "Nghỉ"),
                    july_room("Phòng khám số 2", "7.30 - 16.30", "Sáng: ThS.BS Trần Sinh Cường\nChiều: BS CKII Trần Thị Thanh Hà", "Sáng: BSCKII Nguyễn Văn Dần\nChiều: ThS.BS Phạm Văn Tùng", "Sáng: BS Trần Thanh Hoa\nChiều: ThS.BS. Phạm Đăng Anh", "Sáng: ThS.BS Hoàng Minh Lợi\nChiều: ThS.BS Nguyễn Đình Hồng Phúc", "Sáng: ThS.BS Nguyễn Xuân Từ\nChiều: ThS.BS. Phạm Đăng Anh", "ThS.BS Nguyễn Danh Sen", "Nghỉ"),
                    july_room("Phòng khám số 3", "7.30 - 16.30", "ThS.BS Nguyễn Toàn Thắng", "ThS. Bs Trần Đắc Long", "ThS.BS Nguyễn Quốc Hùng", "ThS.BS Nguyễn Toàn Thắng", "BSCKI Đào Thị Thu Hà", "SAT: BSCKII Vũ Thị Trang", "Nghỉ"),
                    july_room("Phòng khám số 4", "7.30 - 16.30", "Sáng: BS Trần Thanh Hoa\nChiều: TS.BS Ngọ Văn Thanh", "ThS.BS Lê Quang Huy", "Sáng: ThS.BS Nguyễn Mai Hương\nChiều: ThS.BS Phạm Văn Tùng", "ThS.BS Nguyễn Thị Minh Nguyệt", "Sáng: ThS.BS Nguyễn Mai Hương\nChiều: BS Chu Thị Hằng", "Khám TC\nThS.BS Phạm Hùng Cường", "Nghỉ"),
                    july_room("Phòng khám số 5", "6.30 - 16.30", "BSCKII Nguyễn Văn Thực", "Sáng: BSCKI Nguyễn Trung Hiếu\nChiều: ThS.BS Nguyễn Thế Nam Huy", "Sáng: ThS.BS Lê Quang Huy\nChiều: BS CKII Trần Thị Thanh Hà", "BSCKII Nguyễn Văn Dần", "ThS.BS Nguyễn Thế Nam Huy", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 6", "6.30 - 16.30", "SThS.BS Lê Thị Thảo", "Sáng: BS Trần Thanh Hoa\nChiều: BS. Nguyễn Ngọc Tân", "ThS.BS Hoàng Minh Lợi", "ThS.BS Nguyễn Phương Liên", "ThS.BS Lê Thế Kiên", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 7", "6.30 - 16.30", "ThS.BS Nguyễn Mai Hương", "BS Đinh Hải Nam", "Sáng: BSCKI Nguyễn Trung Hiếu\nChiều: BSCKII Nguyễn Văn Thực", "ThS.BS Nguyễn Xuân Từ", "Sáng: ThS.BS Trần Sinh Cường\nChiều: BSCKI Nguyễn Trung Hiếu", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 8", "7.30 - 16.30", "ThS.BS Nguyễn Thị Quỳnh Trang", "Sáng: ThS.BS Trần Sinh Cường\nChiều: ThS.BS Đỗ Thị Vân Anh", "ThS.BS Đỗ Thị Vân Anh", "BSCKII Phạm Thị An", "BS Đinh Hải Nam", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám số 9", "7.30 - 16.30", "Sáng: ThS.BS Lê Thế Kiên\nChiều: BSCKII Phạm Thị An", "Sáng: ThS.BS Lê Thị Thảo\nChiều: ThS.BS Nguyễn Mai Hương", "Sáng: ThS.BS Nguyễn Thị Minh Nguyệt\nChiều: ThS.BS Lê Thị Thảo", "Sáng: ThS.BS Đỗ Thị Vân Anh\nChiều: ThS.BS Trần Sinh Cường", "Sáng: ThS.BS Nguyễn Đình Hồng Phúc\nChiều: ThS.BS Hoàng Minh Lợi", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám tăng cường 1 (HC)", "7.30 - 16.30", "BS Đinh Hải Nam", "BSCKI Nguyễn Trung Hiếu", "", "BS. Nguyễn Ngọc Tân", "Sáng: ThS.BS Đỗ Thị Vân Anh", "Nghỉ", "Nghỉ"),
                    july_room("Phòng khám tăng cường 2 (PK 4)", "7.30 - 16.30", "", "", "", "", "", "Nghỉ", "Nghỉ"),
                ],
            },
        ],
    }
    write_json(out / FILE_TN1_CS1, tn1_payload)

    tn_cs2_payload = {
        "tieu_de": "LỊCH LÀM VIỆC CỦA CÁC BÁC SỸ KHU KHÁM BỆNH TỰ NGUYỆN",
        "dia_diem": "TẠI BỆNH VIỆN TIM HÀ NỘI - CƠ SỞ 2 - 695 LẠC LONG QUÂN - PHƯỜNG TÂY HỒ - HÀ NỘI",
        "thoi_gian": "Tuần từ ngày 15/06/2026 đến ngày 21/06/2026",
        "thong_tin_lien_he": {
            "dat_lich": "19001082",
            "tu_van_hanh_chinh": "02439427791",
            "tu_van_24_24h": "0969655335",
            "website": "benhvientimhanoi.vn",
            "fanpage": "fb.com/BenhVienTimHaNoi.vn",
        },
        "dich_vu": "Dịch vụ khám bệnh theo yêu cầu",
        "lich_kham": [
            {
                "phong_kham": "Phòng khám số 306",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "BS.CKII Lê Thị Hoài Thu",
                "thu_3": "BS.CKII Lê Thị Hoài Thu",
                "thu_4": "BS.CKII Lê Thị Hoài Thu",
                "thu_5": "BS.CKII Lê Thị Hoài Thu",
                "thu_6": "BS.CKII Lê Thị Hoài Thu",
                "thu_7_tn_muc_3": "Bs Phạm Anh Hùng",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 309",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "Ths.Bs Nguyễn Duy Chinh",
                "thu_3": "Ths.Bs Nguyễn Duy Chinh",
                "thu_4": "Ths.Bs Nguyễn Duy Chinh",
                "thu_5": "Ths.Bs Nguyễn Duy Chinh",
                "thu_6": "Ths.Bs Nguyễn Duy Chinh",
                "thu_7_tn_muc_3": "Bs Phạm Anh Hùng",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 308",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "Ts.Bs Trần Thị Linh Tú",
                "thu_3": "Ts.Bs Trần Thị Linh Tú",
                "thu_4": "Ts.Bs Trần Thị Linh Tú",
                "thu_5": "Ts.Bs Trần Thị Linh Tú",
                "thu_6": "Ts.Bs Trần Thị Linh Tú",
                "thu_7_tn_muc_3": "Bs Phạm Anh Hùng",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 310",
                "thoi_gian": "7.00 - 16.30",
                "thu_2": "TC",
                "thu_3": "TC",
                "thu_4": "TC",
                "thu_5": "TC",
                "thu_6": "TC",
                "thu_7_tn_muc_3": "Bs Phạm Anh Hùng",
                "chu_nhat": "NGHỈ",
            },
            {
                "phong_kham": "Phòng khám số 311",
                "thoi_gian": "7.30 - 16.30",
                "thu_2": "Ths.Bs Lê Thùy Ngọc",
                "thu_3": "Ths.Bs Lê Thùy Ngọc",
                "thu_4": "Ths.Bs Lê Thùy Ngọc",
                "thu_5": "Ths.Bs Lê Thùy Ngọc",
                "thu_6": "Ths.Bs Lê Thùy Ngọc",
                "thu_7_tn_muc_3": "Bs Phạm Anh Hùng",
                "chu_nhat": "NGHỈ",
            },
        ],
    }
    write_json(out / FILE_TN_CS2, tn_cs2_payload)

    da_khoa_payload = {
        "tieu_de": "LỊCH LÀM VIỆC CỦA CÁC BÁC SỸ PHÒNG KHÁM ĐA KHOA",
        "dia_diem": "TẠI BỆNH VIỆN TIM HÀ NỘI - CƠ SỞ 2 - 695 LẠC LONG QUÂN, TÂY HỒ, HÀ NỘI",
        "thoi_gian": "Tuần từ ngày 15/6/2026 đến ngày 19/6/2026",
        "thong_tin_lien_he": {
            "so_dien_thoai": "0961.972.097",
            "ghi_chu": "(Giờ hành chính các ngày trong tuần từ thứ 2 đến thứ 6)",
        },
        "lich_kham": [
            july_da_khoa_room("RHM (P401)", "7.30 - 16.30", "BS Nguyễn Thanh Trà", "BS Nguyễn Thanh Trà\nkhám tại CS1(15H)", "BS Nguyễn Thanh Trà", "BS Nguyễn Thanh Trà\nkhám tại CS1(15H)", "BS Nguyễn Thanh Trà", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("PHCN (P401)", "7.30 - 16.30", "BSNT. Trần Thị Quỳnh Nga", "BSNT. Trần Thị Quỳnh Nga", "BSNT. Trần Thị Quỳnh Nga", "BSNT. Trần Thị Quỳnh Nga", "BSNT. Trần Thị Quỳnh Nga", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("TMH (P402)", "7.30 - 16.30", "/", "/", "/", "/", "/", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("PK NHI (P402)", "7.30 - 16.30", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Ths.Bs Dương Thị Thúy Nga", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("DA LIỄU (P403)", "7.30 - 16.30", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "ThsBs Nguyễn Thị Minh Hoa", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("Sản- phụ khoa (P403)", "7.30 - 16.30", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Sáng\nBSCK II Nguyễn Thị Tuyết Mai\nChiều Nghỉ", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("YHCT (P404)", "7.30 - 16.30", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "BSNT. Nguyễn Thị Thuận", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("Nội chung - Hô Hấp (P405.A)", "7.30 - 16.30", "Ths.BS Lại Thị Bạch Yến", "Ths.BS Lại Thị Bạch Yến", "Ths.BS Lại Thị Bạch Yến", "Ths.BS Lại Thị Bạch Yến", "Ths.BS Lại Thị Bạch Yến", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("Nội chung - CXK (P405.B)", "7.30 - 16.31", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Ths.BSNT Phạm Thị Oanh", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("PK NTM - NT (P405.C)", "7.30 - 16.30", "BS TMCH", "BS TMCH", "BS TMCH", "BS TMCH", "BS TMCH", "Nghỉ", "Nghỉ"),
            july_da_khoa_room("MẮT (P405.D)", "7.30 - 16.30", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "BSCKI.Nguyễn Thị Huyền", "Nghỉ", "Nghỉ"),
        ],
    }
    write_json(out / FILE_DA_KHOA_CS2, da_khoa_payload)


def main():
    export_june15_june21()
    export_june22_june28()
    export_june29_july05()
    export_june_08_14()
    export_july_06_12()


if __name__ == "__main__":
    main()
