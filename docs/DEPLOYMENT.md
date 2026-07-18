# HERA Deployment & Operations Runbook

Runbook này dành cho developer/DevOps. Người mới bắt đầu ở [README](../README.md).
Cấu hình từng biến nằm ở [CONFIGURATION.md](CONFIGURATION.md), dữ liệu ở
[DATA_MANAGEMENT.md](DATA_MANAGEMENT.md).

Kết luận ngắn: có server cài Docker là deploy được từ repository này. GitHub chứa code,
migration, raw/generated evidence và PostgreSQL seed archive; server tự tạo volume,
migrate và seed. Docker volume, secret và backup không đi lên GitHub.

## 1. Yêu cầu server

Mức khởi điểm hợp lý cho demo kèm monitoring:

- Ubuntu 22.04/24.04 x86_64;
- 4 vCPU, 8 GB RAM, 30 GB SSD;
- Docker Engine và Docker Compose plugin;
- outbound HTTPS tới FPT gateway/GHCR nếu dùng;
- DNS và TLS certificate khi public;
- account deploy riêng, không chạy hàng ngày bằng root.

Kiểm:

```bash
docker version
docker compose version
openssl version
df -h
free -h
```

Account nằm trong group `docker` có quyền gần tương đương root. Chỉ cấp cho operator/CI
được tin cậy.

## 2. Artifact và layout

Clone repository là đủ để tạo DB demo:

```text
HERA-Hanoi-Heart-Engagement-Response-Assistant/
├── data/                              # raw + generated reproducible evidence
├── apps/backend/data/
│   ├── hera_postgres_seed.json.gz
│   └── hera_postgres_seed.json.gz.sha256
├── apps/backend/alembic/
├── docker-compose.yml
├── docker-compose.monitoring.yml
├── infra/
└── scripts/
```

Runtime chỉ nạp seed archive vào PostgreSQL. Raw/generated không được mount vào backend.
Không có `*.db`.

GitHub không chứa:

- `.env`;
- Docker volume;
- DB dump;
- TLS/SSH/private key;
- production log/trace.

## 3. Account, username và secret

Không có password thật trong repository. Các giá trị dưới đây là tên account/biến, không
phải credential bí mật.

| Tên | Ai tạo/cấp | Nơi lưu | Cách kiểm |
|---|---|---|---|
| `POSTGRES_USER=hera_owner` | team chốt | `.env` | `psql ... -c "select 1"` trong container |
| `POSTGRES_DB=hera` | team chốt | `.env` | migration/ready pass |
| `POSTGRES_PASSWORD` | deploy script hoặc operator sinh | secret manager/`.env` | DB healthy; không in value |
| `API_KEY` | FPT project cấp | secret manager/`.env` | model gateway probe |
| `HOLD_TOKEN_SECRET` | operator sinh | secret manager/`.env` | smoke create/release hold |
| `BOOKING_PII_HASH_SECRET` | deploy script hoặc operator sinh | secret manager/`.env` | HMAC thông tin người giữ chỗ; phải khác `HOLD_TOKEN_SECRET` |
| `GRAFANA_ADMIN_USER=hera_admin` | team chốt | `.env` | login Grafana |
| `GRAFANA_ADMIN_PASSWORD` | operator sinh | secret manager/`.env` | login Grafana |
| `LANGFUSE_PUBLIC_KEY` / `SECRET_KEY` | Langfuse cấp, tùy chọn | secret manager | trace metadata khi bật |
| TLS private key | ACME/CA/LB | host/LB secret store | TLS handshake |
| `DEPLOY_SSH_PRIVATE_KEY` | admin tạo riêng cho CI | GitHub Environment secret | SSH BatchMode |
| `DEPLOY_KNOWN_HOSTS` | admin xác minh fingerprint | GitHub Environment secret | host key pin |

Sinh secret Linux:

```bash
openssl rand -hex 32
```

Các secret PostgreSQL/hold/PII/Grafana phải khác nhau. Không dùng ví dụ như
`password123`, không dùng secret cá nhân, không dùng secret trong Docker build arg.

`deploy.sh` tự sinh các secret nội bộ nếu trống; `API_KEY` phải có thật. File `.env` phải được
giới hạn quyền bằng `chmod 600 .env`.

## 4. Deploy một lệnh

```bash
cp .env.example .env
chmod 600 .env
nano .env
make deploy
```

Nếu máy chưa có GNU Make, dùng trực tiếp script Linux:

```bash
bash scripts/deploy.sh --monitoring
```

Trong `nano`, tối thiểu chỉ cần điền `API_KEY=<key FPT thật>`. Các dòng
`POSTGRES_PASSWORD=`, `HOLD_TOKEN_SECRET=`, `BOOKING_PII_HASH_SECRET=` và
`GRAFANA_ADMIN_PASSWORD=` có thể để trống để script tự sinh. Không xóa dòng, không thêm
dấu ngoặc kép quanh secret.

Sau khi clone/pull code và đã có `.env`, hai lệnh thường dùng nhất là:

```bash
make deploy
make smoke
```

Lệnh đầu dựng toàn bộ stack. Lệnh thứ hai kiểm lại health/readiness/giá/BHYT/lịch/
emergency/booking qua gateway, không gọi model thật.

Hai script:

1. tạo/siết quyền `.env`;
2. sinh các local secret nếu thiếu;
3. lấy `API_KEY` từ `.env`, hoặc `../.env` khi dev;
4. kiểm release manifest nếu chạy từ package;
5. validate Compose bằng `config --quiet`;
6. build backend/frontend;
7. verify seed checksum/format/version;
8. không gọi model nếu operator không yêu cầu flag explicit;
9. `up --wait` để migrate, seed, start app;
10. chạy same-origin smoke structured/emergency/booking không gọi model.

Deploy mặc định không tiêu API. Chỉ xác thực gateway lần cuối khi thật sự cần:

```bash
bash scripts/deploy.sh --monitoring --model-preflight
```

Flag này chạy đúng một LLM probe theo `MODEL_PROBE_LLM_MAX_TOKENS`, tối thiểu 1024 trong
`.env` và một embedding probe đồng thời.

Sau khi probe kết nối đạt, trước khi mở demo hãy chứng minh toàn bộ RAG chạy bằng
model thật trong container cuối cùng:

```bash
make rag-live-check CONFIRM_RAG_LIVE_CHECK=YES
```

Gate này tạo một truy vấn paraphrase có mã ngẫu nhiên để tránh cache, sau đó yêu cầu:

- routing có `decision_source=model`;
- generation có `generation_mode=model_validated`;
- có evidence record và citation chính thức;
- token LLM input/output và token embedding đều tăng so với trước request;
- failure/timeout của FPT không tăng;
- JSON response là UTF-8 và khai báo `charset=utf-8`.

Thiếu bất kỳ điều kiện nào thì lệnh fail. Đây là paid release gate có chủ ý, không
chạy trong CI, stress test, restart hoặc health check định kỳ.

Restart thường không chạy
deploy script:

```bash
docker compose up -d --no-build
```

## 5. Kiểm sau deploy

```bash
docker compose ps --all
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/readyz
docker compose logs --tail 100 backend
```

Mong đợi:

- `db`, `redis`, `backend`, `frontend` healthy;
- `migrate`, `seed` Exited 0;
- `healthz` HTTP 200;
- `readyz` HTTP 200, `status=ok`, toàn bộ check true.

Readiness kiểm PostgreSQL ping, Alembic revision, Redis, manifest/checksum, data counts,
approval lane, embedding model/dimension, lịch, emergency template và booking capacity.
Không bỏ qua gate để mở traffic.

Smoke riêng:

```bash
make smoke
```

Smoke kiểm health/readiness/runtime clock, giá hit/no-match, BHYT, lịch hit/no-match,
emergency và create/idempotent/release hold; `model_api_calls=0`. RAG/FAQ dùng model
thật chỉ nằm trong gate trả phí `rag-live-check` có xác nhận riêng.

## 6. Network, TLS và firewall

Compose mặc định:

- chỉ frontend publish `127.0.0.1:8080`;
- backend, PostgreSQL, Redis ở network nội bộ;
- `/metrics` không đi qua frontend;
- Grafana/Prometheus bind loopback;
- backend có egress HTTPS tới model gateway.

Local/server trước TLS dùng SSH tunnel:

```bash
ssh -L 8080:127.0.0.1:8080 \
    -L 13000:127.0.0.1:13000 \
    -L 19090:127.0.0.1:19090 <deploy-user>@<server>
```

Public:

1. trỏ DNS A/AAAA về server/LB;
2. cấp certificate ACME/CA;
3. dùng `infra/nginx/edge-tls.example.conf` làm mẫu;
4. giữ HERA bind loopback;
5. chỉ public 443; 80 dành ACME/redirect; 22 giới hạn IP/VPN;
6. không public 5432, 6379, 8000, 19090, 13000.

Docker published port có thể đi qua rule riêng, nên kiểm cloud security group và
`DOCKER-USER`, không chỉ `ufw status`.

Public env:

```dotenv
PUBLIC_BASE_URL=https://hera.example.vn
CORS_ORIGINS=["https://hera.example.vn","https://www.benhvientimhanoi.vn"]
GRAFANA_ROOT_URL=https://grafana-internal.example.vn
GRAFANA_COOKIE_SECURE=true
```

Không dùng wildcard CORS. Nếu thay parent iframe, sửa CSP `frame-ancestors` và rebuild
frontend.

## 7. Monitoring

Start:

```bash
make monitoring-up
```

Mặc định:

- Prometheus: `127.0.0.1:19090`, retention 15 ngày;
- Grafana: `127.0.0.1:13000`;
- dashboard provision: `HERA Overview`;
- username: `hera_admin`;
- password: `GRAFANA_ADMIN_PASSWORD` trong secret manager/`.env`.

Theo dõi:

- `up` và `hera_readiness_status`;
- `hera_dependency_up` cho PostgreSQL/Redis;
- request rate, 5xx, in-progress, p95/p99;
- upstream failure/timeout;
- grounding/guardrail/emergency;
- release gates và schedule horizon;
- booking occupied/capacity/hold result;
- structured cache hit/miss/error.

`HERA Overview` theo dõi tốc độ dùng token theo provider/loại token. Dashboard thanh toán của FPT
là nguồn chính thức cho số tiền thực tế.

Alert rules có sẵn cho API down, readiness/dependency/release gate, schedule/capacity,
grounding/freshness/guardrail, upstream, 5xx và latency. Chưa có Alertmanager/notifier:
không tuyên bố có email/Slack/PagerDuty cho tới khi cấu hình và test delivery.

Nếu chưa biết Grafana:

1. Mở `http://127.0.0.1:13000`.
2. Đăng nhập user `hera_admin`.
3. Password lấy từ `GRAFANA_ADMIN_PASSWORD` trong `.env`.
4. Vào dashboard `HERA Overview`.
5. Nếu mọi panel chính xanh/không đỏ và `/readyz` pass, demo có thể chạy.

Không sửa dữ liệu trong Grafana. Grafana chỉ để nhìn metric. Muốn xem lỗi cụ thể, lấy
`request_id` trong response rồi tra log backend.

Langfuse:

- Mặc định tắt: `LANGFUSE_ENABLED=false`.
- Không cần Langfuse để chạy demo hoặc deploy.
- Chỉ bật khi muốn trace RAG/LLM và đã có project Langfuse riêng.
- Luôn giữ `LANGFUSE_CAPTURE_CONTENT=false` cho demo để không gửi prompt/answer raw ra
  ngoài.
- Nếu bật, điền `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, sau đó
  recreate backend.

## 8. Logging và request ID

Backend log JSON một dòng ra stdout. Nginx truyền `X-Request-ID`, backend trả request ID
trong response và log. Không log raw chat, API key, phone/email/BHYT ID, hold token hoặc
Authorization.

```bash
docker compose logs --no-log-prefix --since 10m backend
docker compose logs backend | grep '<request_id>'
```

Docker `json-file` rotation mặc định 10 MB x 5 file/container. Đây không phải audit
archive. Production có thể forward stdout sang Loki/SIEM đã được security/privacy duyệt.

## 9. Horizontal scale và load test

Authoritative state nằm ở PostgreSQL; cache/rate limit/context nằm ở Redis nên backend
có thể scale ngang. Nginx dùng Docker DNS để nhận replica mới. Trước khi tăng replica,
kiểm DB connection budget: default mỗi replica tối đa 5 connection.

Stress chuẩn:

```bash
make stress
```

Extreme:

```bash
make stress-extreme CONFIRM_EXTREME=YES
```

Profile extreme dùng project loopback `hera-stress`, key giả, 3 backend replica,
50.000 read + 10.000 booking request, concurrency 1.000. Nó kiểm ít nhất 3 replica xuất
hiện và `occupied <= capacity`, release các hold rồi dọn project/volume test.

Không chạy stress vào public production hoặc với API key thật.

## 10. CI/CD

`.github/workflows/ci.yml`:

1. backend static/test;
2. PostgreSQL rỗng migration;
3. seed hai lần để chứng minh idempotency;
4. frontend typecheck/test/build/audit;
5. gitleaks;
6. Compose config;
7. build image;
8. stress CI không gọi model;
9. Trivy critical scan;
10. push đúng image đã test lên GHCR bằng full commit SHA khi `main` pass.

`.github/workflows/deploy.yml` chỉ chạy thủ công, yêu cầu CI success đúng SHA trên
`main`, rồi SSH tới server và dùng `remote-deploy.sh` để pull image/digest, verify data,
migrate/seed/readiness/smoke. Live model probe chỉ chạy nếu workflow/operator truyền
`--model-preflight` rõ ràng.

GitHub Environment secrets:

| Secret | Nội dung |
|---|---|
| `DEPLOY_HOST` | server hostname/IP |
| `DEPLOY_PORT` | SSH port, thường 22 |
| `DEPLOY_USER` | user deploy riêng |
| `DEPLOY_PATH` | absolute repository path trên server |
| `DEPLOY_SSH_PRIVATE_KEY` | private key CI riêng |
| `DEPLOY_KNOWN_HOSTS` | host key đã xác minh ngoài kênh |

GHCR token là GitHub token ngắn hạn đi qua stdin vào temporary Docker config và bị xóa.
Không lưu PAT dài hạn trên server nếu không cần.

Server phải được provision repository/Compose tương thích trước. Khi migration, Compose
hoặc seed đổi, cập nhật release layout trước khi chỉ pull image mới.

## 11. Package release

```bash
bash scripts/package-release.sh
```

Package loại `.env`, credential-shaped files, `*.db`, dump, Git/cache/node_modules và
thêm:

- `release-metadata.json`;
- `release-manifest.sha256` cho mọi payload;
- `<release>.zip.sha256` ở ngoài ZIP.

Server kiểm checksum ngoài trước khi unzip, rồi manifest bên trong. Secret chỉ tạo trên
server.

## 12. Backup và restore

Backup:

```bash
BACKUP_DIR=/secure/backup/path make backup
```

Script tạo custom `pg_dump`, kiểm bằng `pg_restore --list`, permission 600 và SHA-256.
Mã hóa/đẩy backup sang storage riêng; không commit.

Restore:

```bash
make restore \
  RESTORE_FILE=/secure/backup/path/hera-postgresql-<timestamp>.dump \
  CONFIRM_RESTORE=YES
```

Restore tự tạo pre-restore backup, dừng app, clean restore, migrate, start và smoke. Nếu
lỗi, app giữ dừng để không phục vụ dữ liệu dở.

Chi tiết data reset/import rollback: [DATA_MANAGEMENT.md](DATA_MANAGEMENT.md).

## 13. Rotate/recover secret

### PostgreSQL

Đổi password role trong `psql` bằng `\password hera_owner`, sau đó cập nhật `.env` và
recreate backend/migrate/seed. Chỉ sửa `.env` không đổi role trong volume.

### FPT API key

Tạo key mới, cập nhật secret, recreate backend, chạy đúng một model gateway probe, sau đó
revoke key cũ. Không revoke key cũ trước khi key mới pass.

### Hold token secret

Dừng hold mới, đợi/release hold active, rotate secret, recreate backend. Token cũ sẽ mất
hiệu lực.

### Grafana

Khi còn login, đổi trong UI. Nếu mất:

```bash
read -rsp "New Grafana password: " NEW_GRAFANA_PASSWORD
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml \
  exec grafana grafana cli admin reset-admin-password "$NEW_GRAFANA_PASSWORD"
unset NEW_GRAFANA_PASSWORD
```

Cập nhật secret manager. Env password chỉ chủ yếu dùng lần init volume Grafana.

### SSH/TLS/Langfuse/GHCR

Tạo credential mới, update, kiểm staging, rồi revoke credential cũ. Ghi owner/time/test
evidence, tuyệt đối không ghi value.

## 14. Rollback

Image rollback:

```bash
make rollback CONFIRM_ROLLBACK=YES CONFIRM_SCHEMA_COMPATIBLE=YES
```

Script yêu cầu metadata current/previous, image trước còn local và tự backup PostgreSQL.
Chỉ rollback image khi schema backward-compatible. Nếu schema/bundle không tương thích,
restore backup cùng release trong maintenance window.

Không dùng `docker compose down -v` để rollback; lệnh đó xóa dữ liệu.

## 15. Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| `config --quiet` fail | Điền secret bắt buộc, sửa JSON env; không in expanded config |
| `migrate` Exit 1 | Xem migration log, giữ backend cũ/dừng traffic |
| `seed` Exit 1 | Kiểm checksum/version/revision/manifest; transaction đã rollback |
| backend unhealthy | Đọc `/readyz` issues/checks, kiểm DB/Redis/model config |
| `model_configuration=false` | Kiểm key, fixed model names, endpoint HTTPS, dimension |
| FPT timeout | Structured path vẫn dùng SQL; kiểm DNS/TLS/egress, không đổi model tùy tiện |
| Redis down | Khôi phục Redis; không tắt shared rate limit trên public |
| PostgreSQL down | Dừng traffic, kiểm disk/volume/log; không tạo DB mới đè volume |
| `CAPACITY_REACHED` | Gợi ý ca khác; không tăng threshold trực tiếp |
| lịch tuần sau gate đỏ | Publish bundle lịch mới theo data workflow |
| 5xx/p95/p99 cao | Dùng request ID, metrics dependency/upstream/cache/pool |
| alert đỏ không gửi email | Đúng hiện trạng: chưa có notifier |
| disk tăng | Kiểm log rotation, backup, Prometheus/Grafana/PostgreSQL volume |

## 16. Ranh giới production

Bản này deploy chắc chắn cho hackathon/staging nhưng chưa phải tích hợp HIS production:

- booking vẫn là local hold;
- capacity 20 là MVP rule, không phải quota bệnh viện phê duyệt;
- hotline có thể để trống tới khi owner xác minh;
- chưa có Alertmanager notifier;
- Langfuse mặc định tắt;
- chưa có OCR/voice;
- production cần DPO/legal/security, HA database/Redis, backup rehearsal, TLS/WAF và
  hospital API adapter.

Không đổi nhãn hoặc tắt validator để che các giới hạn này.
