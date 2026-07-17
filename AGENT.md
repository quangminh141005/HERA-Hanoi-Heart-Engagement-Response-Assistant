# Problem Summary: Intelligent AI Customer Care Assistant for Hanoi Heart Hospital

## 1. Bối cảnh

Bệnh viện Tim Hà Nội là bệnh viện chuyên khoa tim mạch hạng I và là một trong những trung tâm tuyến cuối lớn tại Việt Nam. Mỗi ngày, bệnh viện phục vụ khoảng **2.500–3.000 bệnh nhân ngoại trú**, kéo theo lượng lớn câu hỏi lặp lại từ bệnh nhân và người nhà.

Các câu hỏi phổ biến gồm:

- Đặt lịch khám
- Lịch làm việc của bác sĩ
- Quy trình khám và điều trị
- Quyền lợi bảo hiểm y tế (BHYT)
- Giá dịch vụ
- Thủ tục nhập viện
- Hướng dẫn tái khám
- Thông tin khoa, phòng và dịch vụ chuyên môn

Hiện tại, các yêu cầu này được xử lý qua hotline, website, mạng xã hội và nhân viên tiếp đón. Khối lượng lớn khiến nhân viên quá tải, thời gian phản hồi chậm và chất lượng tư vấn chưa đồng nhất.

## 2. Bài toán cần giải quyết

Xây dựng một **AI Customer Care Assistant** có thể tích hợp trực tiếp vào website Bệnh viện Tim Hà Nội để hỗ trợ bệnh nhân và người nhà tra cứu thông tin, hỏi đáp và thực hiện một số tác vụ liên quan đến dịch vụ bệnh viện.

Hệ thống không phải là bác sĩ AI. Mục tiêu chính là:

- Cung cấp thông tin hành chính và quy trình chính xác
- Hướng dẫn bệnh nhân thực hiện đúng các bước
- Kết nối với hệ thống bệnh viện khi cần dữ liệu thời gian thực
- Giảm tải cho tổng đài và nhân viên tiếp đón
- Bảo đảm an toàn y tế, không bịa thông tin và không tư vấn điều trị vượt phạm vi

## 3. Yêu cầu chức năng chính

### 3.1. Hỏi đáp dựa trên kho tri thức chính thức

Trợ lý phải trả lời chính xác các câu hỏi liên quan đến:

- Đặt lịch khám
- Quy trình khám chữa bệnh
- Bảo hiểm y tế
- Giá dịch vụ
- Giờ làm việc
- Bác sĩ và khoa phòng
- Thủ tục nhập viện
- Tái khám
- Các thông tin chính thức khác của bệnh viện

Giải pháp phù hợp là sử dụng **RAG (Retrieval-Augmented Generation)** để truy xuất thông tin từ tài liệu chính thức trước khi sinh câu trả lời.

### 3.2. Tích hợp hệ thống bệnh viện

Hệ thống cần có khả năng tích hợp API hoặc hệ thống nội bộ để:

- Lấy lịch khám
- Lấy lịch bác sĩ
- Tra cứu thông tin dịch vụ
- Kiểm tra lịch hẹn
- Chuyển người dùng tới website đặt lịch, Zalo Mini App hoặc hotline
- Có thể mở rộng sang đặt, đổi hoặc hủy lịch nếu API cho phép

### 3.3. Trải nghiệm hội thoại

- Hỗ trợ hội thoại bằng văn bản
- Hiểu ngữ cảnh nhiều lượt
- Xử lý tiếng Việt có dấu, không dấu, lỗi chính tả và cách nói đời thường
- Có thể bổ sung ASR để nhận diện giọng nói
- Có thể bổ sung TTS để đọc câu trả lời

### 3.4. Câu trả lời đáng tin cậy

Mọi câu trả lời phải dựa trên nguồn chính thức của bệnh viện.

Hệ thống không được:

- Tự tạo giá dịch vụ
- Tự đoán lịch bác sĩ
- Bịa quy trình
- Suy diễn quyền lợi BHYT
- Khẳng định thông tin khi không có dữ liệu

Khi thiếu thông tin, trợ lý phải nói rõ giới hạn và hướng dẫn người dùng liên hệ đúng kênh hỗ trợ.

### 3.5. Xử lý tình huống cấp cứu

Khi phát hiện các dấu hiệu nguy hiểm như:

- Đau ngực dữ dội
- Khó thở
- Ngất hoặc choáng
- Tím tái
- Tim đập bất thường kèm khó chịu nghiêm trọng

AI không được chẩn đoán, kê thuốc hoặc hướng dẫn điều trị.

Thay vào đó, hệ thống phải ngay lập tức:

- Cảnh báo đây có thể là tình huống khẩn cấp
- Khuyên người dùng gọi cấp cứu hoặc đến cơ sở y tế gần nhất
- Hiển thị hướng dẫn cấp cứu chính thức của bệnh viện
- Cung cấp nút gọi hotline hoặc khoa Cấp cứu nếu có

Trong bài toán này, bỏ sót ca cấp cứu là rủi ro nghiêm trọng nhất.

## 4. Vai trò của tài liệu QT.25.01

Tài liệu **“Quy trình đón tiếp bệnh nhân và khám chữa bệnh ngoại trú tại Khu Tự nguyện 1 – Cơ sở 1”** là một nguồn tri thức chính thức quan trọng cho hệ thống.

Tài liệu mô tả quy trình tổng quát:

```text
Đặt lịch hoặc đến trực tiếp
→ Lấy số tiếp nhận
→ Đăng ký khám
→ Kiểm tra BHYT và giấy tờ
→ Thu phí
→ Đo dấu hiệu sinh tồn
→ Khám bác sĩ
→ Thực hiện cận lâm sàng nếu được chỉ định
→ Quay lại bác sĩ nhận kết luận
→ Hẹn tái khám hoặc làm thủ tục nhập viện
→ Thanh toán và lĩnh thuốc
→ Kết thúc quá trình khám
```

Tài liệu này có thể giúp:

- Xây dựng knowledge base cho RAG
- Trả lời câu hỏi về khám ngoại trú
- Tạo chatbot hướng dẫn từng bước
- Xây dựng intent và conversation flow
- Tạo checklist giấy tờ cho bệnh nhân
- Tạo golden dataset để đánh giá chatbot
- Giảm hallucination nhờ quy trình có căn cứ rõ ràng

Tuy nhiên, tài liệu chỉ áp dụng cho **Khu Tự nguyện 1 – Cơ sở 1**, vì vậy cần gắn metadata rõ ràng để tránh áp dụng nhầm cho các khu khám khác.

## 5. Dữ liệu cần thiết

Hệ thống cần kết hợp ba nhóm dữ liệu:

### Dữ liệu tĩnh

- Quy trình khám
- Quy định BHYT
- Danh sách khoa
- Thủ tục nhập viện
- Hướng dẫn tái khám
- Thông tin liên hệ

### Dữ liệu thời gian thực

- Lịch bác sĩ
- Slot khám còn trống
- Giá dịch vụ mới nhất
- Thông báo nghỉ
- Trạng thái lịch hẹn

Nhóm này nên được lấy qua API thay vì chỉ lưu trong RAG.

### Dữ liệu nhạy cảm

- Họ tên bệnh nhân
- Số điện thoại
- Mã bệnh nhân
- Lịch hẹn cá nhân
- Thông tin BHYT
- Hồ sơ khám chữa bệnh

Nhóm dữ liệu này cần xác thực, phân quyền, mã hóa và hạn chế lưu trong log.

## 6. Kiến trúc đề xuất

```text
Website Chat Widget
        ↓
Chat Backend / API Gateway
        ↓
Safety & Emergency Gate
        ↓
Intent Router
   ┌────┼───────────────┐
   ↓    ↓               ↓
 RAG  Hospital APIs  Human Handoff
   ↓    ↓
Official Knowledge Base
Scheduling / HIS / Service Systems
```

Các thành phần chính:

- Giao diện chat trên website
- Conversation orchestrator
- Intent classification
- RAG engine
- Vector database
- API integration layer
- Emergency handler
- Guardrails
- Human handoff
- Monitoring và logging

## 7. Các thách thức chính

- Tài liệu có thể nằm ở PDF scan, Word, Excel, website hoặc hệ thống nội bộ
- Thông tin có thể thay đổi theo thời gian
- Câu hỏi người dùng thường ngắn, mơ hồ hoặc sai chính tả
- Dữ liệu từ nhiều nguồn có thể mâu thuẫn
- Cần phân biệt thông tin tĩnh và dữ liệu thời gian thực
- Cần tránh tư vấn y tế vượt phạm vi
- Cần phát hiện cấp cứu với độ nhạy cao
- Cần bảo vệ dữ liệu cá nhân và dữ liệu sức khỏe
- Cần chống prompt injection và truy cập trái phép
- Hệ thống phải đủ ổn định để triển khai thực tế

## 8. Cách đánh giá hệ thống

Nên xây dựng golden dataset từ các câu hỏi thực tế và đánh giá bằng các nhóm metric:

- Answer Correctness
- Faithfulness
- Context Recall
- Context Precision
- Citation Accuracy
- Refusal Accuracy
- Emergency Recall
- Emergency False Negative Rate
- Latency P50, P95, P99
- Error rate
- API timeout rate
- Human handoff rate

Trong đó, **Faithfulness**, **Emergency Recall** và **Emergency False Negative Rate** là các chỉ số đặc biệt quan trọng.

## 9. Phạm vi MVP

Một MVP hợp lý nên gồm:

- Chatbot tiếng Việt trên website
- RAG từ tài liệu chính thức
- Hỏi đáp về quy trình khám, BHYT, giờ làm việc, khoa phòng và giá cơ bản
- Trích dẫn nguồn
- Emergency detection
- Hướng dẫn chuyển sang hotline hoặc kênh đặt lịch
- Dashboard theo dõi câu hỏi và lỗi

Các chức năng như đặt lịch trực tiếp, xem lịch cá nhân, ASR, TTS và đa kênh có thể phát triển ở giai đoạn sau.

## 10. Kết luận

Bản chất bài toán là xây dựng một **trợ lý AI chăm sóc khách hàng trong môi trường y tế**, với bốn yêu cầu cốt lõi:

```text
Thông tin chính xác
+ Tích hợp hệ thống bệnh viện
+ An toàn y tế
+ Bảo mật dữ liệu
```

Thành công của hệ thống không chỉ nằm ở khả năng trả lời tự nhiên, mà còn ở việc trả lời đúng nguồn, biết từ chối khi thiếu thông tin, phát hiện tình huống cấp cứu và hoạt động an toàn trong hạ tầng bệnh viện.