# HERA Data Gap Source Links

File này là checklist nguồn để bổ sung dữ liệu thật, giảm synthetic data và tăng độ phủ
theo `PROBLEM.md`. Ưu tiên extract từ nguồn chính thức của Bệnh viện Tim Hà Nội, sau đó
mới dùng nguồn nhà nước như BHXH/Bộ Y tế cho chính sách BHYT chung.

## 1. Đã đủ tương đối trong seed hiện tại

| Nhóm đề bài | Trạng thái hiện tại | Ghi chú |
|---|---|---|
| Giá dịch vụ kỹ thuật | Có 2.946 service catalog record, 4.051 price snapshot | Cần bổ sung giá BHYT và giá theo yêu cầu nếu muốn trả rộng hơn |
| Lịch bác sĩ | Có 18 schedule document, 1.382 schedule entry | Cần duy trì crawl/extract lịch tuần mới |
| Booking prototype | Có 771 booking session, threshold 20 | Chưa phải API booking/capacity thật của bệnh viện |
| BHYT household contribution | Có 2 policy, 10 tier | Mới là mức đóng hộ gia đình; chưa đủ quyền lợi/mức hưởng cá nhân |
| Contact/support channel | Có hotline và booking web | Cần bổ sung Zalo Mini App nếu demo yêu cầu |

## 2. Còn thiếu theo `PROBLEM.md`

| Thiếu gì? | Vì sao cần? | Link nguồn đề xuất để extract |
|---|---|---|
| Quy trình khám chữa bệnh chi tiết | Đề bài yêu cầu trả lời medical examination/treatment procedures | Menu hướng dẫn khám bệnh của website có mục “Quy trình khám chữa bệnh”; cần crawl đúng page từ website bệnh viện |
| Thủ tục nhập viện | Đề bài nêu hospital admission procedures trong nhóm câu hỏi phổ biến | Chưa tìm thấy page nhập viện rõ ràng trên website; nên hỏi bệnh viện hoặc extract từ tài liệu nội bộ |
| Hướng dẫn tái khám | Đề bài nêu follow-up appointment guidance | Website có widget “Số bệnh nhân hẹn tái khám”, nhưng chưa có policy/hướng dẫn đủ rõ; cần extract nếu bệnh viện có page riêng |
| Quyền lợi BHYT/mức hưởng | Seed hiện chỉ có mức đóng hộ gia đình | Dùng nguồn BHXH/Bộ Y tế hiện hành, nhưng phải ghi rõ không thay thế tư vấn quyền lợi cá nhân |
| Bảng giá BHYT bệnh viện | Đề bài yêu cầu BHYT benefits + service pricing | Trang “Bảng giá Bảo Hiểm Y Tế tại Bệnh Viện Tim Hà Nội” |
| Bảng giá dịch vụ theo yêu cầu | User hỏi giá có thể không chỉ là kỹ thuật thông thường | Trang “Bảng báo giá Dịch vụ kỹ thuật theo yêu cầu” |
| Zalo đặt lịch | Đề bài yêu cầu redirect Website/Zalo Mini App/hotline | Video “Hướng dẫn truy cập và đặt lịch hẹn trên Zalo Bệnh viện Tim Hà Nội” |
| Doctor/department master | Hiện doctors suy ra từ schedule, chưa có hồ sơ khoa/phòng/bác sĩ canonical | Extract các trang giới thiệu, khoa/phòng, ban lãnh đạo, dịch vụ |
| Dịch vụ chuyên khoa | Đề bài yêu cầu specialized medical services | Trang giới thiệu chung và các trang dịch vụ/khoa |
| Emergency official procedure | Hiện chỉ có emergency generic 115/handoff | Cần nguồn bệnh viện về khoa cấp cứu/quy trình cấp cứu nếu có; nếu không, giữ câu trả lời an toàn 115/đến cơ sở cấp cứu gần nhất |

## 3. Link cụ thể nên extract

### Bệnh viện Tim Hà Nội

- Hướng dẫn liên hệ đặt lịch khám: `https://benhvientimhanoi.vn/vn/cong/thong-tin/huong-dan-lien-he-dat-lich-kham`
- Khoa Khám bệnh tự nguyện: `https://benhvientimhanoi.vn/vn/cong/thong-tin/khoa-kham-benh-tu-nguyen`
- Chuyên mục lịch làm việc bác sĩ: `https://benhvientimhanoi.vn/vi/chuyen-de/lich-lam-viec-cua-bac-sy/trang-1`
- Ví dụ lịch bác sĩ tuần: `https://benhvientimhanoi.vn/vi/chi-tiet/lich-lam-viec-cua-bac-sy/lich-kham-benh-cua-cac-bac-si-benh-vien-tim-ha-noi-tuan-tu-ngay-04d11d2024-10d11d2024`
- Bảng báo giá dịch vụ kỹ thuật: `https://benhvientimhanoi.vn/vi/chi-tiet/bang-gia-dich-vu/bang-bao-gia-dich-vu-ky-thuat-tai-benh-vien-tim-ha-noi`
- Bảng giá BHYT tại bệnh viện: `https://benhvientimhanoi.vn/vi/chi-tiet/bang-gia-dich-vu/bang-gia-bao-hiem-y-te-tai-benh-vien-tim-ha-noi.`
- Bảng giá dịch vụ kỹ thuật theo yêu cầu: `https://benhvientimhanoi.vn/vi/chi-tiet/bang-gia-dich-vu/bang-bao-gia-dich-vu-ky-thuat-theo-yeu-cau-tai-benh-vien-tim-ha-noi.`
- Hướng dẫn truy cập/đặt lịch trên Zalo: `https://www.benhvientimhanoi.vn/vi/thu-vien-video/chi-tiet/huong-dan-truy-cap-zalo-benh-vien-tim-ha-noi`
- Giới thiệu chung/chuyên khoa: `https://benhvientimhanoi.vn/vn/cong/thong-tin/gioi-thieu-chung`
- Ban lãnh đạo: `https://benhvientimhanoi.vn/vn/cong/thong-tin/ban-lanh-dao`
- Cơ sở 2 chuyển địa điểm: `https://benhvientimhanoi.vn/vi/chi-tiet/tin-tuc-noi-bo/benh-vien-tim-ha-noi-co-so-2-se-chuyen-dia-diem-kham-benh-sang-trung-tam-y-te-quan-tay-ho`

### Nguồn BHYT nhà nước

- BHXH Việt Nam — mở rộng quyền lợi BHYT từ 01/07/2026:
  `https://baohiemxahoi.gov.vn/tintuc/Pages/linh-vuc-bao-hiem-y-te.aspx?CateID=169&ItemID=26712&OtItem=date`
- BHXH Việt Nam — chính sách BHYT từ năm 2026:
  `https://baohiemxahoi.gov.vn/tintuc/Pages/linh-vuc-bao-hiem-y-te.aspx?CateID=169&ItemID=25920`
- Bộ Y tế — điểm mới chính sách BHYT từ 01/07/2026:
  `https://moh.gov.vn/index.jsp?aid=168401&cid=7241&pageId=5803`
- Bộ Y tế — bảo đảm thông suốt khám chữa bệnh BHYT:
  `https://moh.gov.vn/thong-tin-chi-dao-dieu-hanh/-/asset_publisher/DOHhlnDN87WZ/content/bao-am-thong-suot-kham-chua-benh-bhyt-khong-anh-huong-en-quyen-loi-cua-nguoi-benh`

## 4. Field contract đề xuất khi bổ sung

### `hospital_procedure_facts.json`

```json
{
  "fact_id": "PROC-...",
  "topic": "exam_flow | admission | follow_up | payment | documents",
  "question_patterns_vi": [],
  "answer_vi": "",
  "facility_scope": "CS1 | CS2 | all | unknown",
  "source_url": "",
  "source_title": "",
  "verified_at": "YYYY-MM-DD",
  "approval_status": "review_only | approved_for_hackathon | approved_for_production"
}
```

### `bhyt_benefits.json`

```json
{
  "benefit_id": "BHYT-BENEFIT-...",
  "scope": "general_policy",
  "condition_vi": "",
  "benefit_vi": "",
  "exclusions_vi": "",
  "effective_from": "YYYY-MM-DD",
  "effective_to": null,
  "source_url": "",
  "source_title": "",
  "approval_status": "review_only"
}
```

### `hospital_departments_services.json`

```json
{
  "department_id": "DEPT-...",
  "name_vi": "",
  "facility_code": "CS1 | CS2 | all | unknown",
  "service_summary_vi": "",
  "source_url": "",
  "source_title": "",
  "approval_status": "review_only"
}
```

## 5. Quy tắc nhập dữ liệu

1. Không đưa HTML raw vào runtime.
2. Mỗi fact phải có `source_url`, `source_title`, `verified_at`, `approval_status`.
3. Nội dung BHYT cá nhân phải có warning: không thay thế xác nhận quyền lợi tại quầy/BHXH.
4. Lịch bác sĩ phải giữ ngày cụ thể; không “nâng đời” lịch cũ thành lịch mới.
5. Doctor master không nên suy luận từ chức danh/nhãn lớp học như `SHCLBBN COPD(S)`.
6. Runtime chỉ dùng row đã `approved_for_hackathon` hoặc `approved_for_production`.
