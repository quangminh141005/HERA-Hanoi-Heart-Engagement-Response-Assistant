# HERA — Hanoi Heart Engagement Response Assistant

HERA là trợ lý chăm sóc khách hàng ứng dụng AI dành cho Bệnh viện Tim Hà Nội. Mục tiêu của HERA là giúp người bệnh và người nhà tra cứu thông tin bệnh viện nhanh hơn, rõ ràng hơn và an toàn hơn, đồng thời giảm tải cho hotline, quầy tiếp đón và đội ngũ chăm sóc khách hàng.

HERA không phải hệ thống chẩn đoán y khoa. Ứng dụng không kê đơn, không đưa lời khuyên điều trị, không thay thế bác sĩ và không tự tuyên bố một lịch hẹn đã được bệnh viện xác nhận. Trong phạm vi MVP, chức năng đặt lịch được triển khai dưới dạng giữ chỗ prototype dựa trên lịch bác sĩ và ngưỡng tiếp nhận theo từng bác sĩ/ngày/ca.

## Bối cảnh

Bệnh viện Tim Hà Nội là bệnh viện chuyên khoa tim mạch lớn, phục vụ lượng người bệnh ngoại trú rất cao mỗi ngày. Một phần đáng kể yêu cầu hỗ trợ là các câu hỏi lặp lại: lịch bác sĩ, giá dịch vụ, thông tin BHYT, giờ làm việc, hướng dẫn đặt lịch, quy trình khám bệnh, tái khám, nhập viện và kênh liên hệ.

Hiện các câu hỏi này thường được xử lý qua hotline, website, mạng xã hội hoặc nhân viên tiếp đón. Khi số lượng câu hỏi lớn, người bệnh có thể phải chờ lâu, còn bệnh viện phải dành nhiều nguồn lực cho các yêu cầu thông tin cơ bản. HERA được đề xuất như một lớp trợ lý số để xử lý các nhu cầu tra cứu phổ biến trước khi chuyển người dùng tới kênh hỗ trợ chính thức khi cần.

## Vấn đề cần giải quyết

Người bệnh thường gặp ba khó khăn chính khi tìm thông tin bệnh viện.

Thứ nhất, thông tin nằm rải rác ở nhiều nơi như website, file lịch bác sĩ, bảng giá, thông báo, hotline hoặc quầy tiếp đón. Người dùng không phải lúc nào cũng biết nên tìm ở đâu.

Thứ hai, cùng một câu hỏi có thể được diễn đạt theo nhiều cách khác nhau. Ví dụ: “bác sĩ A khám ngày nào”, “tuần sau bác sĩ A có lịch không”, “giá dịch vụ này bao nhiêu”, “có dùng BHYT không”. Nếu chỉ dùng tìm kiếm từ khóa thông thường, trải nghiệm dễ bị đứt đoạn.

Thứ ba, trong lĩnh vực y tế, câu trả lời sai có thể gây rủi ro. Một trợ lý AI cho bệnh viện không được phép bịa thông tin, suy đoán lịch, tự tạo giá dịch vụ hoặc tư vấn điều trị trong tình huống khẩn cấp.

## Ý tưởng giải pháp

HERA kết hợp dữ liệu có cấu trúc, tìm kiếm ngữ nghĩa và mô hình ngôn ngữ để tạo ra một trợ lý chăm sóc khách hàng đáng tin cậy.

Các nhóm thông tin quan trọng như giá dịch vụ, BHYT, lịch bác sĩ và giữ chỗ không phụ thuộc hoàn toàn vào LLM. Những dữ liệu này được lưu trong PostgreSQL và được truy vấn bằng logic backend có kiểm soát. LLM chỉ hỗ trợ diễn đạt tự nhiên, tổng hợp ngữ cảnh và trả lời các câu hỏi cần hội thoại.

Khi có đủ dữ liệu chính thức, HERA trả lời kèm bằng chứng. Khi chưa có dữ liệu, HERA nói rõ là chưa đủ thông tin và hướng người dùng tới kênh hỗ trợ phù hợp. Khi phát hiện dấu hiệu cấp cứu như đau ngực dữ dội, khó thở, ngất hoặc triệu chứng nguy hiểm, HERA không tiếp tục tư vấn thông thường mà chuyển sang hướng dẫn an toàn: gọi cấp cứu hoặc đến cơ sở y tế gần nhất.

## Trải nghiệm người dùng

Người dùng mở giao diện HERA trên trình duyệt và có thể bắt đầu bằng các câu hỏi mẫu hoặc tự nhập câu hỏi bằng tiếng Việt. Giao diện được thiết kế để người dùng hiểu mục đích trong thời gian rất ngắn: đây là trợ lý hỏi đáp thông tin bệnh viện, không phải bác sĩ ảo.

Ứng dụng hiển thị câu trả lời theo dạng dễ đọc, ưu tiên các thẻ thông tin có cấu trúc cho giá dịch vụ, BHYT, lịch bác sĩ và kết quả giữ chỗ. Với chức năng booking, người dùng có thể nhìn thấy thanh ngày nhỏ để biết ngày hiện tại của demo, các ngày tiếp theo và lịch tuần sau. Khi chọn một ca khám, người dùng nhập họ tên, số điện thoại, CCCD và mã thẻ BHYT để giữ chỗ.

Thông tin cá nhân không được đưa vào LLM. Backend chỉ lưu hash HMAC và bản che ký tự để phục vụ kiểm tra/idempotency và hiển thị an toàn.

## Phạm vi MVP

MVP của HERA tập trung vào các chức năng có giá trị demo rõ ràng và có thể hoàn thành trong thời gian ngắn.

Các chức năng đã có trong phạm vi MVP:

- hỏi đáp tiếng Việt dạng text;
- tra cứu giá dịch vụ kỹ thuật từ dữ liệu đã tổng hợp;
- tra cứu thông tin BHYT hiện có trong bộ dữ liệu;
- tra cứu lịch bác sĩ theo ngày, cơ sở và ca;
- hiển thị lịch nhiều ngày để người dùng thấy khả năng đặt hôm nay, ngày sau và tuần sau;
- giữ chỗ prototype theo từng bác sĩ/ngày/ca;
- kiểm soát capacity bằng PostgreSQL transaction để không nhận quá ngưỡng;
- phát hiện tình huống cấp cứu và trả lời theo hướng an toàn;
- lưu thông tin giữ chỗ bằng hash/mask thay vì raw PII;
- dashboard monitoring bằng Prometheus và Grafana;
- Docker Compose deployment;
- CI/CD kiểm tra code, dữ liệu, container, secret, dependency và stress test.

Các chức năng không thuộc MVP hiện tại:

- OCR;
- ASR/TTS;
- xác nhận lịch thật từ hệ thống HIS;
- tư vấn chẩn đoán;
- kê đơn hoặc hướng dẫn điều trị;
- tích hợp production với hệ thống bệnh viện khi chưa có API và phê duyệt.

## Dữ liệu sử dụng

HERA tận dụng dữ liệu đã được tổng hợp trong dự án, bao gồm:

- bảng giá dịch vụ kỹ thuật;
- dữ liệu BHYT;
- lịch bác sĩ theo tuần;
- nguồn tri thức chính thức đã chuẩn hóa;
- dữ liệu test/evaluation dùng để kiểm tra chất lượng;
- PostgreSQL seed archive có checksum để tái tạo database demo.

Hệ thống không dùng SQLite. Dữ liệu runtime được đưa vào PostgreSQL để sau này dễ nâng cấp sang môi trường server thật. Repo chứa seed archive để developer khác có thể clone về, tạo `.env`, chạy deploy và có ngay database demo tương đương.

Tên bác sĩ được tận dụng từ dữ liệu lịch khám thay vì gen giả. Synthetic data chỉ còn dùng ở mức tối thiểu cho fixture, evaluation hoặc stress test.

## Kiến trúc kỹ thuật

HERA sử dụng kiến trúc web app có thể deploy bằng Docker.

Thành phần chính:

- Frontend: React/Vite, phục vụ qua Nginx;
- Backend: FastAPI;
- Database: PostgreSQL + pgvector;
- Cache và state ngắn hạn: Redis;
- AI model: `gpt-oss-20b` cho LLM;
- Embedding: `Vietnamese_Embedding`;
- Monitoring: Prometheus + Grafana;
- CI/CD: GitHub Actions;
- Container registry: GHCR.

Các truy vấn quan trọng như giá, BHYT, lịch và booking đi qua PostgreSQL có cấu trúc. RAG/pgvector dùng cho các phần tri thức cần tìm kiếm ngữ nghĩa. Redis dùng cho cache, rate limit và ngữ cảnh hội thoại ngắn hạn. Backend có cơ chế giới hạn số request vào LLM, queue timeout và response cache để tránh nghẽn khi nhiều người dùng gọi model cùng lúc.

## An toàn và độ tin cậy

HERA được thiết kế theo nguyên tắc “không chắc thì không bịa”. Nếu không có dữ liệu đủ tin cậy, hệ thống phải trả lời rằng chưa có thông tin trong nguồn hiện tại và hướng người dùng tới hotline hoặc kênh hỗ trợ chính thức.

Các lớp an toàn chính:

- không chẩn đoán;
- không kê đơn;
- không tư vấn điều trị trong tình huống cấp cứu;
- câu trả lời phải dựa trên dữ liệu được duyệt;
- thông tin cá nhân không đưa vào LLM;
- booking chỉ là giữ chỗ prototype, không phải lịch hẹn đã xác nhận;
- production validator không cho chạy cấu hình nguy hiểm;
- log không chủ động ghi raw chat, API key, hold token hoặc thông tin định danh nhạy cảm.

## Khả năng triển khai

HERA được chuẩn bị để có thể triển khai nhanh trên server Ubuntu/WSL có Docker.

Luồng triển khai cơ bản:

```bash
cp .env.example .env
chmod 600 .env
nano .env
make deploy
```

Sau khi deploy, hệ thống có:

- frontend tại cổng nội bộ;
- backend API;
- PostgreSQL đã migrate và seed;
- Redis;
- smoke test;
- readiness check;
- monitoring dashboard;
- log có request ID;
- stress test không gọi model thật.

CI/CD được thiết kế để khi push lên `dev` có thể build và publish container phục vụ kiểm thử sớm, còn khi merge vào `main` sẽ build lại container release chính. Image `dev` và `main` dùng tag riêng nên không ghi đè nhau.

## Tính khả thi trong hackathon

HERA phù hợp với hackathon vì giải pháp tập trung vào MVP có thể demo được, không phụ thuộc vào việc phải tích hợp ngay hệ thống bệnh viện thật.

Các phần có thể demo rõ:

- hỏi giá dịch vụ;
- hỏi thông tin BHYT hiện có;
- tìm lịch bác sĩ theo ngày;
- giữ chỗ một ca khám;
- kiểm tra không vượt capacity;
- nhập thông tin người giữ chỗ và thấy backend chỉ lưu hash/mask;
- hỏi câu có dấu hiệu cấp cứu và thấy hệ thống chuyển sang cảnh báo an toàn;
- xem dashboard monitoring;
- chạy smoke/stress test để chứng minh hệ thống có kiểm tra tải và readiness.

## Giá trị mang lại

Đối với người bệnh, HERA giúp giảm thời gian tìm kiếm thông tin và giảm nhu cầu gọi hotline cho các câu hỏi lặp lại.

Đối với bệnh viện, HERA giúp chuẩn hóa câu trả lời, giảm tải nhân sự chăm sóc khách hàng và tạo nền tảng để tích hợp booking/API chính thức trong tương lai.

Đối với bài toán AI trong y tế, HERA thể hiện hướng tiếp cận thực tế: AI không thay bác sĩ, mà hỗ trợ vận hành, tra cứu và điều hướng người dùng dựa trên dữ liệu đáng tin cậy.

## Domain

HERA thuộc lĩnh vực Healthcare AI và Digital Health.

Các nhánh cụ thể:

- tự động hóa chăm sóc khách hàng bệnh viện;
- trợ lý thông tin y tế;
- patient engagement;
- healthcare information retrieval;
- trustworthy AI;
- vận hành bệnh viện số.

HERA không nằm trong nhóm clinical diagnosis AI. Đây là hệ thống hỗ trợ hành chính, thông tin và điều hướng người bệnh.

## Roadmap sau MVP

Các bước phát triển tiếp theo:

1. tích hợp API đặt lịch thật của bệnh viện;
2. xây dựng pipeline cập nhật lịch bác sĩ hằng tuần;
3. bổ sung dữ liệu quy trình khám bệnh, nhập viện và tái khám từ nguồn chính thức;
4. bổ sung dữ liệu quyền lợi BHYT chi tiết với disclaimer rõ ràng;
5. thêm redirect Zalo Mini App;
6. bổ sung giao diện quản trị để nhân sự bệnh viện duyệt dữ liệu;
7. thêm ASR/TTS sau khi đã đánh giá privacy;
8. kiểm thử bảo mật, pháp lý và vận hành trước khi pilot production.

## Tóm tắt đề xuất

HERA là một trợ lý AI chăm sóc khách hàng cho Bệnh viện Tim Hà Nội, tập trung vào việc trả lời thông tin bệnh viện một cách có căn cứ, hỗ trợ tra cứu lịch bác sĩ, giá dịch vụ, BHYT và giữ chỗ prototype. Ứng dụng ưu tiên an toàn, không bịa thông tin, không chẩn đoán và sẵn sàng triển khai bằng Docker với monitoring, CI/CD và kiểm thử tải.

Điểm mạnh của HERA là không chỉ là một chatbot. HERA là một hệ thống hỗ trợ vận hành bệnh viện có dữ liệu, kiểm soát rủi ro, khả năng mở rộng và lộ trình rõ ràng để tiến tới tích hợp thật.
