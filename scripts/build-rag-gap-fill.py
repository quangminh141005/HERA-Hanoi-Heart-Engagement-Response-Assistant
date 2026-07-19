#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "rag_gap_fill"
RAW_DIR = ROOT / "data" / "source" / "raw"
VERIFIED_AT = "2026-07-18T00:00:00+07:00"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rag_record(fact: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    warning = fact.get("safety_warning_vi")
    retrieval_lines = [
        f"Nguồn: {source['source_title']}.",
        f"Nhà xuất bản: {source['publisher']}.",
        f"URL: {source['source_url']}.",
        f"Chủ đề: {fact['topic']}.",
        f"Phạm vi cơ sở: {fact['facility_scope']}.",
        f"Nội dung: {fact['answer_vi']}",
    ]
    if warning:
        retrieval_lines.append(f"Cảnh báo: {warning}")
    retrieval_lines.append("Quy tắc trả lời: chỉ dùng nội dung đã có nguồn; không suy luận giá, quyền lợi cá nhân hoặc tình trạng còn chỗ.")
    return {
        "rag_id": f"rag__{fact['fact_id'].lower()}",
        "document_type": fact["document_type"],
        "topic": fact["topic"],
        "source": {
            "source_id": source["source_id"],
            "title": source["source_title"],
            "url": source["source_url"],
            "publisher": source["publisher"],
            "authority": source["authority"],
            "raw_file": source.get("raw_file"),
            "raw_sha256": source.get("raw_sha256"),
        },
        "metadata": {
            "fact_id": fact["fact_id"],
            "facility_scope": fact["facility_scope"],
            "approval_status": fact["approval_status"],
            "verified_at": fact["verified_at"],
            "effective_from": fact.get("effective_from"),
            "effective_to": fact.get("effective_to"),
            "requires_human_review_before_production": fact["approval_status"] != "approved_for_production",
        },
        "canonical_answer_vi": fact["answer_vi"],
        "safety_warning_vi": warning,
        "query_variants": fact["question_patterns_vi"],
        "retrieval_text": "\n".join(retrieval_lines),
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    raw_files = {
        "booking_html": RAW_DIR / "hanoi-heart-hospital-booking-guide-2026-07-18.html",
        "voluntary_html": RAW_DIR / "hanoi-heart-hospital-voluntary-clinic-2026-07-18.html",
        "bhxh_bhyt_html": RAW_DIR / "bhxh-bhyt-outpatient-crosstier-2026-06-26.html",
        "general_html": RAW_DIR / "hanoi-heart-hospital-general-introduction-2026-07-18.html",
        "leadership_html": RAW_DIR / "hanoi-heart-hospital-leadership-2026-07-18.html",
        "zalo_html": RAW_DIR / "hanoi-heart-hospital-zalo-guide-2026-07-18.html",
    }

    sources = [
        {
            "source_id": "SRC-HHH-BOOKING-GUIDE-2026-07-18",
            "source_title": "Hướng dẫn liên hệ đặt lịch khám",
            "publisher": "Bệnh viện Tim Hà Nội",
            "authority": "official_hospital",
            "source_url": "https://benhvientimhanoi.vn/vn/cong/thong-tin/huong-dan-lien-he-dat-lich-kham",
            "retrieved_at": VERIFIED_AT,
            "raw_file": str(raw_files["booking_html"].relative_to(ROOT)),
            "raw_sha256": sha256_file(raw_files["booking_html"]),
            "usable_for_runtime": True,
        },
        {
            "source_id": "SRC-HHH-VOLUNTARY-CLINIC-2026-07-18",
            "source_title": "Khoa Khám bệnh tự nguyện",
            "publisher": "Bệnh viện Tim Hà Nội",
            "authority": "official_hospital",
            "source_url": "https://benhvientimhanoi.vn/vn/cong/thong-tin/khoa-kham-benh-tu-nguyen",
            "retrieved_at": VERIFIED_AT,
            "raw_file": str(raw_files["voluntary_html"].relative_to(ROOT)),
            "raw_sha256": sha256_file(raw_files["voluntary_html"]),
            "usable_for_runtime": True,
        },
        {
            "source_id": "SRC-BHXH-BHYT-OUTPATIENT-2026-06-26",
            "source_title": "Mở rộng quyền lợi BHYT khi khám ngoại trú trái tuyến từ ngày 01/7/2026",
            "publisher": "Bảo hiểm xã hội Việt Nam",
            "authority": "official_bhxh_vietnam",
            "source_url": "https://baohiemxahoi.gov.vn/tintuc/Pages/linh-vuc-bao-hiem-y-te.aspx?CateID=169&ItemID=26712&OtItem=date",
            "published_at": "2026-06-26T14:14:00+07:00",
            "retrieved_at": VERIFIED_AT,
            "raw_file": str(raw_files["bhxh_bhyt_html"].relative_to(ROOT)),
            "raw_sha256": sha256_file(raw_files["bhxh_bhyt_html"]),
            "usable_for_runtime": True,
        },
        {
            "source_id": "SRC-HHH-GENERAL-INTRODUCTION-2026-07-18",
            "source_title": "Giới thiệu chung",
            "publisher": "Bệnh viện Tim Hà Nội",
            "authority": "official_hospital",
            "source_url": "https://benhvientimhanoi.vn/vn/cong/thong-tin/gioi-thieu-chung",
            "retrieved_at": VERIFIED_AT,
            "raw_file": str(raw_files["general_html"].relative_to(ROOT)),
            "raw_sha256": sha256_file(raw_files["general_html"]),
            "usable_for_runtime": True,
        },
        {
            "source_id": "SRC-HHH-LEADERSHIP-2026-07-18",
            "source_title": "Ban lãnh đạo bệnh viện",
            "publisher": "Bệnh viện Tim Hà Nội",
            "authority": "official_hospital",
            "source_url": "https://benhvientimhanoi.vn/vn/cong/thong-tin/ban-lanh-dao",
            "retrieved_at": VERIFIED_AT,
            "raw_file": str(raw_files["leadership_html"].relative_to(ROOT)),
            "raw_sha256": sha256_file(raw_files["leadership_html"]),
            "usable_for_runtime": True,
        },
        {
            "source_id": "SRC-HHH-ZALO-GUIDE-2026-07-18",
            "source_title": "Hướng dẫn truy cập và đặt lịch hẹn trên Zalo Bệnh viện Tim Hà Nội",
            "publisher": "Bệnh viện Tim Hà Nội",
            "authority": "official_hospital",
            "source_url": "https://www.benhvientimhanoi.vn/vi/thu-vien-video/chi-tiet/huong-dan-truy-cap-zalo-benh-vien-tim-ha-noi",
            "published_at": "2026-01-27",
            "retrieved_at": VERIFIED_AT,
            "raw_file": str(raw_files["zalo_html"].relative_to(ROOT)),
            "raw_sha256": sha256_file(raw_files["zalo_html"]),
            "usable_for_runtime": True,
        },
    ]
    source_by_id = {source["source_id"]: source for source in sources}

    facts = [
        {
            "fact_id": "GAP-BOOKING-NON-EMERGENCY",
            "document_type": "hospital_booking_policy",
            "topic": "booking",
            "facility_scope": "all",
            "question_patterns_vi": ["đặt lịch khám có dùng cho cấp cứu không", "trường hợp nào không nên đặt hẹn khám", "cấp cứu thì đặt lịch hay gọi ai"],
            "answer_vi": "Đặt hẹn khám của Bệnh viện Tim Hà Nội chỉ dành cho trường hợp không cấp cứu, không khẩn cấp. Nếu cấp cứu, người bệnh cần gọi số cấp cứu theo tỉnh/thành theo dạng mã vùng + 115 hoặc đến thẳng cơ sở cấp cứu gần nhất.",
            "source_id": "SRC-HHH-BOOKING-GUIDE-2026-07-18",
            "verified_at": VERIFIED_AT,
            "approval_status": "approved_for_hackathon",
        },
        {
            "fact_id": "GAP-BOOKING-LEAD-TIME-CONFIRMATION",
            "document_type": "hospital_booking_policy",
            "topic": "booking",
            "facility_scope": "all",
            "question_patterns_vi": ["cần đặt lịch trước bao lâu", "lịch hẹn có hiệu lực khi nào", "đến trước giờ khám bao lâu"],
            "answer_vi": "Người bệnh được hướng dẫn đặt hẹn trước ít nhất 24 giờ so với giờ dự định khám. Lịch hẹn chỉ có giá trị sau khi Bệnh viện xác nhận. Người bệnh cần có mặt trước giờ hẹn ít nhất 15 phút để làm thủ tục đăng ký và đo mạch, huyết áp trước khi gặp bác sĩ.",
            "source_id": "SRC-HHH-BOOKING-GUIDE-2026-07-18",
            "verified_at": VERIFIED_AT,
            "approval_status": "approved_for_hackathon",
        },
        {
            "fact_id": "GAP-BOOKING-CONTACTS",
            "document_type": "hospital_contact",
            "topic": "booking_contact",
            "facility_scope": "all",
            "question_patterns_vi": ["số điện thoại đặt lịch bệnh viện tim hà nội", "hotline đặt khám", "đăng ký khám online ở đâu", "liên hệ bảo hiểm y tế bệnh viện tim hà nội"],
            "answer_vi": "Bệnh viện Tim Hà Nội công bố hotline 19001082 cho đăng ký khám bệnh tại cơ sở 1 và cơ sở 2, đồng thời dùng 19001082 để giải đáp thủ tục hành chính và tư vấn BHYT. Phòng khám đa khoa có số 0243.758.9090 hoặc 096.197.2097 trong giờ hành chính. Link đặt khám website là https://benhvientimhanoi.vn/he-thong/hen-kham/index.html.",
            "source_id": "SRC-HHH-BOOKING-GUIDE-2026-07-18",
            "verified_at": VERIFIED_AT,
            "approval_status": "approved_for_hackathon",
        },
        {
            "fact_id": "GAP-BOOKING-SCOPE-FACILITIES",
            "document_type": "hospital_booking_policy",
            "topic": "booking_scope",
            "facility_scope": "all",
            "question_patterns_vi": ["đặt lịch áp dụng khu nào", "khám tự nguyện nào đặt lịch được", "khám thường cơ sở 2 đặt hẹn được chưa"],
            "answer_vi": "Theo hướng dẫn đặt lịch, bệnh viện đang nhận đặt hẹn cho Khám Tự nguyện 1 và 2 ở cơ sở 1 và khám Tự nguyện cơ sở 2. Khám Tự nguyện 3 cơ sở 1 và khám Thường cơ sở 2 được nêu là sẽ triển khai đặt khám theo hẹn sau.",
            "source_id": "SRC-HHH-BOOKING-GUIDE-2026-07-18",
            "verified_at": VERIFIED_AT,
            "approval_status": "review_only",
        },
        {
            "fact_id": "GAP-VOLUNTARY-CLINIC-SUMMARY",
            "document_type": "hospital_department_service",
            "topic": "department_service",
            "facility_scope": "CS1",
            "question_patterns_vi": ["khoa khám bệnh tự nguyện có gì", "khám tự nguyện bệnh viện tim hà nội", "khoa tự nguyện có mấy khu"],
            "answer_vi": "Khoa Khám bệnh Tự nguyện được thành lập tháng 10/2013 và có 2 khu khám bệnh: Khám bệnh tự nguyện 1 và Khám bệnh tự nguyện 3. Khoa có các phòng khám chuyên khoa tim mạch, phòng khám tĩnh mạch chi dưới, phòng siêu âm và hệ thống tài chính riêng để giảm thời gian chờ thủ tục tài chính.",
            "source_id": "SRC-HHH-VOLUNTARY-CLINIC-2026-07-18",
            "verified_at": VERIFIED_AT,
            "approval_status": "approved_for_hackathon",
        },
        {
            "fact_id": "GAP-VOLUNTARY-CLINIC-SERVICES",
            "document_type": "hospital_department_service",
            "topic": "specialized_services",
            "facility_scope": "CS1",
            "question_patterns_vi": ["dịch vụ chuyên sâu khoa tự nguyện", "có holter huyết áp không", "có siêu âm tim thai không", "khám tim chuyên sâu gồm gì"],
            "answer_vi": "Trang Khoa Khám bệnh tự nguyện liệt kê các dịch vụ/thăm dò như điện tim đồ, X-quang tim phổi, siêu âm Doppler tim thường quy, xét nghiệm cơ bản, siêu âm ổ bụng, nghiệm pháp gắng sức, siêu âm tim Dobutamine, Holter huyết áp 24 giờ, Holter điện tim 24 giờ, siêu âm tim qua thực quản, siêu âm tim 4D, siêu âm Doppler mạch máu, đo ABI, xét nghiệm máu chuyên sâu, chụp cộng hưởng từ, chụp CT động mạch vành và siêu âm tim thai từ tuần thai thứ 18.",
            "source_id": "SRC-HHH-VOLUNTARY-CLINIC-2026-07-18",
            "verified_at": VERIFIED_AT,
            "approval_status": "approved_for_hackathon",
        },
        {
            "fact_id": "GAP-VOLUNTARY-CLINIC-BHYT-INPATIENT",
            "document_type": "hospital_insurance_note",
            "topic": "bhyt_hospital_note",
            "facility_scope": "CS1",
            "question_patterns_vi": ["khám tự nguyện có dùng bảo hiểm y tế không", "vào viện nội trú từ khoa tự nguyện có bhyt không", "cần chuyển tuyến khi vào viện không cấp cứu không"],
            "answer_vi": "Trang Khoa Khám bệnh tự nguyện nêu rằng bệnh nhân có thẻ BHYT và giấy chuyển viện đúng tuyến có thể lựa chọn một trong hai khu Tự nguyện. Khi vào viện điều trị nội trú, trường hợp cấp cứu được hưởng BHYT cấp cứu; trường hợp không cấp cứu cần xin chuyển tuyến theo quy định BHYT.",
            "source_id": "SRC-HHH-VOLUNTARY-CLINIC-2026-07-18",
            "verified_at": VERIFIED_AT,
            "approval_status": "review_only",
            "safety_warning_vi": "Không thay thế xác nhận quyền lợi BHYT cá nhân tại quầy bệnh viện hoặc cơ quan BHXH.",
        },
        {
            "fact_id": "GAP-BHYT-OUTPATIENT-CROSSTIER-2026",
            "document_type": "bhyt_general_policy",
            "topic": "bhyt_benefits",
            "facility_scope": "general_policy",
            "question_patterns_vi": ["bhyt ngoại trú trái tuyến từ 1/7/2026", "50% mức hưởng bhyt là gì", "tự đi khám ngoại trú trái tuyến có được bhyt không"],
            "answer_vi": "Từ ngày 01/07/2026, BHXH Việt Nam nêu rằng người tham gia BHYT tự đi khám chữa bệnh ngoại trú tại một số cơ sở cấp cơ bản và cấp chuyên sâu có thể được quỹ BHYT thanh toán 50% mức hưởng đối với các bệnh, nhóm bệnh trước đây chưa được thanh toán. Chính sách không áp dụng cho mọi bệnh viện hoặc mọi trường hợp; còn phụ thuộc cấp chuyên môn kỹ thuật của cơ sở, bệnh/nhóm bệnh được chẩn đoán, mức hưởng và phạm vi chi phí được quỹ BHYT thanh toán.",
            "source_id": "SRC-BHXH-BHYT-OUTPATIENT-2026-06-26",
            "verified_at": VERIFIED_AT,
            "effective_from": "2026-07-01",
            "effective_to": None,
            "approval_status": "review_only",
            "safety_warning_vi": "Không tính quyền lợi cá nhân hoặc số tiền phải trả; cần xác nhận tại bệnh viện hoặc cơ quan BHXH.",
        },
        {
            "fact_id": "GAP-EXAM-FLOW-CS1-CS2-LINKED",
            "document_type": "hospital_procedure_fact",
            "topic": "exam_flow",
            "facility_scope": "CS1 | CS2",
            "question_patterns_vi": [
                "quy trình khám chữa bệnh cơ sở 1",
                "quy trình khám chữa bệnh cơ sở 2",
                "bệnh viện tim hà nội có flow khám bệnh không",
            ],
            "answer_vi": "Trang Khoa Khám bệnh tự nguyện của Bệnh viện Tim Hà Nội có mục Quy trình khám chữa bệnh và liên kết tới hai sơ đồ: Quy trình khám chữa bệnh tại Bệnh viện Tim Hà Nội cơ sở 1 và Quy trình khám chữa bệnh tại Bệnh viện Tim Hà Nội cơ sở II. Nội dung sơ đồ hiện nằm trong ảnh/link nguồn; dataset này chưa OCR được các bước chi tiết, nên khi trả lời không được tự dựng thứ tự bước nếu chưa có bản text đã kiểm chứng.",
            "source_id": "SRC-HHH-VOLUNTARY-CLINIC-2026-07-18",
            "verified_at": VERIFIED_AT,
            "approval_status": "review_only",
            "safety_warning_vi": "Chỉ dùng như chỉ dẫn nguồn quy trình; chưa đủ để trả lời chi tiết từng bước khám.",
        },
        {
            "fact_id": "GAP-ZALO-BOOKING-GUIDE-VIDEO",
            "document_type": "hospital_booking_channel",
            "topic": "zalo_booking",
            "facility_scope": "all",
            "question_patterns_vi": [
                "đặt lịch qua zalo bệnh viện tim hà nội",
                "zalo mini app bệnh viện tim hà nội",
                "hướng dẫn truy cập zalo bệnh viện tim hà nội",
            ],
            "answer_vi": "Bệnh viện Tim Hà Nội có trang video chính thức tên 'Hướng dẫn truy cập và đặt lịch hẹn trên Zalo Bệnh viện Tim Hà Nội', ngày đăng 27/01/2026. Trang website cũng đặt link Zalo công khai dạng https://zalo.me/s/2972821668579995579/ trong khu vực đăng ký lịch khám online.",
            "source_id": "SRC-HHH-ZALO-GUIDE-2026-07-18",
            "verified_at": VERIFIED_AT,
            "approval_status": "approved_for_hackathon",
        },
        {
            "fact_id": "GAP-HOSPITAL-FACILITY-MASTER",
            "document_type": "hospital_department_service",
            "topic": "department_master",
            "facility_scope": "all",
            "question_patterns_vi": [
                "bệnh viện tim hà nội có mấy cơ sở",
                "cơ cấu khoa phòng bệnh viện tim hà nội",
                "các khoa lâm sàng bệnh viện tim hà nội",
            ],
            "answer_vi": "Trang Giới thiệu chung nêu Bệnh viện Tim Hà Nội có hai cơ sở: số 92 Trần Hưng Đạo, phường Cửa Nam, Hà Nội và số 695 Lạc Long Quân, phường Tây Hồ, Hà Nội. Trang này nêu bệnh viện có 30 khoa/phòng/ban, gồm 16 khoa lâm sàng, 3 khoa cận lâm sàng, 11 khoa/phòng/ban chức năng và hậu cần; phần liệt kê hiện có 11 khoa lâm sàng: Khám bệnh, Nội, Nội Nhi, Tim mạch chuyển hóa, Hồi sức tích cực nhi, Gây mê hồi sức, Hồi sức tích cực, Ngoại, Tim mạch can thiệp, Cấp cứu, Các bệnh mạch máu; 5 khoa cận lâm sàng: Xét nghiệm, Dược, Kiểm soát nhiễm khuẩn, Chẩn đoán hình ảnh, Dinh dưỡng; và 6 đơn nguyên: Khám và điều trị tự nguyện, Thăm dò điện sinh lý và rối loạn nhịp, Sơ sinh, Tim mạch can thiệp cơ sở 2, Can thiệp tĩnh mạch, chẩn đoán hình ảnh kỹ thuật cao.",
            "source_id": "SRC-HHH-GENERAL-INTRODUCTION-2026-07-18",
            "verified_at": VERIFIED_AT,
            "approval_status": "review_only",
            "safety_warning_vi": "Trang nguồn có chênh giữa số tổng hợp và danh sách chi tiết, nên giữ review_only trước khi dùng như master production.",
        },
        {
            "fact_id": "GAP-HOSPITAL-LEADERSHIP-MASTER",
            "document_type": "hospital_person_master",
            "topic": "doctor_department_master",
            "facility_scope": "all",
            "question_patterns_vi": [
                "ban lãnh đạo bệnh viện tim hà nội",
                "lãnh đạo bệnh viện tim hà nội gồm ai",
                "giám đốc phó giám đốc bệnh viện tim hà nội",
            ],
            "answer_vi": "Trang Ban lãnh đạo bệnh viện liệt kê bốn tên: PGS.TS.BS Nguyễn Sinh Hiền, TS.BS Vũ Quỳnh Nga, TS.BS Phạm Như Hùng và TS.Bs Hoàng Văn. Trang nguồn không hiển thị chức vụ dạng text trong phần đã extract, nên dataset không gán chức danh cụ thể cho từng người.",
            "source_id": "SRC-HHH-LEADERSHIP-2026-07-18",
            "verified_at": VERIFIED_AT,
            "approval_status": "review_only",
            "safety_warning_vi": "Không suy luận chức danh từ thứ tự ảnh hoặc kiến thức ngoài trang nguồn.",
        },
        {
            "fact_id": "GAP-SPECIALIZED-SERVICES-GENERAL",
            "document_type": "hospital_department_service",
            "topic": "specialized_services",
            "facility_scope": "all",
            "question_patterns_vi": [
                "dịch vụ chuyên khoa bệnh viện tim hà nội",
                "bệnh viện tim hà nội mạnh về kỹ thuật gì",
                "các mũi nhọn chuyên môn bệnh viện tim hà nội",
            ],
            "answer_vi": "Trang Giới thiệu chung nêu Bệnh viện Tim Hà Nội là trung tâm tim mạch với 5 mũi nhọn: nội khoa, ngoại khoa, nhi khoa, tim mạch can thiệp và tim mạch chuyển hóa. Trang liệt kê các nhóm kỹ thuật như chẩn đoán và điều trị nội khoa tim mạch - chuyển hóa, siêu âm tim Doppler 2D/4D, siêu âm tim qua thực quản, siêu âm tim cản âm, siêu âm Dobutamin, siêu âm tim thai, Holter điện tim, Holter huyết áp, nghiệm pháp gắng sức, MSCT 128 dãy, cộng hưởng từ 1.5 Tesla, can thiệp động mạch vành, nong van hai lá, stent graft, thay van động mạch chủ qua da, điện sinh lý tim, phẫu thuật tim nhi khoa, phẫu thuật sửa/thay van tim và bắc cầu động mạch vành.",
            "source_id": "SRC-HHH-GENERAL-INTRODUCTION-2026-07-18",
            "verified_at": VERIFIED_AT,
            "approval_status": "approved_for_hackathon",
        },
        {
            "fact_id": "GAP-EMERGENCY-HOSPITAL-NOTE",
            "document_type": "hospital_emergency_note",
            "topic": "emergency_official_procedure",
            "facility_scope": "all",
            "question_patterns_vi": [
                "cấp cứu bệnh viện tim hà nội",
                "quy trình cấp cứu bệnh viện tim hà nội",
                "can thiệp cấp cứu mất bao lâu",
            ],
            "answer_vi": "Nguồn hiện có của Bệnh viện Tim Hà Nội chỉ cho phép trả lời an toàn rằng đặt hẹn khám không dành cho trường hợp cấp cứu, không khẩn cấp; khi cấp cứu cần gọi số cấp cứu theo tỉnh/thành dạng mã vùng + 115 hoặc đến thẳng cơ sở cấp cứu gần nhất. Trang Giới thiệu chung có nêu bệnh viện có Khoa Cấp cứu và các bệnh nhân cần can thiệp cấp cứu sẽ được thực hiện trong vòng 1 tiếng từ khi đến bệnh viện, nhưng chưa có trang quy trình cấp cứu chi tiết để hướng dẫn luồng xử trí.",
            "source_id": "SRC-HHH-GENERAL-INTRODUCTION-2026-07-18",
            "verified_at": VERIFIED_AT,
            "approval_status": "review_only",
            "safety_warning_vi": "Không thay thế gọi cấp cứu hoặc đánh giá trực tiếp; không hướng dẫn tự xử trí triệu chứng cấp cứu qua chat.",
        },
        {
            "fact_id": "GAP-ADMISSION-PROCEDURE-UNRESOLVED",
            "document_type": "unresolved_data_gap",
            "topic": "admission",
            "facility_scope": "unknown",
            "question_patterns_vi": [
                "thủ tục nhập viện bệnh viện tim hà nội",
                "vào viện cần giấy tờ gì",
                "quy trình nhập viện bệnh viện tim hà nội",
            ],
            "answer_vi": "Chưa có nguồn chính thức đã extract trong dataset này về thủ tục nhập viện chi tiết của Bệnh viện Tim Hà Nội. Nếu người dùng hỏi thủ tục nhập viện, hệ thống nên nói chưa có dữ liệu xác thực và chuyển sang kênh chính thức: hotline 19001082 hoặc quầy bệnh viện; không tự suy luận giấy tờ, bước làm thủ tục hoặc điều kiện nhập viện.",
            "source_id": "SRC-HHH-BOOKING-GUIDE-2026-07-18",
            "verified_at": VERIFIED_AT,
            "approval_status": "review_only",
            "safety_warning_vi": "Record này là gap guardrail, không phải quy trình nhập viện.",
        },
        {
            "fact_id": "GAP-FOLLOW-UP-GUIDANCE-UNRESOLVED",
            "document_type": "unresolved_data_gap",
            "topic": "follow_up",
            "facility_scope": "unknown",
            "question_patterns_vi": [
                "hướng dẫn tái khám bệnh viện tim hà nội",
                "hẹn tái khám như thế nào",
                "số bệnh nhân hẹn tái khám có nghĩa gì",
            ],
            "answer_vi": "Dataset hiện chỉ thấy widget thống kê 'Số bệnh nhân hẹn tái khám' trên website Bệnh viện Tim Hà Nội, chưa có policy/hướng dẫn tái khám chi tiết đã extract. Nếu người dùng hỏi hướng dẫn tái khám, hệ thống nên nói chưa có dữ liệu xác thực và khuyến nghị liên hệ hotline 19001082, kiểm tra giấy hẹn/phiếu ra viện hoặc hỏi quầy bệnh viện.",
            "source_id": "SRC-HHH-BOOKING-GUIDE-2026-07-18",
            "verified_at": VERIFIED_AT,
            "approval_status": "review_only",
            "safety_warning_vi": "Không dùng widget thống kê để suy ra quy trình tái khám.",
        },
    ]

    rag_records = [rag_record(fact, source_by_id[fact["source_id"]]) for fact in facts]
    write_json(OUT_DIR / "hospital_gap_sources.json", sources)
    write_json(OUT_DIR / "hospital_gap_facts.json", facts)
    write_json(OUT_DIR / "hospital_gap_rag.json", rag_records)
    with (OUT_DIR / "hospital_gap_rag.jsonl").open("w", encoding="utf-8") as handle:
        for record in rag_records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    summary = {
        "bundle": "hera-rag-gap-fill",
        "generated_at": VERIFIED_AT,
        "source_count": len(sources),
        "fact_count": len(facts),
        "rag_record_count": len(rag_records),
        "approval_status_counts": {
            status: sum(fact["approval_status"] == status for fact in facts)
            for status in sorted({fact["approval_status"] for fact in facts})
        },
        "recommended_embedding_field": "retrieval_text",
        "price_pdf_sources_moved_to": [
            "data/gia_bhyt",
            "data/gia_kthuat_theo_yeu_cau",
        ],
    }
    write_json(OUT_DIR / "hospital_gap_summary.json", summary)


if __name__ == "__main__":
    main()
