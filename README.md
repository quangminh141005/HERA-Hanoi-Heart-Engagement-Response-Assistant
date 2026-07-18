# HERA — Hanoi Heart Engagement Response Assistant

HERA là trợ lý chăm sóc khách hàng cho Bệnh viện Tim Hà Nội. Bản hiện tại có thể tra cứu
thông tin có nguồn, giá dịch vụ, mức đóng BHYT hộ gia đình, lịch bác sĩ theo ngày và giữ
chỗ tạm theo ngưỡng của từng bác sĩ/ngày/ca. HERA không chẩn đoán, không kê đơn và không
tuyên bố một lịch hẹn đã được bệnh viện xác nhận.

Chỉ cần clone repository này là có đủ code và dữ liệu để dựng môi trường demo:

- PostgreSQL + pgvector lưu toàn bộ dữ liệu và trạng thái booking;
- Redis dùng chung cho cache, rate limit và ngữ cảnh hội thoại ngắn hạn;
- FastAPI là backend; React/Vite là frontend; Nginx là cổng vào duy nhất;
- Prometheus + Grafana có sẵn qua Compose monitoring;
- file seed PostgreSQL có checksum đã được commit tại
  `apps/backend/data/hera_postgres_seed.json.gz`.

Không có SQLite và không có OCR trong hệ thống.

## 1. PostgreSQL Docker có được đẩy lên GitHub không?

Không. GitHub không chứa container, image hay Docker volume của máy bạn.

| Thành phần | Có trong GitHub? | Ý nghĩa |
|---|---:|---|
| `docker-compose.yml` | Có | Công thức tạo PostgreSQL, Redis, backend và frontend |
| Alembic migration | Có | Tạo schema PostgreSQL/pgvector |
| Seed archive + SHA-256 | Có | Dữ liệu chuẩn để nạp lại một DB mới |
| Docker image đã build trên máy | Không | Có thể build lại; CI có thể push image lên GHCR |
| Volume `hera_postgres_data` | Không | Dữ liệu đang chạy chỉ tồn tại trên Docker host |
| File `.env` và mật khẩu thật | Không | Phải tạo riêng trên từng máy/server |
| File backup `*.dump` | Không | Lưu mã hóa ngoài repo |

Vì vậy, khi chuyển sang server: clone repo, tạo `.env` rồi chạy deploy. Compose tạo DB,
migration tạo bảng và seed archive nạp dữ liệu. Muốn mang theo dữ liệu phát sinh như
feedback hoặc booking hold, phải dùng backup/restore PostgreSQL; không thể push volume
lên GitHub.

## 2. Chạy nhanh nhất trên Ubuntu/WSL

Yêu cầu:

1. Docker Engine hoặc Docker Desktop/WSL integration đang chạy;
2. Git;
3. GNU Make;
4. một `API_KEY` hợp lệ cho FPT model gateway.

Clone repo và tạo `.env`:

```bash
git clone <URL-REPOSITORY-CỦA-BẠN>
cd HERA-Hanoi-Heart-Engagement-Response-Assistant
cp .env.example .env
chmod 600 .env
nano .env
```

Trong `.env`, điền tối thiểu:

```dotenv
API_KEY=<khóa FPT của bạn>
POSTGRES_PASSWORD=
HOLD_TOKEN_SECRET=
BOOKING_PII_HASH_SECRET=
GRAFANA_ADMIN_PASSWORD=
```

Không điền ví dụ trên bằng mật khẩu thật trong tài liệu. Có thể để trống các secret nội bộ:
script deploy sẽ sinh ngẫu nhiên và ghi vào file `.env` đã bị Git ignore.

Giải thích từng dòng cần nhìn trong `.env`:

| Dòng | Bạn làm gì? | Nếu không biết thì làm gì? |
|---|---|---|
| `API_KEY=` | Dán key FPT model gateway thật vào sau dấu `=` | Bắt buộc phải có để dùng LLM/embedding thật. Không commit, không chụp ảnh |
| `POSTGRES_PASSWORD=` | Có thể để trống | Script deploy tự sinh password PostgreSQL local |
| `HOLD_TOKEN_SECRET=` | Có thể để trống | Script tự sinh secret ký token giữ chỗ |
| `BOOKING_PII_HASH_SECRET=` | Có thể để trống | Script tự sinh secret hash tên/SĐT/CCCD/BHYT; phải khác hold secret |
| `GRAFANA_ADMIN_PASSWORD=` | Có thể để trống khi bật monitoring | Script tự sinh password đăng nhập Grafana |
| `MODEL_PROBE_LLM_MAX_TOKENS=8` | Giữ nguyên mặc định | Chỉ tăng nhẹ, ví dụ `16`, khi live model probe trả rỗng |
| `LANGFUSE_ENABLED=false` | Giữ nguyên | Chưa cần Langfuse để demo; bật sau khi hiểu privacy |

Không sửa các dòng này khi mới chạy lần đầu:

```dotenv
ENVIRONMENT=hackathon
APP_DEBUG=false
FPT_LLM_MODEL=gpt-oss-20b
FPT_EMBEDDING_MODEL=Vietnamese_Embedding
EMBEDDING_DIMENSIONS=1024
BOOKING_PROVIDER=local_prototype
REFERENCE_DATE_MODE=dataset_start
```

Sau khi điền `.env`, chạy một lệnh:

```bash
make deploy
```

`make deploy` tương đương luồng: kiểm config/data → build image → migrate → seed
PostgreSQL → đợi readiness → smoke test → bật monitoring. Nếu máy chưa có `make`, dùng trực tiếp:

```bash
bash scripts/deploy.sh --monitoring
```

Script sẽ kiểm cấu hình/checksum, build image, migrate, seed PostgreSQL, đợi readiness và
smoke test. Deploy mặc định không gọi API trả phí. Khi thành công:

- ứng dụng: http://127.0.0.1:8080
- Grafana: http://127.0.0.1:13000
- Prometheus: http://127.0.0.1:19090

Username Grafana mặc định là `hera_admin`. Password là giá trị
`GRAFANA_ADMIN_PASSWORD` trong `.env`; không gửi file này qua chat/email và không commit.

Sau deploy, dùng hệ thống như sau:

1. Mở `http://127.0.0.1:8080`.
2. Ở khung chat, thử các câu mẫu về giá, BHYT, lịch bác sĩ hoặc thủ tục.
3. Kéo xuống khu booking, chọn ngày trên thanh ngày nhỏ, chọn ca, nhập thông tin giữ chỗ.
4. Sau khi bấm xác nhận, backend chỉ lưu hash/mask thông tin người giữ chỗ.
5. Mở `http://127.0.0.1:13000`, đăng nhập Grafana để xem hệ thống có healthy không.

Nếu `http://127.0.0.1:8080` không mở được:

```bash
docker compose ps --all
docker compose logs --tail 100 frontend
docker compose logs --tail 100 backend
```

Nếu `readyz` fail:

```bash
curl -fsS http://127.0.0.1:8080/readyz
```

Đọc trường `checks` trong JSON: check nào `false` thì xem log service liên quan.

Chỉ khi cần xác thực key/model lần cuối, chạy đúng một probe LLM cực nhỏ
(`MODEL_PROBE_LLM_MAX_TOKENS=8` trong `.env`) và một probe embedding:

```bash
bash scripts/deploy.sh --monitoring --model-preflight
```

Không lặp lệnh này trong test hoặc restart thường.

## 3. Chạy nhanh trên Ubuntu server

Server cần Docker Engine + Docker Compose plugin, tối thiểu nên có 4 vCPU, 8 GB RAM và
30 GB SSD cho demo kèm monitoring. Sau khi clone:

```bash
cd HERA-Hanoi-Heart-Engagement-Response-Assistant
cp .env.example .env
chmod 600 .env
nano .env
bash scripts/deploy.sh --monitoring
```

Script tự sinh `POSTGRES_PASSWORD`, `HOLD_TOKEN_SECRET`, `BOOKING_PII_HASH_SECRET` và
`GRAFANA_ADMIN_PASSWORD` nếu đang trống. `API_KEY` phải do bạn cấp. Không dùng
`admin/admin`, không tái sử dụng mật khẩu cá nhân và không ghi secret vào shell history.

Mặc định các cổng chỉ bind `127.0.0.1`. Trước khi có HTTPS, mở SSH tunnel từ laptop:

```bash
ssh -L 8080:127.0.0.1:8080 \
    -L 13000:127.0.0.1:13000 \
    -L 19090:127.0.0.1:19090 <user>@<server>
```

Khi public, giữ HERA bind loopback và đặt Nginx/load balancer TLS phía trước theo
`infra/nginx/edge-tls.example.conf`. Chỉ mở 443 cho người dùng; không public PostgreSQL,
Redis, FastAPI, Prometheus hoặc Grafana.

Hướng dẫn server, TLS, credential, CI/CD, backup và rollback đầy đủ:
[Deployment runbook](docs/DEPLOYMENT.md).

## 4. Cách biết deploy đã thật sự ổn

```bash
docker compose ps --all
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/readyz
docker compose logs --tail 100 backend
```

Kết quả đúng:

- `db`, `redis`, `backend`, `frontend`: running/healthy;
- `migrate` và `seed`: exited với mã 0;
- `/healthz` trả `status=ok`;
- `/readyz` trả HTTP 200, `status=ok` và mọi `checks` là `true`.

`healthz` chỉ nói tiến trình còn sống. `readyz` mới xác nhận PostgreSQL, migration,
Redis, checksum/manifest, dữ liệu bắt buộc, vector 1024 chiều, lịch và capacity booking.
Load balancer chỉ nên gửi traffic tới replica vượt qua `readyz`.

## 5. Monitoring cho người mới

Mở Grafana, đăng nhập và chọn dashboard `HERA Overview`. Theo dõi trước tiên:

- API/backend có `up` hay không;
- tỉ lệ 5xx và p95/p99 latency;
- PostgreSQL/Redis dependency;
- readiness/release gate;
- grounding failure và upstream timeout;
- số hold, occupancy và capacity của booking;
- độ phủ lịch tuần kế tiếp;
- hit/miss/error của structured Redis cache.

Alert rule đã có, nhưng repository chưa có Alertmanager hay kênh gửi email/Slack.
Nghĩa là Prometheus/Grafana hiển thị cảnh báo, chưa tự nhắn cho người trực.

Tìm một request lỗi:

```bash
docker compose logs backend | grep "<request_id>"
```

Log là JSON stdout và được rotate. Hệ thống không chủ động log raw chat, API key,
hold token, số điện thoại, email hoặc số thẻ BHYT.

Grafana là gì?

- Grafana là màn hình quan sát hệ thống.
- Nó không phải database và không phải nơi sửa dữ liệu.
- Dùng nó để biết app đang sống hay chết, request có chậm không, DB/Redis có lỗi không,
  booking có vượt capacity không.

Prometheus là gì?

- Prometheus đi lấy số liệu từ backend.
- Grafana đọc Prometheus rồi vẽ dashboard.
- Bạn thường không cần mở Prometheus nếu chỉ demo; mở Grafana là đủ.

Langfuse là gì?

- Langfuse là công cụ trace LLM/RAG để debug vì sao model trả lời như vậy.
- Release này để `LANGFUSE_ENABLED=false` mặc định.
- Không bật `LANGFUSE_CAPTURE_CONTENT=true` nếu chưa được duyệt privacy, vì nó có thể gửi
  nội dung prompt/answer ra dịch vụ ngoài.
- Muốn bật an toàn cho demo nội bộ chỉ metadata:

```dotenv
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=<public key>
LANGFUSE_SECRET_KEY=<secret key>
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_CAPTURE_CONTENT=false
LANGFUSE_SAMPLE_RATE=0.2
```

Sau khi sửa `.env`, recreate backend:

```bash
docker compose up -d --force-recreate backend
```

## 6. Các lệnh thường dùng

Trên Ubuntu/WSL có GNU Make:

```bash
make help
make config-check
make data-validate
make db-bootstrap
make up
make status
make logs SERVICE=backend TAIL=200
make smoke
make monitoring-up
make monitoring-status
make backup
make down
```

Khi cập nhật source: `make data-generate`. Chỉ data owner đã review canonical
PostgreSQL mới chạy `make data-export CONFIRM_DATA_EXPORT=YES`. Scale backend dùng
`make scale REPLICAS=3`.

`docker compose down` giữ volume. Không thêm `-v` trừ khi bạn thực sự muốn xóa dữ liệu.

Stress test không gọi model:

```bash
make stress
make stress-extreme CONFIRM_EXTREME=YES
```

Profile extreme tạo project `hera-stress` tách biệt, chạy ba backend replica, kiểm phân
phối replica và invariant không vượt capacity, sau đó dọn volume test.

## 7. Model và cách dùng dữ liệu

- LLM cố định: `gpt-oss-20b`.
- Embedding cố định: `Vietnamese_Embedding`, 1024 chiều.
- Endpoint: `https://mkp-api.fptcloud.com`, giao thức OpenAI-compatible.
- Giá, BHYT, lịch và booking đi bằng truy vấn PostgreSQL có cấu trúc.
- pgvector chỉ dùng cho knowledge chunks/FAQ cần semantic retrieval.
- Redis cache kết quả structured đã duyệt; cache lỗi thì truy vấn PostgreSQL.
- Giá/BHYT được coi là dữ liệu hiện hành của demo và câu trả lời không gắn năm.
- Lịch luôn hiển thị theo ngày có trong dữ liệu; ngày tham chiếu là ngày sớm nhất để
  demo được hôm nay, ngày sau và tuần sau.

## 8. Giới hạn an toàn cần nhớ

- Booking là giữ chỗ prototype, chưa phải xác nhận lịch bệnh viện.
- Threshold mặc định là 20 người cho một bác sĩ/ngày/ca và được kiểm trong transaction
  PostgreSQL; không tăng trực tiếp trong DB.
- Khi phát hiện dấu hiệu khẩn cấp, HERA không tư vấn điều trị mà hướng người dùng gọi
  115/đến khoa Cấp cứu.
- Khi thiếu bằng chứng, HERA phải từ chối trả lời chắc chắn và chuyển kênh hỗ trợ.
- Không có OCR, ASR hay TTS trong release này.
- `ENVIRONMENT=production` cố ý từ chối booking prototype; đây là rào chắn, không phải lỗi.

## 9. Tài liệu tiếp theo

- [Cấu hình cốt lõi](docs/CONFIGURATION.md)
- [Hướng dẫn developer](docs/DEVELOPMENT.md)
- [Quản trị dữ liệu](docs/DATA_MANAGEMENT.md)
- [Deploy và vận hành](docs/DEPLOYMENT.md)
- [Tài liệu kỹ thuật tổng thể](../TECHNICAL.md)
