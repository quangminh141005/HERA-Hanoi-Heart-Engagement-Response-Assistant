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

Thành công của hệ thống không chỉ nằm ở khả năng trả lời tự nhiên, mà còn ở việc trả lời đúng nguồn, biết từ chối khi thiếu thông tin, phát hiện tình huống cấp cứu và hoạt động an toàn trong hạ tầng bệnh viện.;


• ## Kết luận

  HERA hiện ở mức:

   Hạng mục                                                                         Đánh giá
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Demo/hackathon                                                           Tốt, khoảng 8/10
  ─────────────────────────────────  ────────────────────────────────────────────────────────
   Chạy nhiều replica trên một EC2      Có nền tảng, nhưng chưa an toàn khi tải AI tăng mạnh
  ─────────────────────────────────  ────────────────────────────────────────────────────────
   CI/CD                              Khá đầy đủ, còn vài lỗi kiểm soát release nghiêm trọng
  ─────────────────────────────────  ────────────────────────────────────────────────────────
   Production thực tế                             Chưa sẵn sàng; cần xử lý P0 và phần lớn P1

  Điểm đáng lo nhất không phải thiếu cache hay thiếu Redis. Hệ thống đã có khá nhiều cơ chế tốt, nhưng vẫn có bốn lỗi P0 có thể
  làm model ngừng phục vụ, migration sai, hoặc deploy hỏng dữ liệu.

  Phạm vi audit:

  - 289 file được Git theo dõi.
  - Đã duyệt toàn bộ source, config, script, workflow, Docker, monitoring và tài liệu kỹ thuật — khoảng 205 file, hơn 32.000
    dòng code/config/docs.

  - Các file JSON dữ liệu rất lớn được kiểm tra qua schema, manifest, seed pipeline và luồng sử dụng; không đánh giá thủ công
    từng bản ghi nội dung.

  - Ba cấu hình Compose đều hợp lệ.
  - Kiểm tra UTF-8 pass.
  - Bốn container chính đang healthy.
  - Worktree sạch; audit này không sửa file.

  ## Trả lời thẳng câu hỏi về batch

   Thành phần                 Có nên batch không?                      Khuyến nghị
  ━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Embedding query            Có, nhưng chưa phải việc đầu tiên        Singleflight trước, sau đó micro-batch 2–5 ms, tối đa 8–
                                                                       16 query
  ─────────────────────────  ───────────────────────────────────────  ──────────────────────────────────────────────────────────
   Router gpt-oss-20b         Không ghép nhiều người vào một prompt    Dùng priority queue, Redis gate, backpressure
  ─────────────────────────  ───────────────────────────────────────  ──────────────────────────────────────────────────────────
   HyDE gpt-oss-20b           Không cross-user batch                   Gộp query expansion vào output router hoặc chỉ gọi khi
                                                                       retrieval yếu
  ─────────────────────────  ───────────────────────────────────────  ──────────────────────────────────────────────────────────
   Reranker                   Đã batch documents của một query         Chỉ cần gate toàn cụm, timeout và retry đúng
  ─────────────────────────  ───────────────────────────────────────  ──────────────────────────────────────────────────────────
   Generation gpt-oss-120b    Không cross-user batch                   Bounded queue, circuit breaker, cache an toàn
  ─────────────────────────  ───────────────────────────────────────  ──────────────────────────────────────────────────────────
   PostgreSQL retrieval       Không gọi là batching                    Đẩy lexical search vào PostgreSQL FTS và gộp truy vấn

  Embedding adapter đã hỗ trợ list[str], nhưng runtime luôn gửi đúng [query] tại HERA-Hanoi-Heart-Engagement-Response-Assistant/
  apps/backend/app/ai/rag/retrieval/service.py:294. Tuy nhiên nếu thêm batch ngay mà chưa có queue giới hạn, singleflight và
  deadline riêng thì chỉ biến một kiểu nghẽn thành kiểu nghẽn khác.

  ## P0 — bắt buộc sửa trước

  ### 1. Redis lỗi lúc release có thể làm chết toàn bộ slot model

  Tại HERA-Hanoi-Heart-Engagement-Response-Assistant/apps/backend/app/ai/llm/client.py:387, code làm:

  1. Gọi model thành công.
  2. await distributed_gate.release().
  3. Sau đó mới self._semaphore.release().

  Nếu Redis ZREM lỗi ở bước 2:

  - Response model thành công bị biến thành exception.
  - Semaphore cục bộ không được trả.
  - Lặp vài lần sẽ hết toàn bộ permit.
  - Tất cả request model tiếp theo queue timeout.

  Phải sửa bằng nested try/finally: semaphore luôn được trả, còn Redis release là best-effort có log/metric. Cũng cần test mô
  phỏng release() ném exception.

  ### 2. Migration Alembic cũ đã bị sửa trực tiếp

  Dự án chỉ có revision 0001_initial_schema, nhưng constraint tại HERA-Hanoi-Heart-Engagement-Response-Assistant/apps/backend/
  alembic/versions/0001_initial_schema.py:286 đã được thêm afternoon.

  Máy đã chạy revision 0001 sẽ không chạy lại file này. Vì vậy:

  - Database mới clone thì đúng.
  - Database cũ vẫn giữ constraint cũ.
  - Seed mới có afternoon có thể fail dù Alembic báo đang ở head.

  Cần giữ 0001 bất biến và tạo migration 0002 để thay constraint. Sau đó cập nhật revision kỳ vọng trong health và seed script.

  ### 3. Không có đường cập nhật lịch/dữ liệu mới khi hệ thống đã có người dùng

  Khi manifest thay đổi, HERA-Hanoi-Heart-Engagement-Response-Assistant/apps/backend/scripts/seed_postgres.py:487 yêu cầu
  --replace-reference-data. Nhưng đoạn HERA-Hanoi-Heart-Engagement-Response-Assistant/apps/backend/scripts/seed_postgres.py:420
  lại từ chối replace nếu chat, audit, hold hoặc runtime data đã tồn tại.

  Trong khi đó backend bắt buộc chờ seed hoàn thành tại HERA-Hanoi-Heart-Engagement-Response-Assistant/docker-compose.yml:175.

  Kết quả: chỉ cần thêm lịch tuần mới, lần deploy tiếp theo có thể không khởi động được.

  Giải pháp đúng:

  - Import vào staging tables.
  - Validate manifest và FK.
  - Upsert/diff theo source_id hoặc record_id.
  - Không xóa reference row đang được runtime data tham chiếu.
  - Đánh dấu phiên bản cũ inactive thay vì truncate.
  - Tách data migration khỏi startup bình thường.

  ### 4. Image mới có thể chạy với Compose/script cũ trên server

  Workflow deploy chỉ SSH rồi chạy script đang có sẵn trên EC2 tại HERA-Hanoi-Heart-Engagement-Response-Assistant/.github/
  workflows/deploy.yml:104.

  Image được gắn tag commit, nhưng:

  - docker-compose.yml trên server có thể cũ.
  - remote-deploy.sh có thể cũ.
  - Quy tắc migration, env mapping và healthcheck có thể không cùng commit với image.

  Ngoài ra, nếu migration mới đã chạy rồi deploy fail, cleanup tại HERA-Hanoi-Heart-Engagement-Response-Assistant/scripts/
  remote-deploy.sh:156 tự bật image cũ mà không kiểm tra schema compatibility.

  Cần deploy một release bundle đúng SHA hoặc checkout chính xác commit trên server, xác minh worktree sạch, dùng migration
  expand/contract và không tự rollback image sau khi migration phá tương thích đã chạy.

  ## P1 — các điểm quan trọng tiếp theo

  ### AI concurrency và API gateway

  - Embedding không có semaphore, queue timeout hay distributed gate tại HERA-Hanoi-Heart-Engagement-Response-Assistant/apps/
    backend/app/ai/rag/embeddings/embedder.py:70.

  - Cache embedding có Redis nhưng không chống cache stampede. Hai request giống nhau cùng miss vẫn gọi API hai lần.
  - Reranker chỉ có semaphore theo process tại HERA-Hanoi-Heart-Engagement-Response-Assistant/apps/backend/app/ai/rag/
    rerank.py:83.

  - Guard 20b và generation 120b có Redis gate riêng, nhưng không có một ngân sách tổng cho cùng FPT account.

  Với N replica, tải tối đa hiện có thể gần:

  4 guard + 4 generation + 4×N rerank + embedding không giới hạn

  Nên có một provider-wide admission controller, bên trong chia priority:

  1. Emergency/router.
  2. Structured/RAG routing.
  3. Embedding.
  4. Rerank.
  5. HyDE.
  6. Generation thông thường.

  Router và HyDE đang dùng chung guard client nhưng không có ưu tiên, nên HyDE có thể chiếm slot của router an toàn.

  ### Không có circuit breaker và timeout Redis đầy đủ

  Redis gate và rate limiter chưa đặt socket_connect_timeout, socket_timeout và pool bound. Queue timeout 2 giây không bảo vệ
  được một lệnh Redis đang treo.

  Khi FPT lỗi, mỗi request vẫn tiếp tục retry và chờ timeout. Cần:

  - Circuit breaker theo provider/model.
  - Retry budget nằm trong deadline tổng.
  - Jitter.
  - Tôn trọng nhưng giới hạn Retry-After.
  - Trả 429/503 và Retry-After khi overload, thay vì câu fallback dưới HTTP 200.

  ### Pipeline RAG đang quá tuần tự

  Một câu generic có thể phải đi qua:

  router 20b
  → HyDE 20b
  → embedding
  → pgvector/RRF
  → reranker
  → generation 120b

  HyDE còn chạy trước exact lexical fast path tại HERA-Hanoi-Heart-Engagement-Response-Assistant/apps/backend/app/ai/rag/
  retrieval/service.py:71.

  Tối ưu hợp lý nhất:

  - Chạy exact structured/lexical trước.
  - Nếu kết quả đủ chắc thì bỏ HyDE, embedding, rerank và generation.
  - Cho router trả thêm retrieval_query.
  - Chỉ chạy cross-intent retrieval khi lane chính thiếu kết quả.
  - Chạy các truy vấn lexical độc lập song song có giới hạn.

  CHAT_OVERALL_TIMEOUT_SECONDS=35 hiện chỉ bao RAG, chưa bao router tối đa 6 giây, trong khi Nginx timeout 40 giây. Tổng thời
  gian tiềm năng lớn hơn timeout proxy. Deadline phải bắt đầu ngay khi nhận HTTP request và nhỏ hơn timeout phía ngoài.

  ### Lexical search không dùng đúng sức mạnh PostgreSQL

  Repository hiện tải approved facts về Python rồi so token tại HERA-Hanoi-Heart-Engagement-Response-Assistant/apps/backend/app/
  structured/postgres_repository.py:490, trong khi migration đã tạo GIN full-text index.

  Nên dùng:

  - websearch_to_tsquery hoặc plainto_tsquery.
  - ts_rank_cd.
  - Trigram fallback.
  - Filter intent ngay trong SQL.
  - LIMIT trước khi trả về Python.

  Cross-intent hiện chạy thêm cả truy vấn filtered và unfiltered, tăng tải DB và dễ kéo fact sai domain.

  ### Reranker chưa thể thực sự loại kết quả kém

  Tại HERA-Hanoi-Heart-Engagement-Response-Assistant/apps/backend/app/ai/rag/rerank.py:234, score mới dùng max(old_score,
  rerank_score). Vì vậy reranker không thể hạ confidence của candidate sai.

  Ngoài ra raise_for_status() nằm ngoài retry wrapper, nên HTTP 429/502/503 của rerank gần như không được retry đúng.

  Cần:

  - Coi rerank score là tín hiệu mới, không chỉ boost.
  - Áp relevance floor sau rerank.
  - Đưa raise_for_status() vào callback retry.
  - Filter embedding_model và embedding version trong semantic SQL.

  ### Singleflight chưa xử lý cancellation sạch

  LLM và reranker dùng asyncio.shield, nhưng khi HTTP caller bị hủy:

  - Provider call vẫn chạy và vẫn tốn tiền.
  - Task hoàn tất có thể nằm lại trong _in_flight.
  - Kết quả không chắc được cache.
  - Nhiều query độc nhất có thể làm dictionary tăng dần.

  Cần done callback chịu trách nhiệm cleanup/cache thay vì chỉ cleanup trong caller.

  ### Load test chưa đo tải AI

  Stress test hiện chỉ gọi giá, lịch, BHYT, booking và health; nó tự ghi model_api_calls: 0 tại HERA-Hanoi-Heart-Engagement-
  Response-Assistant/scripts/stress_test.py:337.

  Nó cũng chủ yếu dùng năm query cố định nên đo warm cache, và chưa fail theo p95/p99.

  Cần ba loại test:

  - CI miễn phí: provider stub có latency, 429, timeout, Redis failure.
  - Scheduled staging: 10–20 live query, concurrency 2 rồi 4.
  - Load thực: query lặp + query khác nhau, cold/warm cache, SLO p95/p99/error rate/cost.

  ### Cấu hình .env không phải biến nào cũng vào container

  DB_POOL_SIZE, DB_MAX_OVERFLOW, rate-limit thresholds, RAG_MIN_CONFIDENCE và một số Langfuse config có trong Settings/docs
  nhưng không được map vào x-api-environment tại HERA-Hanoi-Heart-Engagement-Response-Assistant/docker-compose.yml:17.

  Dev có thể sửa .env nhưng runtime vẫn âm thầm dùng default. Cần CI test đối chiếu:

  Settings ↔ .env.example ↔ docker-compose environment ↔ docs

  ### Redis đang vừa làm cache vừa làm coordination

  Redis 256 MB dùng volatile-lru tại HERA-Hanoi-Heart-Engagement-Response-Assistant/docker-compose.yml:134.

  Embedding cache hoặc structured cache có thể evict:

  - Rate-limit keys.
  - Conversation memory.
  - Model gate leases.
  - Singleflight/lock keys trong tương lai.

  Tối thiểu nên tách Redis logical purpose:

  - Redis coordination: noeviction.
  - Redis cache: LRU.
  - Nếu vẫn một container, dùng riêng database không đủ để tách maxmemory policy; nên có hai Redis nhỏ hoặc tránh lưu cache
    payload lớn.

  Structured cache key cố định hera:structured:v6, không gắn manifest SHA. Sau cập nhật dữ liệu có thể trả lịch/giá cũ trong
  TTL.

  ### Readiness đang làm quá nhiều việc

  /readyz gọi đồng bộ từ async route, chạy nhiều count/join và materialize mọi booking session. Docker gọi mỗi 30 giây tại HERA-
  Hanoi-Heart-Engagement-Response-Assistant/docker-compose.yml:241.

  Hiện tại đo thực tế vẫn khoảng 24–39 ms, nhưng chi phí sẽ tăng theo dữ liệu và số replica.

  Đồng thời mỗi booking session được tạo hai Prometheus series với label session_id tại HERA-Hanoi-Heart-Engagement-Response-
  Assistant/apps/backend/app/services/health.py:137. Hiện đã hơn 1.000 session.

  Nên tách:

  - /healthz: liveness cực nhẹ, không phụ thuộc Redis.
  - /readyz: DB ping, Redis ping và revision.
  - Full release/data audit: chỉ khi startup/deploy hoặc cache 30–60 giây.
  - Metric booking aggregate theo facility/date/status, không theo mọi session.

  Health và metrics hiện còn đi qua Redis rate limiter; Redis hỏng có thể làm mất luôn liveness và /metrics.

  ### Database và retention

  - Backend runtime dùng cùng role owner với migrate/seed tại HERA-Hanoi-Heart-Engagement-Response-Assistant/docker-
    compose.yml:15.

  - Mỗi chat turn chạy retention cleanup trong transaction.
  - Thiếu một số index cho created_at, expires_at, handoff và expired holds.
  - Expired hold chủ yếu được cập nhật khi session liên quan được truy cập.

  Nên tách:

  - hera_migrator: DDL.
  - hera_app: DML tối thiểu.
  - Retention/expired-hold cleanup thành scheduled job.
  - Index partial cho active/expired holds.

  PostgreSQL hiện có max_connections=100; pool mặc định mỗi replica tối đa 3+2=5. Ba replica vẫn an toàn, nhưng Makefile cho
  scale số replica không giới hạn. Cần kiểm tra:

  replicas × (pool_size + overflow) + migration + monitoring < max_connections

  ### Một EC2 chưa có cô lập tài nguyên và durability

  Không container nào có memory, CPU hay PID limit. Runtime hiện dùng ít RAM, nhưng một process runaway có thể OOM cả EC2.

  Backup chỉ nằm trên cùng server. Nếu mất EC2/EBS thì mất cả DB và backup. Cần:

  - Giới hạn RAM/CPU/PID.
  - EBS riêng/encrypted.
  - Backup PostgreSQL lên S3 SSE-KMS.
  - Lifecycle/retention.
  - Restore rehearsal định kỳ.
  - stop_grace_period ít nhất 45–60 giây.
  - CloudWatch disk/memory/OOM alarms.

  ### Network chưa least-privilege

  Frontend, backend, PostgreSQL, Redis và một phần monitoring cùng chạm network backend. Nếu frontend hoặc Grafana bị
  compromise, attacker có đường mạng trực tiếp tới state stores.

  Nên tách:

  edge ↔ frontend
  frontend_api ↔ backend
  backend_data ↔ PostgreSQL/Redis
  metrics ↔ backend/Prometheus/Grafana

  ### Observability chưa đủ để vận hành thật

  Thiếu:

  - Alertmanager hoặc webhook gửi cảnh báo.
  - Node exporter/cAdvisor.
  - PostgreSQL exporter.
  - Redis exporter.
  - DB pool wait/in-use.
  - Model queue depth/wait/rejection.
  - Gate occupancy.
  - Cache hit/miss từng stage.
  - Provider latency/status/retry/circuit state.
  - Retrieval zero-result và rerank score.

  Prometheus histogram mặc định kết thúc ở bucket 10 giây, trong khi alert muốn phân biệt p95 >10 giây và p99 >35 giây. Cần
  bucket tới 45/60 giây.

  Langfuse không hiện input/output là hành vi chủ ý vì LANGFUSE_CAPTURE_CONTENT=false. Nếu cần debug, chỉ bật capture đã
  redaction trên môi trường test, không bật raw production PII.

  ### Supply chain và CD

  - Base Docker images và GitHub Actions chưa pin digest/full commit SHA.
  - Trivy chỉ scan CRITICAL cho hai app image.
  - Không có SBOM/signature/provenance.
  - GHCR deploy dùng SHA tag nhưng không so digest với digest CI đã phát hành.
  - Job container trên pull request được cấp packages: write.
  - Smoke deploy chỉ kiểm tra mạng nội bộ, không kiểm tra public DNS/TLS.
  - Live model preflight mặc định bị bỏ qua.
  - Restore vào DB hiện tại với --clean có thể để lại object mới không có trong dump cũ.

  ## Dữ liệu runtime hiện tại

  - PostgreSQL: 57 MB, 7 connection trên giới hạn 100.
  - Redis: 1,39 MB/256 MB, 295 hit, 84 miss, 0 eviction.
  - RAM lúc nhàn rỗi:
      - Backend khoảng 112 MiB.
      - PostgreSQL khoảng 112 MiB.
      - Redis khoảng 7 MiB.
      - Frontend khoảng 11 MiB.

  - Không container nào có resource limit.
  - Docker đang có khoảng 31,3 GB image, 19,84 GB có thể thu hồi.
  - Build cache khoảng 12,05 GB có thể thu hồi.
  - hera-embedding:local cũ vẫn xuất hiện khoảng 10,1 GB cùng volume hera_model_cache; chúng không còn thuộc Compose hiện tại
    nhưng vẫn chiếm disk.

  ## Điểm dự án đang làm tốt

  - Backend chạy non-root, read-only, có init.
  - Log Docker có rotation.
  - PostgreSQL/Redis không publish trực tiếp ra host.
  - Có Redis shared memory/rate-limit/model gate khi scale replica.
  - Có checksum seed, migration gate, deterministic export và pre-deploy backup.
  - CI đã có backend/frontend tests, gitleaks, dependency audit, Trivy và stress booking.
  - LLM có semaphore, local singleflight và Redis gate.
  - Embedding query có RAM cache + Redis cache.
  - Nginx dùng Docker DNS nên nhận ra backend replica mới.
  - Encoding gate pass.
  - Compose base, monitoring và stress đều validate thành công.

  ## Thứ tự nâng cấp đề xuất

  1. Sửa semaphore leak và Redis timeout.
  2. Tạo Alembic 0002; tuyệt đối không sửa migration đã phát hành.
  3. Xây data updater versioned cho lịch tuần mới.
  4. Version hóa deployment bundle theo đúng Git SHA và chặn schema-unsafe rollback.
  5. Thêm provider-wide admission control và priority queue.
  6. Thêm embedding singleflight, bounded queue, rồi mới micro-batch.
  7. Chuyển exact lexical trước HyDE, dùng PostgreSQL FTS, cross-intent chỉ fallback.
  8. Sửa reranker retry, score semantics và relevance floor.
  9. Tách readiness nhẹ khỏi release audit; giảm metric cardinality.
  10. Thêm AI load test, circuit breaker, Alertmanager/exporters và off-site backup.

  Tóm lại: nền tảng hiện tại tốt hơn khá nhiều dự án hackathon, nhưng chưa nên scale traffic thật chỉ bằng cách tăng backend
  replicas. Bottleneck và failure domain chính đang nằm ở FPT API admission control, Redis coordination, reference-data update
  và quy trình migration/deploy.
