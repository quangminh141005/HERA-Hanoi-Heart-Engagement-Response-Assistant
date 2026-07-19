# HERA - Hanoi Heart Engagement & Response Assistant

## 1. Câu chuyện bắt đầu từ một nhu cầu rất thật

Bệnh viện Tim Hà Nội không phải một đơn vị y tế nhỏ chỉ cần một chatbot FAQ đơn giản. Theo thông tin giới thiệu chính thức, bệnh viện là bệnh viện chuyên khoa đầu ngành tim mạch của Thủ đô Hà Nội, đồng thời là bệnh viện chuyên khoa tim mạch tuyến cuối của cả nước. Bệnh viện khám và điều trị bệnh tim mạch cho người dân Hà Nội và cả nước trên nhiều lĩnh vực: tim mạch nội khoa, tim mạch nhi khoa, tim mạch can thiệp, phẫu thuật tim mạch và tim mạch chuyển hóa. Website bệnh viện cũng thể hiện hệ sinh thái thông tin khá rộng: giới thiệu, dịch vụ, hướng dẫn khám bệnh, bảng giá dịch vụ, lịch làm việc của bác sĩ, đặt lịch khám, trả kết quả online, phổ biến kiến thức, đào tạo, chỉ đạo tuyến và công tác xã hội.

Điều đó tạo ra một bối cảnh rất đặc biệt: người bệnh tim mạch thường cần thông tin nhanh, đúng và dễ hiểu, nhưng thông tin họ cần lại nằm rải rác ở nhiều nơi. Một người nhà bệnh nhân có thể bắt đầu bằng câu hỏi rất nhỏ như "mai bác sĩ nào khám ở cơ sở 1?", rồi chuyển sang "giá siêu âm tim bao nhiêu?", "BHYT có áp dụng không?", "đặt lịch qua đâu?", "cần đến trước bao lâu?", "nếu đau ngực thì có nên chờ lịch hẹn không?". Những câu hỏi này không chỉ là FAQ; chúng là một chuỗi quyết định trong hành trình đi khám.

Website chính thức cho thấy bệnh viện đã có các điểm tiếp xúc số quan trọng: tổng đài 19001082, đặt lịch khám, lịch làm việc của bác sĩ, trả kết quả khám bệnh online và hướng dẫn đặt lịch qua Zalo. Trang hướng dẫn liên hệ đặt lịch khám cũng nêu rõ các khung giờ, hai cơ sở chính, kênh đặt khám qua điện thoại/website và lưu ý rằng việc đặt hẹn khám chỉ có giá trị sau khi bệnh viện xác nhận cuộc hẹn. Đây chính là lý do HERA không nên được thiết kế như một chatbot "nói gì cũng được", mà phải là một lớp trợ lý số biết giới hạn, biết nguồn, biết chuyển tiếp và biết tôn trọng quy trình xác nhận chính thức của bệnh viện.

Đề bài trong `PROJECT_CHECK.md` đặt ra đúng vấn đề này: xây dựng một AI Customer Care Assistant tích hợp được vào website Bệnh viện Tim Hà Nội, hỗ trợ hỏi đáp dựa trên knowledge base chính thức, tra cứu đặt lịch, lịch bác sĩ, quy trình khám, BHYT, bảng giá, giờ làm việc, thông tin khoa/phòng, đồng thời phải có phản hồi đáng tin cậy, không hallucinate, xử lý emergency đúng nguyên tắc và sẵn sàng triển khai với yêu cầu bảo mật, quyền riêng tư, an toàn dữ liệu y tế. HERA được xây dựng để trả lời đúng bài toán đó: không thay thế bác sĩ, không thay thế HIS, nhưng giảm áp lực lặp lại lên tổng đài/quầy tiếp đón và giúp người bệnh đi qua hành trình thông tin một cách rõ ràng hơn.

## 2. Vì sao đề tài này quan trọng với Bệnh viện Tim Hà Nội

Với một bệnh viện chuyên khoa tim mạch tuyến cuối, lượng câu hỏi hành chính lặp lại không hề "nhỏ". Nó ảnh hưởng trực tiếp đến trải nghiệm người bệnh, tải vận hành của nhân viên và khả năng chuẩn hóa thông tin. Người bệnh tim mạch thường có tâm lý căng thẳng hơn so với nhiều nhóm khám thông thường: họ cần biết đúng cơ sở, đúng ca, đúng bác sĩ, đúng giấy tờ, đúng chi phí dự kiến và đúng kênh xử lý khi triệu chứng trở nặng. Nếu phải gọi hotline nhiều lần, đọc nhiều trang web rời rạc hoặc chờ nhân viên giải thích lại các thông tin giống nhau, trải nghiệm khám bệnh sẽ bị kéo dài ngay từ trước khi bệnh nhân đến viện.

HERA giải quyết ba tầng giá trị cho bệnh viện. Tầng thứ nhất là giảm tải câu hỏi lặp lại: giá dịch vụ, mức đóng BHYT hộ gia đình, lịch bác sĩ, quy trình khám, kênh đặt lịch, địa chỉ cơ sở, hotline và các hướng dẫn phổ biến. Tầng thứ hai là chuẩn hóa câu trả lời: cùng một câu hỏi phải trả lời từ cùng một nguồn dữ liệu, có citation và có cảnh báo phạm vi sử dụng. Tầng thứ ba là an toàn y tế: khi người dùng mô tả dấu hiệu nguy cấp như đau ngực dữ dội, khó thở, ngất hoặc triệu chứng giống cấp cứu, HERA không tiếp tục trả lời như tư vấn hành chính mà chuyển sang emergency handoff.

Điểm quan trọng là HERA không cố gắng biến AI thành bác sĩ. Trong môi trường tim mạch, một câu trả lời "có vẻ thông minh" nhưng không có nguồn hoặc đi quá phạm vi có thể nguy hiểm hơn một câu từ chối rõ ràng. Vì vậy HERA chọn vai trò thực tế hơn: trợ lý thông tin chính thức, cầu nối giữa người bệnh và hệ thống bệnh viện, lớp giảm tải cho các câu hỏi phổ biến, đồng thời là hàng rào nhắc người bệnh tìm chăm sóc y tế khẩn cấp khi có tín hiệu nguy hiểm.

## 3. Ý tưởng giải pháp: một trợ lý AI có nghiệp vụ, không phải chatbot tự do

HERA là trợ lý chăm sóc khách hàng AI được thiết kế riêng cho Bệnh viện Tim Hà Nội, hướng tới tích hợp trực tiếp trên website bệnh viện. Sản phẩm cho phép người bệnh và người nhà tra cứu thông tin bằng tiếng Việt tự nhiên, nhận câu trả lời có nguồn, xem dữ liệu cấu trúc dưới dạng dễ đọc và chuyển sang workflow giữ chỗ khám theo ca trong phạm vi bản demo.

Điểm khác biệt cốt lõi của HERA là kiến trúc "grounded AI + structured data + guardrail". Các nhóm thông tin cần độ chính xác cao như bảng giá dịch vụ, mức đóng BHYT hộ gia đình, lịch bác sĩ, ca khám, capacity giữ chỗ và kênh hỗ trợ được lưu trong PostgreSQL. LLM không được phép tự bịa giá, tự bịa lịch bác sĩ hoặc tự suy đoán quyền lợi BHYT cá nhân. LLM được dùng đúng vai trò: hiểu câu hỏi tự nhiên, phân loại ý định, hỗ trợ routing, mở rộng truy vấn, diễn đạt câu trả lời mạch lạc và giúp trải nghiệm hội thoại tự nhiên hơn.

Với thông tin hành chính chung, HERA dùng RAG trên knowledge base chính thức. Câu trả lời chỉ được sinh sau khi retrieval tìm được evidence phù hợp; nếu thiếu evidence hoặc output không vượt qua kiểm tra nguồn, hệ thống từ chối trả lời và hướng người dùng tới kênh chính thức. Đây là nguyên tắc vận hành quan trọng nhất của dự án: trong bệnh viện, câu "HERA chưa có đủ dữ liệu chính thức để trả lời chắc chắn" tốt hơn một câu trả lời trôi chảy nhưng không kiểm chứng được.

## 4. Hành trình người dùng mà HERA phục vụ

Một người dùng không cần biết bảng giá nằm ở trang nào, lịch bác sĩ nằm ở mục nào, hay quy trình đặt lịch có những bước nào. Họ chỉ cần nhập câu hỏi vào giao diện HERA:

- "Dịch vụ Giá Khám bệnh đang niêm yết bao nhiêu?"
- "Mức đóng BHYT hộ gia đình hiện nay là bao nhiêu?"
- "Lịch bác sĩ cơ sở 1 hôm nay"
- "Tuần sau bác sĩ nào có lịch tại cơ sở 2?"
- "Tôi cần chuẩn bị giấy tờ gì khi đi khám?"
- "Thủ tục tái khám tại bệnh viện như thế nào?"

Nếu câu hỏi thuộc nhóm giá dịch vụ, HERA trả về kết quả tra trực tiếp từ bảng dữ liệu đã chuẩn hóa, có tên dịch vụ, cơ sở, mức giá, ghi chú và nguồn. Nếu câu hỏi thuộc nhóm BHYT, HERA chỉ trả lời phạm vi dữ liệu hiện có như mức đóng BHYT hộ gia đình, đồng thời cảnh báo rằng đây không phải quyền lợi cá nhân hoặc số tiền quỹ chi trả cho một dịch vụ cụ thể. Nếu câu hỏi thuộc nhóm lịch bác sĩ, HERA trả về lịch theo ngày, cơ sở, ca, phòng khám hoặc tên bác sĩ, thay vì để model tự đoán.

Nếu người dùng chuyển từ tra lịch sang muốn giữ chỗ, giao diện có phần booking riêng. Người dùng lọc theo tên bác sĩ, ngày khám, ca khám; xem danh sách ca còn chỗ; chọn ca; nhập họ tên và số điện thoại; tùy chọn nhập CCCD hoặc mã BHYT; sau đó xác nhận giữ chỗ tạm. Giao diện hiển thị rõ đây là chức năng nguyên mẫu hackathon, giữ chỗ tự hết hạn và không đồng nghĩa bệnh viện đã xác nhận lịch hẹn. Điều này khớp với quy trình thực tế trên website bệnh viện: đặt hẹn chỉ có giá trị sau khi bệnh viện xác nhận.

Nếu người dùng nói về triệu chứng nguy cấp, luồng hội thoại đổi trạng thái. HERA không hỏi thêm để "chẩn đoán", không gợi ý dùng thuốc, không phân tích bệnh. Hệ thống ưu tiên thông báo cấp cứu, hướng dẫn gọi 115 hoặc đến cơ sở y tế gần nhất. Đây là điểm bắt buộc với một trợ lý trong chuyên khoa tim mạch, vì độ trễ trong các tình huống như đau ngực dữ dội hoặc khó thở có thể gây hậu quả nghiêm trọng.

## 5. Giao diện sản phẩm: AI-native nhưng vẫn giống một công cụ bệnh viện

Giao diện HERA không được thiết kế như một landing page quảng cáo, mà như một công cụ hỗ trợ thông tin có thể dùng ngay. Trang chính gồm hai vùng chức năng: khung chat HERA và khung giữ chỗ khám theo ca. Người dùng nhìn thấy thương hiệu HERA, trạng thái "Trợ lý thông tin", thông điệp "Không thay thế tư vấn y tế", các câu hỏi gợi ý và liên kết cấp cứu gọi 115. Cách trình bày này giúp người dùng hiểu ngay phạm vi của trợ lý: hỏi thông tin hành chính, xem nguồn, nhận cảnh báo, và chuyển sang booking prototype khi phù hợp.

Khung chat có trải nghiệm AI-native ở chỗ người dùng không phải điền form cứng ngay từ đầu. Họ có thể hỏi bằng ngôn ngữ tự nhiên, tiếp tục ngữ cảnh từ câu trước, hỏi lại theo tên bác sĩ hoặc dịch vụ, và nhận kết quả đã được hệ thống phân loại. Mỗi tin nhắn của HERA có nhãn ý định như tra bảng giá, BHYT, lịch bác sĩ, cấp cứu, đặt khám, thủ tục hoặc ngoài phạm vi. Khi có dữ liệu cấu trúc, câu trả lời không chỉ là một đoạn văn mà còn render thành card: bảng giá, mức đóng BHYT, lịch bác sĩ, cảnh báo, citation drawer và handoff card.

Phần booking được thiết kế như một workflow rõ ràng. Người dùng có thể lọc bác sĩ/ngày/ca, chọn nhanh ngày demo hiện tại và các ngày kế tiếp, xem từng card ca khám với bác sĩ, ngày, ca, cơ sở, phòng, capacity còn lại và progress bar số chỗ đã dùng. Khi giữ chỗ thành công, giao diện hiển thị trạng thái hold, countdown còn bao lâu, nút hủy giữ chỗ và cảnh báo rằng đây chưa phải lịch hẹn chính thức. Cách này giúp demo thể hiện được tư duy sản phẩm: AI không chỉ trả lời, mà còn dẫn người dùng tới hành động có kiểm soát.

Về mặt cảm nhận, giao diện cần giữ đúng tinh thần bệnh viện: rõ ràng, tin cậy, ít gây nhiễu, dễ scan, không dùng màu sắc quá phô trương, không biến câu trả lời y tế thành trải nghiệm giải trí. Với bệnh viện tim, "AI-native" không có nghĩa là càng nhiều hiệu ứng càng tốt; nó có nghĩa là câu hỏi tự nhiên, dữ liệu có nguồn, trạng thái an toàn rõ, hành động tiếp theo cụ thể và luôn có đường quay về kênh chính thức.

## 6. Dữ liệu thực tế và cách HERA biến dữ liệu thành knowledge base

Repository HERA đã chuẩn hóa nhiều nhóm dữ liệu để seed vào PostgreSQL: service catalog record, price snapshot, BHYT policy, BHYT tier, schedule document, schedule entry, doctor, booking session, knowledge chunk có vector, support channel và metadata. Các nguồn dữ liệu bao gồm dữ liệu chính thức đã crawl/lưu từ website bệnh viện, PDF bảng giá, lịch bác sĩ theo tuần, dữ liệu generated đã kiểm tra và test fixtures phục vụ đánh giá RAG.

Seed archive được commit tại `apps/backend/data/hera_postgres_seed.json.gz` kèm checksum SHA-256. Bên cạnh đó còn có manifest, validation report, raw/generated data và các script build/verify để đảm bảo dữ liệu không bị import thiếu hoặc sai. Seeder dùng transaction, advisory lock, upsert idempotent và row-count verification, giúp dựng lại môi trường demo ổn định từ repository mà không cần đẩy Docker volume lên GitHub. Runtime đọc PostgreSQL đã seed; raw/generated data được giữ như evidence và pipeline quản trị dữ liệu.

Điểm cần nói chính xác là bản hiện tại không có OCR runtime và không đọc ảnh/PDF người dùng tải lên trong lúc chat. Các tài liệu như PDF/HTML được xử lý ở tầng chuẩn bị dữ liệu, chuyển thành JSON/RAG JSON/JSONL và seed vào PostgreSQL. Nếu sau này bệnh viện muốn tự động cập nhật lịch bác sĩ từ ảnh chụp, bảng biểu hoặc PDF nội bộ, đó sẽ là một module DataOps/OCR riêng có kiểm duyệt, không phải chức năng đã hoàn thiện trong MVP hiện tại.

## 7. Kỹ thuật RAG phía sau: đủ sâu để tin, đủ gọn để triển khai

Luồng RAG của HERA được tổ chức thành nhiều lớp để giảm hallucination. Đầu tiên, câu hỏi người dùng được xử lý privacy redaction trước khi đi vào các bước AI có thể gọi model. Sau đó hệ thống dùng bộ phân loại ý định deterministic kết hợp model routing assessor khi được cấu hình. Các intent như giá dịch vụ, BHYT và lịch bác sĩ được chuyển sang structured lookup; các câu hỏi hành chính chung mới đi qua RAGPipeline.

Retrieval không chỉ dựa vào semantic search. HERA dùng lexical search trên fact đã duyệt để bắt các truy vấn có tên dịch vụ, mã dịch vụ, cụm từ bệnh viện hoặc từ khóa gần đúng. Đồng thời hệ thống có thể gọi Vietnamese_Embedding 1024 chiều để tìm các knowledge chunk tương đồng trong PostgreSQL/pgvector. Ứng viên lexical và semantic được hợp nhất bằng Reciprocal Rank Fusion, sau đó bge-reranker-v2-m3 chọn top evidence tốt nhất. Nếu có một fact chính xác duy nhất vượt ngưỡng exact match, hệ thống ưu tiên deterministic exact answer để an toàn hơn.

Generation cũng có cơ chế kiểm soát riêng. Prompt hệ thống yêu cầu LLM chỉ dùng fact liên quan trực tiếp trong context; không thêm giá, lịch, bác sĩ, URL, số điện thoại, chẩn đoán hoặc lời khuyên điều trị ngoài evidence. Sau khi model sinh câu trả lời, `evidence_validator` kiểm tra câu trả lời có được hỗ trợ bởi evidence hay không. Nếu không đạt, output model bị loại bỏ và hệ thống quay về câu trả lời deterministic từ fact đã duyệt. Nếu không có citation, hệ thống từ chối trả lời. Đây là cấu trúc RAG có trách nhiệm: model giúp diễn đạt, nhưng nguồn dữ liệu và validator quyết định câu trả lời được phép hiển thị.

Cấu hình mặc định của project dùng model gateway tương thích OpenAI qua FPT: `gpt-oss-120b` cho generation, `gpt-oss-20b` cho guard/routing, `Vietnamese_Embedding` cho embedding và `bge-reranker-v2-m3` cho rerank. Redis hỗ trợ cache, rate limit và ngữ cảnh hội thoại ngắn hạn. PostgreSQL + pgvector lưu dữ liệu cấu trúc, trạng thái booking và vector knowledge. FastAPI đóng vai trò backend API, React/Vite là frontend, Nginx là cổng vào, Prometheus/Grafana theo dõi vận hành.

## 8. Guardrail y tế, quyền riêng tư và handoff

HERA có nhiều lớp guardrail thay vì chỉ dựa vào prompt. Input guardrail chặn yêu cầu ngoài phạm vi hành chính bệnh viện, prompt injection hoặc các yêu cầu lạm dụng hệ thống. Output guardrail yêu cầu câu trả lời cần grounding phải có citation. Emergency detector có lớp deterministic an toàn cao và có thể được bổ sung bởi model routing. Handoff service đưa người dùng về kênh hỗ trợ chính thức khi câu hỏi cần xác nhận nghiệp vụ hoặc vượt quá dữ liệu.

Privacy là một biên quan trọng. HERA không đưa raw PII vào LLM trong luồng booking. Họ tên, số điện thoại, CCCD và mã BHYT được xử lý bằng HMAC hash và dạng che ký tự ở backend. Hệ thống cũng không chủ động log raw chat, API key, hold token, số điện thoại, email hoặc số thẻ BHYT. Log phục vụ vận hành có request ID, event, latency, result code và trạng thái kỹ thuật, nhưng tránh ghi lại nội dung nhạy cảm.

Trong ngữ cảnh bệnh viện, guardrail không phải một tính năng phụ. Nó là điều kiện để AI có thể được tin. HERA không trả lời quyền lợi BHYT cá nhân nếu dữ liệu chỉ có mức đóng hộ gia đình. HERA không ghép bảng giá với BHYT để tính hóa đơn thực trả. HERA không xác nhận lịch hẹn chính thức khi bản demo chỉ giữ chỗ tạm. HERA không diễn giải xét nghiệm hoặc chẩn đoán qua chat. Những giới hạn này làm sản phẩm thực tế hơn, vì chúng phản ánh đúng trách nhiệm của một trợ lý thông tin y tế.

## 9. Booking prototype: có workflow nhưng không vượt quá quy trình bệnh viện

Website Bệnh viện Tim Hà Nội cho thấy bệnh viện có đặt lịch qua điện thoại, website và Zalo; đồng thời nêu rõ người bệnh cần đặt trước, có mặt trước giờ hẹn và lịch hẹn chỉ có giá trị sau khi bệnh viện xác nhận. Vì vậy HERA thiết kế booking trong MVP như một "local prototype hold", tức là mô phỏng giữ chỗ theo capacity chứ không tuyên bố đã đặt lịch thành công với bệnh viện.

Backend quản lý booking session theo bác sĩ/ngày/ca. Người dùng chỉ tạo hold sau khi chọn ca và nhập thông tin tối thiểu. Hold có TTL, có idempotency key để tránh double submit, có quota số hold đang hoạt động trên mỗi anonymous session và có transaction để kiểm soát capacity. Người dùng có thể hủy hold; khi hold hết hạn, capacity được làm mới. Trên giao diện, mọi điểm nhạy cảm đều có cảnh báo "bản demo" để không gây hiểu nhầm với lịch hẹn thật.

Thiết kế này vừa đủ để chứng minh năng lực workflow, vừa không tạo overclaim. Nó cho thấy HERA có thể mở rộng sang HIS/API đặt lịch chính thức sau này, nhưng vẫn tôn trọng sự thật hiện tại: MVP chưa tích hợp HIS và chưa xác nhận cuộc hẹn thay bệnh viện.

## 10. Khả năng scale và triển khai thực tế

HERA được thiết kế theo hướng có thể scale ngang. Backend FastAPI có thể chạy nhiều replica vì state quan trọng nằm ở PostgreSQL và Redis. PostgreSQL lưu dữ liệu chuẩn, vector knowledge và booking state; Redis chia sẻ cache, rate limit và ngữ cảnh hội thoại ngắn hạn. Nginx/load balancer phía trước chỉ nên gửi traffic tới instance vượt qua `/readyz`, không chỉ `/healthz`, vì readiness mới kiểm tra đủ PostgreSQL, Redis, Alembic revision, checksum dữ liệu, model/embedding config, lịch, emergency template và booking capacity.

Repository đã có Docker Compose, Alembic migration, seed archive, Makefile, deploy script, smoke test, stress test booking, script backup/restore/rollback, release packaging, kiểm tra UTF-8, kiểm tra generated data và monitoring stack. Với server có Docker, luồng triển khai có thể bắt đầu từ `.env`, chạy `make deploy` hoặc `bash scripts/deploy.sh --monitoring`, sau đó kiểm `/readyz` và smoke test. Khi cần xác thực model thật, project có model preflight và RAG live check riêng để kiểm generation, guard/routing, embedding, rerank, citation và UTF-8.

Về scale lớn, HERA không phụ thuộc vào việc "một chatbot trả lời tất cả bằng một model". Các truy vấn phổ biến và dữ liệu chuẩn được phục vụ bằng structured lookup/cache; RAG chỉ dùng khi cần truy xuất knowledge base; model generation có concurrency limit, timeout và fallback. Đây là cách scale thực tế hơn cho bệnh viện: giảm số lần gọi model đắt, giữ các câu trả lời cần độ chính xác cao trong database, và chỉ dùng LLM ở nơi nó tạo giá trị rõ ràng.

## 11. Phần nào đã đáp ứng đề bài

So với yêu cầu trong `PROJECT_CHECK.md`, HERA đã bao phủ các nhóm chính. Với knowledge-based question answering, hệ thống có RAG grounded trên knowledge base và structured lookup cho giá, BHYT, lịch. Với hospital system integration, MVP chưa tích hợp HIS thật nhưng đã có kiến trúc tách provider booking (`local_prototype`, `redirect_only`, `hospital`) và các endpoint có thể nối sang API bệnh viện sau này. Với conversational experience, frontend hỗ trợ chat text tiếng Việt, câu hỏi gợi ý, ngữ cảnh ngắn hạn và hiển thị kết quả dạng card.

Với trustworthy AI responses, HERA có citation, evidence validation, deterministic fallback và refusal khi thiếu nguồn. Với emergency handling, HERA phát hiện tín hiệu cấp cứu và chuyển sang emergency handoff thay vì tư vấn điều trị. Với deployment readiness, project có Docker Compose, migration, seed checksum, readiness gate, monitoring, rate limit, privacy redaction, logging an toàn và backup/rollback script. ASR/TTS hiện chưa có, nên nên trình bày là hướng mở rộng, không phải tính năng hiện tại.

## 12. Những điểm còn thiếu để production thật

Dù luồng giữ chỗ prototype đã được xây dựng khá chặt chẽ với transaction, HMAC hash, TTL, idempotency và quota, để vận hành chính thức vẫn cần các bổ sung nghiệp vụ quan trọng.

Đồng bộ thời gian thực với HIS: hệ thống hiện chưa xác thực bệnh án, mã BHYT, trạng thái người bệnh, lịch sử đặt khám hoặc xung đột với tổng đài/quầy tiếp đón. Khi production, cần API HIS hoặc booking gateway chính thức để xác nhận lịch, cập nhật trạng thái và tránh ghost booking.

Xử lý ngoại lệ và giao dịch bán phần: khi tích hợp thật, cần outbox pattern, retry queue, trạng thái giao dịch rõ ràng và compensation transaction. Ví dụ, nếu capacity đã được giữ ở HERA nhưng HIS trả lỗi muộn, hệ thống phải giải phóng quota, ghi audit và thông báo nhất quán.

Chính sách đổi/hủy/ưu tiên: MVP có tạo hold và hủy hold, nhưng production cần reschedule, cancel, cut-off time, xác thực chủ sở hữu, giới hạn số lần đổi ca, xử lý bác sĩ đổi lịch và chính sách ưu tiên do bệnh viện quyết định. AI không nên tự xếp ưu tiên y tế.

Audit trail y tế: log kỹ thuật chưa đủ cho kiểm toán nghiệp vụ. Cần bảng audit riêng cho hành động có giá trị pháp lý như đồng ý cung cấp thông tin, tạo/hủy giữ chỗ, chuyển handoff, thay đổi trạng thái từ HIS hoặc nhân viên can thiệp.

Effective date cho dữ liệu: bảng giá, BHYT và lịch bác sĩ cần versioning theo ngày hiệu lực, ngày hết hiệu lực, approval status và khả năng trả lời theo ngày khám thực tế, không chỉ theo bộ dữ liệu mới nhất.

Quản trị vòng đời dữ liệu RAG: mỗi fact nên có nguồn, người chịu trách nhiệm, ngày nhập/crawl, ngày duyệt, trạng thái phê duyệt, lịch hết hạn, regression tests và rollback. RAG tốt không cứu được dữ liệu sai; vì vậy DataOps là điều kiện sống còn.

OCR và tài liệu động: bản hiện tại không có OCR runtime. Nếu cần tự động cập nhật lịch từ PDF/ảnh/bảng nội bộ, nên xây thành pipeline riêng: OCR nội bộ, parser bảng, kiểm schema, so khớp bác sĩ/phòng, human-in-the-loop approval, sinh embedding và update PostgreSQL. Không nên public dữ liệu OCR chưa được duyệt.

Phân quyền vận hành: production cần vai trò cho nhân viên chăm sóc khách hàng, đội dữ liệu, người duyệt nghiệp vụ, quản trị kỹ thuật và auditor. Mỗi vai trò chỉ được xem/sửa phần phù hợp.

## 13. Rào cản lớn nhất khi ra mắt

Rào cản lớn nhất không chỉ là thuật toán. HERA đã có nền kỹ thuật tốt, nhưng một hệ thống trả lời cho bệnh viện cần được phê duyệt, được vận hành, được cập nhật và được chịu trách nhiệm.

Chấp thuận pháp lý và trách nhiệm y tế là rào cản đầu tiên. Bệnh viện cần quy định HERA được phép trả lời nhóm thông tin nào, câu trả lời nào chỉ mang tính tham khảo, khi nào bắt buộc chuyển hotline, ai chịu trách nhiệm khi dữ liệu sai và quy trình đính chính/truy vết ra sao.

Độ tin cậy dữ liệu động là rào cản thứ hai. Lịch bác sĩ, bảng giá, chính sách BHYT và kênh tiếp nhận có thể thay đổi. Nếu dữ liệu chưa cập nhật hoặc chưa được duyệt, câu trả lời vẫn sai dù RAG hoạt động tốt. Vì vậy phải có quy trình DataOps liên tục: nhập dữ liệu, kiểm tra tự động, duyệt nghiệp vụ, publish, rollback và theo dõi lỗi.

Niềm tin vận hành là rào cản thứ ba. Nhân viên y tế có thể lo hệ thống tạo thêm việc đối soát; người bệnh có thể vẫn gọi hotline để xác nhận lại. Giai đoạn ra mắt mềm nên giới hạn phạm vi, đào tạo nhân viên, gắn thông điệp rõ HERA là trợ lý thông tin hành chính và đo các chỉ số như tỷ lệ câu hỏi tự xử lý được, tỷ lệ handoff đúng, tỷ lệ người dùng cần gọi lại hotline, lỗi citation và phản hồi không hữu ích.

Phụ thuộc model gateway và chính sách dữ liệu nhạy cảm cũng cần quyết định rõ. Bản hiện tại dùng provider tương thích OpenAI qua FPT model gateway và có redaction để không gửi raw PII. Nếu bệnh viện yêu cầu tuyệt đối không phụ thuộc API bên thứ ba, cần triển khai inference nội bộ hoặc gateway riêng đạt chuẩn bảo mật.

## 14. Kết luận

HERA là một giải pháp phù hợp với bài toán thực tế của Bệnh viện Tim Hà Nội vì nó xuất phát từ đúng hành trình người bệnh: tìm lịch, hỏi giá, hỏi BHYT, hỏi thủ tục, đặt lịch, cần hỗ trợ khẩn cấp và cần câu trả lời có nguồn. Dự án không chỉ trình diễn một chatbot, mà trình diễn một kiến trúc trợ lý y tế có trách nhiệm: dữ liệu cấu trúc trong PostgreSQL, RAG có retrieval nhiều lớp, evidence validation, citation, guardrail, privacy redaction, booking hold prototype, monitoring và khả năng deploy.

Điểm cần trình bày mạnh nhất là HERA biết giới hạn. Nó không chẩn đoán, không kê đơn, không tính quyền lợi BHYT cá nhân khi thiếu dữ liệu, không xác nhận lịch hẹn thay bệnh viện và không đọc OCR runtime trong bản MVP. Chính sự rõ ràng này làm giải pháp đáng tin hơn. Một trợ lý AI cho bệnh viện không cần cố tỏ ra biết mọi thứ; nó cần biết câu nào được trả lời, câu nào phải có nguồn, câu nào phải chuyển người thật và câu nào phải ưu tiên cấp cứu.

Với nền tảng hiện tại, HERA đủ tốt để demo như một sản phẩm AI-native phục vụ chăm sóc khách hàng bệnh viện: giao diện có chat, kết quả cấu trúc, citation, cảnh báo, giữ chỗ theo ca và dashboard vận hành; backend có dữ liệu seed kiểm chứng, RAG pipeline, structured lookup, guardrail và readiness gate. Để trở thành sản phẩm production, HERA cần bổ sung HIS integration, quy trình duyệt dữ liệu, audit trail, effective date, phân quyền vận hành, quy trình pháp lý và kiểm thử RAG liên tục. Đây là lộ trình thực tế, chuyên nghiệp và phù hợp với một bệnh viện tim mạch tuyến cuối.

## 15. Nguồn dữ kiện thực tế đã đối chiếu

- Website chính thức Bệnh viện Tim Hà Nội: https://benhvientimhanoi.vn/
- Giới thiệu chung Bệnh viện Tim Hà Nội: https://benhvientimhanoi.vn/vn/cong/thong-tin/gioi-thieu-chung
- Hướng dẫn liên hệ đặt lịch khám: https://benhvientimhanoi.vn/vn/cong/thong-tin/huong-dan-lien-he-dat-lich-kham
- Khoa Khám bệnh tự nguyện: https://benhvientimhanoi.vn/vn/cong/thong-tin/khoa-kham-benh-tu-nguyen
- Giá dịch vụ kỹ thuật áp dụng tại Bệnh viện Tim Hà Nội 2025: https://benhvientimhanoi.vn/vi/chi-tiet-lich-kham/bang-gia-dich-vu/gia-dich-vu-ky-thuat-ap-dung-tai-benh-vien-tim-ha-noi-2025
- Hướng dẫn truy cập và đặt lịch hẹn trên Zalo Bệnh viện Tim Hà Nội: https://www.benhvientimhanoi.vn/vi/thu-vien-video/chi-tiet/huong-dan-truy-cap-zalo-benh-vien-tim-ha-noi
