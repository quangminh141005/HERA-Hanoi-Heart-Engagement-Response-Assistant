# Langfuse Quickstart cho HERA

Langfuse dùng để xem trace AI/RAG: một request chat đi qua bước nào, intent là gì, có emergency hay không, có grounded hay không, mất bao lâu và lỗi ở đâu.

Mặc định HERA tắt Langfuse để tránh gửi dữ liệu ra ngoài:

```dotenv
LANGFUSE_ENABLED=false
LANGFUSE_CAPTURE_CONTENT=false
```

## 1. Khi nào cần bật?

Bật khi bạn muốn debug:

- vì sao câu hỏi bị phân loại sai intent;
- vì sao RAG không tìm được nguồn;
- vì sao LLM timeout/trả rỗng;
- vì sao emergency/model safety được kích hoạt;
- latency từng lượt chat.

Không cần Langfuse để demo bình thường. Grafana dùng để xem hệ thống sống/chết và latency tổng thể; Langfuse dùng để soi từng lượt AI.

## 2. Tạo project Langfuse

1. Vào `https://cloud.langfuse.com`.
2. Đăng nhập hoặc tạo tài khoản.
3. Tạo project mới, ví dụ `hera-hackathon`.
4. Vào phần project settings/API keys.
5. Copy:
   - `public key`;
   - `secret key`;
   - host, thường là `https://cloud.langfuse.com`.

## 3. Bật trong `.env`

Chỉ sửa file `.env`, không sửa `.env.example` để chứa key thật.

```dotenv
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=<public-key-cua-ban>
LANGFUSE_SECRET_KEY=<secret-key-cua-ban>
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_SAMPLE_RATE=1.0
LANGFUSE_CAPTURE_CONTENT=false
```

Giữ `LANGFUSE_CAPTURE_CONTENT=false` cho demo. Khi tắt capture content, HERA chỉ gửi metadata nhỏ như:

- request id;
- channel;
- intent;
- response type;
- grounded true/false;
- emergency true/false.

Không gửi raw prompt, raw answer, số điện thoại, CCCD hoặc mã BHYT.

## 4. Restart backend

Sau khi sửa `.env`:

```bash
docker compose up -d --force-recreate backend
```

Kiểm tra backend còn ready:

```bash
curl -fsS http://127.0.0.1:8080/readyz
```

## 5. Xem trace

1. Mở Langfuse project.
2. Vào mục `Traces`.
3. Gửi một câu hỏi trên UI HERA.
4. Tìm trace tên `hera.chat_turn`.
5. Mở trace và xem metadata.

Các trường nên nhìn:

| Trường | Ý nghĩa |
|---|---|
| `request_id` | Dùng để đối chiếu với backend log |
| `intent` | Hệ thống hiểu câu hỏi thuộc nhóm nào |
| `response_type` | Structured answer, grounded answer, refusal, emergency |
| `grounded` | Câu trả lời có nguồn hay không |
| `emergency` | Có kích hoạt luồng cấp cứu hay không |

## 6. Khi nào được bật capture content?

Chỉ bật khi đã có phê duyệt privacy/security rõ ràng:

```dotenv
LANGFUSE_CAPTURE_CONTENT=true
```

Không bật flag này trong demo public hoặc khi người dùng có thể nhập PII.

