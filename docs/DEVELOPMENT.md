# HERA Developer Guide

Tài liệu này dành cho người sửa code. Người mới chỉ cần chạy hệ thống theo
[README](../README.md). Cấu hình từng biến ở [CONFIGURATION.md](CONFIGURATION.md),
quản trị dữ liệu ở [DATA_MANAGEMENT.md](DATA_MANAGEMENT.md), còn server/monitoring/
backup ở [DEPLOYMENT.md](DEPLOYMENT.md).

## 1. Nguồn sự thật và phạm vi

Đọc theo thứ tự:

1. `PROBLEM.md` ở workspace cha: yêu cầu hackathon;
2. `TECHNICAL.md` ở workspace cha: contract nghiệp vụ, dữ liệu, API, safety, deploy;
3. migration `apps/backend/alembic/versions/0001_initial_schema.py`: schema thật;
4. `apps/backend/app/core/config.py`: type/default/validator thật;
5. `docker-compose.yml`: cấu hình container thật;
6. `.env.example`: profile deploy được hỗ trợ;
7. test backend/frontend: hành vi có thể kiểm chứng.

Nếu docs và code lệch nhau, không âm thầm chọn một bên. Sửa contract, code, test,
Compose và migration trong cùng change khi chúng liên quan.

Giới hạn cố định:

- PostgreSQL + pgvector là database duy nhất;
- Redis là shared cache/rate-limit/ephemeral memory;
- LLM generation `gpt-oss-120b`, guard/routing `gpt-oss-20b`, embedding `Vietnamese_Embedding` 1024 chiều, rerank `bge-reranker-v2-m3`;
- không OCR, không ASR/TTS;
- booking chỉ là hold prototype, không phải HIS confirmation;
- không chẩn đoán hoặc tư vấn điều trị;
- structured data không được đưa qua LLM khi SQL đã trả lời chính xác.

## 2. Repository layout

```text
HERA-Hanoi-Heart-Engagement-Response-Assistant/
├── apps/backend/
│   ├── alembic/                 # PostgreSQL migration
│   ├── app/                     # FastAPI, AI, structured, booking, persistence
│   ├── data/
│   │   ├── hera_postgres_seed.json.gz
│   │   └── hera_postgres_seed.json.gz.sha256
│   ├── scripts/                 # seed, verify, smoke, model probe
│   └── tests/
├── apps/frontend/               # React/Vite + Nginx
├── docs/
├── infra/                       # Prometheus, Grafana, edge Nginx
├── scripts/                     # deploy, package, backup, restore, stress
├── docker-compose.yml
├── docker-compose.monitoring.yml
├── docker-compose.stress.yml
└── Makefile
```

Repository tự đủ để deploy vì source/generated và seed archive đều đã commit. Thư mục
`data/` là source/provenance để tạo release, nhưng không được runtime mount.

## 3. Setup developer không gọi API

Ubuntu/WSL:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install \
  -r apps/backend/requirements.txt \
  -r requirements-dev.txt
npm --prefix apps/frontend ci
```

Unit test và lint không cần key thật:

```bash
.venv/bin/python -m ruff check \
  apps/backend/app apps/backend/tests apps/backend/scripts scripts
.venv/bin/python -m pytest \
  apps/backend/tests --ignore=apps/backend/tests/integration
npm --prefix apps/frontend run typecheck
npm --prefix apps/frontend test
npm --prefix apps/frontend run build
```

`make lint`, `make unit` và `make test-full` là các shortcut tương ứng. Không đặt `API_KEY`
thật trong test fixture, CI variable hoặc file snapshot.

Chỉ `apps/backend/scripts/verify_model_gateway.py` gọi gateway thật. Không chạy nó trong
vòng lặp dev.

## 4. Dựng database, migrate và seed bằng một lệnh

Sau khi có `.env`:

```bash
docker compose up -d --build --wait
```

Lệnh này:

1. tạo PostgreSQL/pgvector và Redis;
2. chạy `alembic upgrade head` qua service `migrate`;
3. verify checksum + upsert seed archive qua service `seed`;
4. chỉ start backend khi DB healthy, migration và seed thành công;
5. chỉ start frontend khi backend vượt readiness.

Kiểm:

```bash
docker compose ps --all
curl -fsS http://127.0.0.1:8080/readyz
```

Chạy riêng:

```bash
make migrate
make seed
make smoke
```

Seed là idempotent: chạy lại cùng bundle không nhân bản record. Nó dùng advisory lock,
transaction, primary key upsert, checksum và row-count verification. Seed khác manifest
hoặc migration revision bị từ chối.

## 5. Chạy local giống server

Đường đầy đủ nhưng không tiêu model:

```bash
bash scripts/deploy.sh --monitoring
```

Sau khi chỉ sửa backend:

```bash
docker compose build backend
docker compose up -d --force-recreate backend
curl -fsS http://127.0.0.1:8080/readyz
```

Sau khi sửa frontend hoặc `VITE_*`:

```bash
docker compose build frontend
docker compose up -d --force-recreate frontend
```

Không dùng `docker compose down -v` trong vòng lặp thường: `-v` xóa volume PostgreSQL
và volume monitoring. `docker compose down` không có `-v` là an toàn cho state.

## 6. Kiến trúc code cần giữ

### Structured path

Giá/BHYT/lịch/booking đi theo:

```text
router -> service -> PostgreSQL repository -> response có classification/citation
                     ^
                     └── Redis cache cho kết quả structured đã duyệt
```

Route structured là sync function của FastAPI nên DB/Redis sync chạy trong threadpool.
Trong chat orchestrator, structured call chặn được đẩy qua worker thread. Không thực hiện
sync I/O trực tiếp trên event loop.

### RAG path

FAQ/thông tin chung:

```text
gpt-oss-20b guard/routing -> input guardrail if non-emergency
-> embedding -> pgvector retrieval -> RRF -> bge-reranker-v2-m3
-> evidence validator -> gpt-oss-120b -> output guardrail -> citation/handoff
```

Giá dịch vụ, BHYT hộ gia đình và lịch bác sĩ không đi qua RAG text path ở trên.
`gpt-oss-20b` chỉ route intent và trích slot; phần trả lời lấy từ PostgreSQL. Riêng
bảng giá dùng candidate widening theo token đã normalize, BM25-style scoring trên
tập candidate nhỏ, phrase/bigram continuity và trigram similarity. Cách này tránh
hardcode danh sách chuyên khoa/dịch vụ nhưng vẫn không để model tự bịa số tiền.

Không gọi LLM nếu exact structured/template path đã đủ. Không trả factual answer khi
evidence validator không chấp nhận nguồn.

### Shared state

- PostgreSQL: reference data, vector, booking holds, conversation có consent, feedback,
  citations và audit metadata.
- Redis: structured cache, rate limit, context ngắn hạn giữa replica.
- process memory: chỉ singleton/client/pool không authoritative.

Mọi hành vi phải đúng khi có nhiều backend replica. Không thêm counter booking hoặc
idempotency map chỉ trong process memory.

## 7. Quy tắc thay đổi cấu hình

Biến backend mới cần đủ:

1. field/validator trong `Settings`;
2. sample an toàn trong `.env.example`;
3. mapping Compose;
4. unit test default/override/invalid;
5. docs và readiness nếu biến là release gate.

Biến frontend mới cần Docker build arg + Compose build arg + type/use code + rebuild.
Không truyền secret qua `ARG`/`VITE_*` vì nó sẽ xuất hiện trong image/browser.

Timeout phải giữ quan hệ:

```text
embedding 10s <= LLM 30s < chat overall 35s < Nginx 40s
```

Không tăng riêng một lớp mà không kiểm lớp ngoài, retry và ngân sách connection.

## 8. Database và migration

Schema authoritative là Alembic; không tạo bảng bằng tay trên server. Khi đổi schema:

1. viết migration forward;
2. kiểm trên database rỗng;
3. kiểm trên backup/copy của revision trước;
4. đánh giá backward compatibility với image cũ;
5. cập nhật seed contract nếu table/column seed thay đổi;
6. backup trước deploy;
7. chạy readiness + smoke + booking invariant.

Local direct migration:

```bash
cd apps/backend
DATABASE_URL='postgresql+psycopg://...' alembic upgrade head
DATABASE_URL='postgresql+psycopg://...' \
  python scripts/seed_postgres.py \
  --seed-archive data/hera_postgres_seed.json.gz \
  --expected-bundle-version 2.0.0
```

Không trỏ lệnh test/seed vào database đang phục vụ người dùng.

## 9. Integration test PostgreSQL

Integration test chỉ chạy khi có database test riêng. Thiết lập
`HERA_TEST_DATABASE_URL` và `DATABASE_URL` cùng trỏ DB test đã migrate/seed:

```bash
export HERA_TEST_DATABASE_URL='postgresql+psycopg://hera_test:<password>@127.0.0.1:55432/hera_test'
export DATABASE_URL="$HERA_TEST_DATABASE_URL"
cd apps/backend
alembic upgrade head
python scripts/seed_postgres.py --expected-bundle-version 2.0.0
cd ../..
.venv/bin/python -m pytest apps/backend/tests/integration
```

Test phải chứng minh:

- readiness đủ gate PostgreSQL/Redis/data/model config;
- query giá, BHYT, lịch và pgvector;
- seed idempotent;
- booking đồng thời không vượt threshold;
- hold token/idempotency/quota;
- không có đường fallback SQLite.

CI đã tạo PostgreSQL `pgvector:pg16` riêng, migrate, seed hai lần và chạy toàn bộ test.

## 10. Data workflow

Không sửa gzip, manifest, vector hay row trong DB để “làm test pass”. Dev update dữ liệu
phải đi theo raw -> normalize/staging -> validation/approval -> seed archive -> checksum
-> migration/seed -> readiness. Quy trình đầy đủ và giới hạn tooling hiện tại:
[DATA_MANAGEMENT.md](DATA_MANAGEMENT.md).

Repo có generator, validator, seeder và deterministic PostgreSQL exporter. Tuy nhiên,
reference data mới vẫn phải được reconcile vào canonical PostgreSQL bằng migration/ETL
được review trước `make data-export`; không có generic importer được phép tự đoán mapping.

## 11. API contract

Endpoint public dưới `/api/v1`:

- `POST /chat`
- `POST /feedback`
- `GET /service-prices`
- `GET /bhyt/household-contributions`
- `GET /schedules`
- `GET /runtime-clock`
- `GET /booking-sessions`
- `POST /booking-holds`
- `POST /booking-holds/{hold_id}/confirm`
- `DELETE /booking-holds/{hold_id}`
- `GET /health`, `/health/ready`, `/health/db`

Ngoài version prefix có `/healthz`, `/readyz` và `/metrics` nội bộ. Thay response phải
đồng bộ Pydantic schema, frontend types/component, smoke và test.

Chat response phải giữ: `request_id`, `conversation_id`, `answer_vi`,
`response_type`, `intent`, `grounded`, `data_classification`, `citations`, `warnings`,
`actions` và emergency/handoff flags.

## 12. Privacy, security và logging

- Không log raw message, API key, Authorization header, hold token, phone/email/BHYT.
- Redact trước persistence; chỉ lưu nội dung khi `consent_to_store=true`.
- Không dùng user/query/doctor name làm Prometheus label.
- Request ID phải đi qua Nginx -> FastAPI -> response/log/trace metadata.
- Backend không publish port; chỉ tin proxy header từ CIDR được cấu hình.
- Không tắt grounding, readiness, rate limit hoặc capacity gate để demo “mượt”.
- Emergency gate chạy trước model và không đưa lời khuyên điều trị.

Langfuse mặc định tắt. Nếu bật, giữ `LANGFUSE_CAPTURE_CONTENT=false`.

## 13. CI/CD contract

CI:

1. Python compile/Ruff/Pytest;
2. seed checksum, migration DB rỗng, seed hai lần;
3. frontend typecheck/test/build/audit;
4. secret scan;
5. Compose validation;
6. build image, stress CI không gọi model;
7. Trivy critical scan;
8. push đúng image đã test lên GHCR bằng full commit SHA.

Deploy workflow chỉ nhận SHA trên `main` đã có CI success, pull image, kiểm digest/data,
migrate/seed/readiness/smoke rồi mới ghi release metadata. Live probe chỉ chạy khi
operator yêu cầu explicit.

Checklist PR:

1. không secret, `.env`, dump, log hoặc cache;
2. test không gọi live API;
3. migration/seed backward compatibility được đánh giá;
4. data/checksum gate pass;
5. docs/config/Compose khớp;
6. frontend contract khớp backend;
7. không thêm state local phá horizontal scale.

## 14. Performance và stress

Structured lookup ưu tiên SQL index + Redis cache; RAG chỉ chạy khi cần. Không tối ưu
bằng cách bỏ citation/safety. Dùng metric và query plan để chứng minh bottleneck.

```bash
make stress
make stress-extreme CONFIRM_EXTREME=YES
```

Stress dùng project `hera-stress` và key giả, không gọi model. Profile extreme chạy
50.000 read, 10.000 booking request, concurrency 1.000 trên ba backend replica; kiểm
replica header và invariant `occupied <= capacity`, sau đó release hold/dọn test project.
