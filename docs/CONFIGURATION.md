# HERA Configuration Reference

Đây là tài liệu cấu hình cốt lõi cho developer và người vận hành. Giá trị mẫu không
nhạy cảm nằm trong `.env.example`; secret thật chỉ nằm trong secret manager hoặc file
`.env` của đúng máy chạy. Không dán secret vào README, issue, ảnh chụp, command line,
Dockerfile, biến `VITE_*` hay log CI.

Xem thêm:

- [Quản trị dữ liệu](DATA_MANAGEMENT.md)
- [Deploy và vận hành](DEPLOYMENT.md)
- [Hướng dẫn developer](DEVELOPMENT.md)

## 1. Cấu hình được nạp như thế nào?

Với Compose, giá trị shell đang export có thể ghi đè file truyền qua
`--env-file .env`; sau đó mới đến default trong Compose. Backend chỉ nhận biến được map
trong `x-api-environment`. Thêm một field vào Python `Settings` nhưng quên map qua Compose
thì container vẫn không nhận được.

Backend cũng có thể đọc `.env` khi chạy trực tiếp, theo các vị trí workspace, repository
và `apps/backend`. Trong deploy chính thức nên luôn chỉ định đúng một file env.

Frontend là static build. Mọi biến `VITE_*` được đóng vào JavaScript khi build image,
không thay đổi khi chỉ restart container.

Sau khi sửa `.env`:

```bash
docker compose --env-file .env config --quiet
docker compose --env-file .env up -d --force-recreate backend frontend
curl -fsS http://127.0.0.1:8080/readyz
```

Không đưa output của `docker compose config` không có `--quiet` vào log/ticket vì secret
đã được expand.

## 2. Profile được hỗ trợ cho bản demo

```dotenv
APP_DEBUG=false
ENVIRONMENT=hackathon
LLM_PROVIDER=openai
EMBEDDING_PROVIDER=openai
FPT_LLM_MODEL=gpt-oss-20b
FPT_EMBEDDING_MODEL=Vietnamese_Embedding
EMBEDDING_MODEL=Vietnamese_Embedding
EMBEDDING_DIMENSIONS=1024
VECTOR_STORE_PROVIDER=pgvector
BOOKING_PROVIDER=local_prototype
RATE_LIMIT_ENABLED=true
RATE_LIMIT_STORAGE=redis
CONVERSATION_MEMORY_BACKEND=redis
STRUCTURED_CACHE_ENABLED=true
LOG_RAW_MESSAGES=false
```

Không đổi `ENVIRONMENT=production` chỉ vì môi trường GitHub có tên
`hackathon-live`. Validator production cố ý cấm `local_prototype` và capacity rule MVP.
Muốn production thật phải có adapter booking bệnh viện và rule capacity được bệnh viện
phê duyệt.

## 3. Secret và credential

| Biến | Bắt buộc | Cách tạo/cấp | Ghi chú |
|---|---:|---|---|
| `API_KEY` | Có | FPT cấp cho project | Dùng cho LLM và embedding; không commit |
| `POSTGRES_PASSWORD` | Có | 32 byte ngẫu nhiên | Không dùng lại password cá nhân |
| `HOLD_TOKEN_SECRET` | Có | 32 byte ngẫu nhiên | HMAC token giữ chỗ; rotate làm token cũ mất hiệu lực |
| `BOOKING_PII_HASH_SECRET` | Có | 32 byte ngẫu nhiên, khác `HOLD_TOKEN_SECRET` | HMAC tên/SĐT/CCCD/BHYT; rotate làm mất khả năng so khớp hash cũ |
| `GRAFANA_ADMIN_PASSWORD` | Khi bật monitoring | 32 byte ngẫu nhiên | Username mặc định `hera_admin` |
| `LANGFUSE_SECRET_KEY` | Chỉ khi bật Langfuse | Langfuse project cấp | Giữ content capture tắt |
| `LANGFUSE_PUBLIC_KEY` | Chỉ khi bật Langfuse | Langfuse project cấp | Không đủ để bật nếu thiếu secret key |

Linux:

```bash
openssl rand -hex 32
chmod 600 .env
```

Các secret local có thể để trống trong template để `scripts/deploy.sh` tự sinh; không được để
trống `API_KEY`.

`.env.example` được commit; `.env` bị Git ignore. Kiểm trước commit:

```bash
git status --short
git check-ignore .env
```

## 4. PostgreSQL, pgvector và connection pool

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `POSTGRES_DB` | `hera` | Tên database do container tạo |
| `POSTGRES_USER` | `hera_owner` | Owner của schema |
| `POSTGRES_PASSWORD` | không có | Password role/database |
| `DATABASE_URL` | Compose tự tạo | `postgresql+psycopg://...@db:5432/...` |
| `DB_POOL_SIZE` | `3` | Kết nối thường trực tối đa của mỗi backend process |
| `DB_MAX_OVERFLOW` | `2` | Kết nối vượt pool tối đa của mỗi process |
| `DB_POOL_TIMEOUT_SECONDS` | `30` | Thời gian chờ lấy connection |
| `DB_POOL_RECYCLE_SECONDS` | `1800` | Tái tạo connection cũ |
| `VECTOR_STORE_PROVIDER` | `pgvector` | Contract vector store của release |

Mỗi backend có tối đa `DB_POOL_SIZE + DB_MAX_OVERFLOW` connection. Khi scale 3 replica
với default, ngân sách tối đa là 15 connection ứng dụng, chưa tính migration/seed/admin.
Phải so với `max_connections` và tài nguyên server trước khi tăng replica hoặc pool.

Image DB là `pgvector/pgvector:pg16`. Migration `0001_initial_schema` bật extension
`vector` và tạo HNSW index cho vector 1024 chiều. Giá, BHYT, lịch và booking vẫn dùng SQL
có cấu trúc; vector chỉ tìm knowledge chunks/FAQ.

Đổi `POSTGRES_PASSWORD` trong `.env` không tự đổi password role đã tồn tại trong volume.
Rotation phải đổi trong PostgreSQL và file env theo cùng runbook.

## 5. Redis, cache, rate limit và memory

| Biến | Giá trị deploy | Ý nghĩa |
|---|---|---|
| `REDIS_URL` | `redis://redis:6379/0` | Redis nội bộ, không publish host |
| `RATE_LIMIT_ENABLED` | `true` | Bật rate limit backend |
| `RATE_LIMIT_STORAGE` | `redis` | Bắt buộc shared store khi không debug |
| `RATE_LIMIT_DEFAULT_PER_MINUTE` | `120` | Default mỗi client |
| `RATE_LIMIT_CHAT_PER_MINUTE` | `30` | Chat mỗi client |
| `RATE_LIMIT_HEALTH_PER_MINUTE` | `300` | Health mỗi client |
| `CONVERSATION_MEMORY_BACKEND` | `redis` | Ngữ cảnh hội thoại ngắn hạn dùng chung replica |
| `EPHEMERAL_CONTEXT_TTL_MINUTES` | `30` | TTL ngữ cảnh chưa consent |
| `STRUCTURED_CACHE_ENABLED` | `true` | Cache kết quả structured đã duyệt |
| `STRUCTURED_CACHE_TTL_SECONDS` | `300` | TTL cache |
| `STRUCTURED_CACHE_MAX_PAYLOAD_BYTES` | `524288` | Bỏ qua payload quá lớn |
| `REDIS_MAXMEMORY` | `256mb` | Giới hạn memory container Redis |

Cache key dùng hash, không chứa query/PII đọc được; cache fail-open nên Redis cache lỗi
thì truy vấn PostgreSQL. Redis đồng thời là readiness dependency vì rate limit và memory
cần shared state khi scale ngang.

Compose chạy Redis không persistence: `--save "" --appendonly no`. Điều này phù hợp với
cache/rate-limit/context ngắn hạn; dữ liệu authoritative nằm trong PostgreSQL. Redis
restart có thể làm mất context/cache/counter, không làm mất giá/BHYT/lịch/booking hold.

## 6. Model, embedding và timeout

| Biến | Giá trị chốt | Quy tắc |
|---|---|---|
| `FPT_API_BASE_URL` | `https://mkp-api.fptcloud.com` | OpenAI-compatible endpoint |
| `FPT_LLM_MODEL` | `gpt-oss-20b` | Không đổi model trong release này |
| `FPT_EMBEDDING_MODEL` | `Vietnamese_Embedding` | Phải khớp metadata seed |
| `EMBEDDING_MODEL` | `Vietnamese_Embedding` | Tên logic đồng bộ |
| `EMBEDDING_DIMENSIONS` | `1024` | Sai kích thước làm readiness fail |
| `LLM_TIMEOUT_SECONDS` | `30` | Budget một LLM call |
| `LLM_MAX_CONCURRENT_REQUESTS` | `2` | Số request được phép đi vào model cùng lúc trên mỗi backend worker |
| `LLM_QUEUE_TIMEOUT_SECONDS` | `2` | Thời gian chờ slot model; quá hạn trả fallback an toàn |
| `LLM_RESPONSE_CACHE_ENABLED` | `true` | Cache câu trả lời model đã validate trong process |
| `LLM_RESPONSE_CACHE_TTL_SECONDS` | `300` | TTL cache LLM |
| `LLM_RESPONSE_CACHE_MAX_ENTRIES` | `512` | Số entry cache LLM tối đa mỗi worker |
| `EMBEDDING_TIMEOUT_SECONDS` | `10` | Budget embedding query |
| `CHAT_OVERALL_TIMEOUT_SECONDS` | `35` | Deadline toàn pipeline chat |
| `MODEL_TIMEOUT_SECONDS` | `45` | Chỉ dùng model gateway probe |
| `MODEL_PROBE_LLM_MAX_TOKENS` | `8` | Token output tối đa cho live LLM probe; tăng nhẹ khi provider trả rỗng |
| `RAG_TOP_K` | `5` | Số chunk tối đa |
| `RAG_MIN_CONFIDENCE` | `0.55` | Ngưỡng evidence; không hạ để “cố trả lời” |

Nginx có `proxy_read_timeout 40s` nên deadline chat 35 giây phải nhỏ hơn lớp proxy.
Khi model timeout hoặc evidence không đạt, HERA trả fallback/handoff an toàn; không bịa.

`LLM_MAX_CONCURRENT_REQUESTS` là giới hạn trên từng backend worker. Nếu chạy nhiều replica
hoặc nhiều worker, tổng request tối đa đi vào model xấp xỉ bằng số worker nhân với biến này.
Vì vậy khi scale ngang, tăng replica trước nhưng không tăng biến này nếu quota model thấp.

Lệnh duy nhất cố ý gọi live model:

```bash
make model-preflight CONFIRM_MODEL_PREFLIGHT=YES
```

Nó chạy một probe LLM cực nhỏ theo `MODEL_PROBE_LLM_MAX_TOKENS` và một probe embedding đồng thời, không gửi nội dung người dùng và
không in key. Deploy mặc định và unit/integration/smoke/stress/CI không gọi live gateway.

## 7. Dữ liệu và đồng hồ demo

| Biến | Giá trị chốt | Ý nghĩa |
|---|---|---|
| `REFERENCE_DATE_MODE` | `dataset_start` | Dùng ngày lịch sớm nhất làm “hôm nay” của demo |
| `REFERENCE_DATE` | trống | Chỉ bắt buộc khi mode `fixed` |
| `TREAT_PROVIDED_DATA_AS_LATEST` | `true` | Coi dữ liệu tổng hợp là hiện hành |
| `ALLOW_REVIEW_ONLY_DATA` | `false` | Không cho dữ liệu chưa duyệt đi vào câu trả lời |

Giá/BHYT được hiển thị như dữ liệu hiện hành, không gắn năm trong câu trả lời. Lịch luôn
giữ ngày cụ thể. Bundle chứa nhiều tuần để người dùng thấy hôm nay, ngày sau và tuần sau.

Runtime chỉ đọc PostgreSQL đã seed. Không có path SQLite và không mount thư mục `data/`
vào backend. Source/generated vẫn được commit để clean clone có thể regenerate/validate.
Chi tiết nguồn, checksum và cập nhật:
[DATA_MANAGEMENT.md](DATA_MANAGEMENT.md).

## 8. Booking và threshold

| Biến | Giá trị demo | Ý nghĩa |
|---|---|---|
| `BOOKING_PROVIDER` | `local_prototype` | Giữ chỗ cục bộ, không xác nhận bệnh viện |
| `DEFAULT_DOCTOR_CAPACITY_PER_SESSION` | `20` | Mặc định mỗi bác sĩ/ngày/ca |
| `BOOKING_HOLD_TTL_SECONDS` | `300` | Hold hết hạn được loại khỏi occupancy |
| `BOOKING_REQUIRE_APPROVED_DOCTOR` | `true` | Chỉ bác sĩ đã duyệt |
| `BOOKING_REQUIRE_APPROVED_CAPACITY_RULE` | `false` | Demo dùng MVP rule |
| `BOOKING_ALLOW_PROJECT_MVP_RULE` | `true` | Chỉ hợp lệ trong hackathon |
| `BOOKING_MAX_ACTIVE_HOLDS_PER_ANONYMOUS_SESSION` | `2` | Chống chiếm chỗ |

Capacity không phải biến đếm trong RAM. PostgreSQL khóa theo owner/session, kiểm
idempotency, quota và `occupied < capacity_limit` trong transaction. Nhiều backend replica
vẫn dùng cùng một nguồn sự thật nên không được nhận quá threshold.

Đổi default env không tự sửa các session đã seed. Muốn đổi capacity phải có rule được
duyệt, cập nhật bundle, migrate/seed và chạy stress invariant.

## 9. Privacy, CORS và public channel

| Biến | Mặc định | Quy tắc |
|---|---|---|
| `CORS_ORIGINS` | local origin | Production không dùng `*` |
| `VITE_EMBED_PARENT_ORIGINS` | domain bệnh viện | Build-time; CSP phải khớp |
| `CHAT_MAX_CHARS` | `2000` | Giới hạn payload chat |
| `CONSENTED_MESSAGE_TTL_DAYS` | `7` | Retention message có consent |
| `LOG_RAW_MESSAGES` | `false` | Production validator cấm bật |
| `HOSPITAL_HOTLINE` | trống | Chỉ điền sau khi owner xác minh |
| `HOSPITAL_PUBLIC_BASE_URL` | domain bệnh viện | Chỉ link domain chính thức |
| `EMERGENCY_HOTLINE` | `115` | Backend + frontend; frontend cần rebuild |
| `TRUST_PROXY_HEADERS` | `true` trong Compose | Chỉ an toàn khi backend sau proxy nội bộ |
| `TRUSTED_PROXY_CIDRS` | loopback + Docker private | Peer ngoài list không được tin IP header |

`VITE_*` không được chứa secret. Muốn thay domain iframe phải đổi cả build arg và
`frame-ancestors` trong `apps/frontend/nginx.conf` rồi rebuild frontend.

## 10. Network và TLS

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `HERA_BIND_ADDRESS` | `127.0.0.1` | Frontend chỉ mở loopback |
| `HERA_HTTP_PORT` | `8080` | Cổng edge nội bộ |
| `PUBLIC_BASE_URL` | `http://localhost:8080` | Public thật phải HTTPS |
| `MONITORING_BIND_ADDRESS` | `127.0.0.1` | Monitoring chỉ tunnel/VPN |
| `PROMETHEUS_PORT` | `19090` | Loopback |
| `GRAFANA_PORT` | `13000` | Loopback |

PostgreSQL 5432, Redis 6379, FastAPI 8000 và `/metrics` không publish. Backend có network
egress để gọi FPT; frontend Nginx là cổng vào. Khi public, terminate TLS ở host Nginx/LB,
giữ Compose bind loopback và chỉ mở firewall cần thiết.

## 11. Logging, metrics và tracing

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Không dùng DEBUG dài hạn trên public |
| `DOCKER_LOG_MAX_SIZE` | `10m` | Một file log/container |
| `DOCKER_LOG_MAX_FILES` | `5` | Khoảng 50 MB/container |
| `PROMETHEUS_METRICS_ENABLED` | `true` | Expose nội bộ `/metrics` |
| `PROMETHEUS_RETENTION` | `15d` | Retention local |
| `LANGFUSE_ENABLED` | `false` | Chỉ bật sau privacy approval |
| `LANGFUSE_SAMPLE_RATE` | `0.2` | Tỉ lệ trace metadata |
| `LANGFUSE_CAPTURE_CONTENT` | `false` | Không export prompt/answer |

Metrics dùng label hữu hạn; không đưa raw URL, message, doctor name, user ID vào label.
Repository chưa có Alertmanager/notifier, vì vậy alert chỉ được đánh giá và hiển thị.

## 12. Image và release metadata

| Biến | Local | CI/CD |
|---|---|---|
| `HERA_API_IMAGE_REPOSITORY` | `hera-api` | GHCR repository API |
| `HERA_WEB_IMAGE_REPOSITORY` | `hera-web` | GHCR repository web |
| `HERA_IMAGE_TAG` | `local` | Full Git commit SHA đã CI pass |
| `APP_VERSION` | `0.1.0` | Commit SHA khi remote deploy |

CI build, test, scan rồi push đúng image đã qua gate. Remote deploy pull tag SHA, ghi digest
vào `.release.env` và giữ bản trước ở `.release.previous.env`. Không tái build trên server
CI-managed với cùng tag.

## 13. Checklist thay đổi cấu hình

1. Ghi biến, lý do, owner và tác động; không ghi secret value.
2. Backup nếu đổi database, booking, bundle hoặc token secret.
3. Sửa `.env` đúng máy, permission 600/ACL hạn chế.
4. Chạy `docker compose --env-file .env config --quiet`.
5. Recreate backend; rebuild frontend nếu đổi `VITE_*`, CSP hoặc hotline build-time.
6. Chạy verifier data, `/readyz` và smoke.
7. Chỉ chạy live model probe khi cần xác thực key/model, không lặp trong test.
8. Theo dõi Grafana/log bằng request ID và chuẩn bị rollback.
