# HERA Data Management

Tài liệu này trả lời bốn câu hỏi quan trọng:

1. dev clone GitHub nhận được dữ liệu gì;
2. database được tạo/migrate/seed thế nào;
3. cập nhật nguồn mới mà vẫn giữ checksum, approval và rollback ra sao;
4. backup/restore/reset môi trường nào là an toàn.

## 1. Mô hình dữ liệu cần nhớ

HERA có ba lớp, nhưng runtime chỉ đọc một lớp:

| Lớp | Vị trí | Mục đích | Runtime đọc trực tiếp? |
|---|---|---|---:|
| Official/runtime input | `data/BHYT.json`, bảng giá, schedules, `data/source/` | Nguồn nghiệp vụ để tạo release | Không |
| Synthetic test input | `data/test-fixtures/` | Paraphrase/scenario/golden case chỉ để test | Không |
| Generated/staging | `data/generated/` | Kết quả deterministic đã chuẩn hóa + manifest | Không |
| PostgreSQL seed release | `apps/backend/data/hera_postgres_seed.json.gz` | Artifact đã duyệt để dựng DB | Có, qua service `seed` |
| PostgreSQL volume | Docker host | DB đang chạy + dữ liệu phát sinh | Có |

Không có SQLite và không có OCR.

Runtime không mount `data/`. Việc tách source/staging khỏi runtime giúp server nhỏ,
deploy lặp lại được và không vô tình trả dữ liệu chưa duyệt.

Ba loại phải phân biệt:

- **official/runtime input:** có thể đi vào source/fact/structured seed sau approval;
- **deterministic normalized:** `data/generated` được tạo lại byte-for-byte từ input;
- **synthetic test-only:** giúp test cách hỏi, không được trở thành kiến thức runtime.

Inventory hiện tại là 55 JSON:

- 20 primary raw: 2 catalog + 18 schedule;
- 1 curated official-knowledge input;
- 10 curated synthetic test-fixture input;
- 24 generated output.

Nói cách khác: 31 input và 24 output. Không cộng test fixture vào số nguồn nghiệp vụ.

## 2. GitHub chứa gì và không chứa gì?

### Được commit

- migration Alembic;
- code repository/query/seed;
- `hera_postgres_seed.json.gz`;
- `hera_postgres_seed.json.gz.sha256`;
- Compose/Makefile/deploy/backup/restore;
- schema/test/docs không chứa secret.

Seed hiện tại có:

| Nhóm | Số lượng |
|---|---:|
| service catalog record | 2.946 |
| service price snapshot theo cơ sở | 4.051 |
| BHYT policy | 2 |
| BHYT tier | 10 |
| schedule document | 18 |
| schedule entry | 1.382 |
| doctor | 82 |
| booking session | 771 |
| knowledge chunk có vector | 11 |
| support channel | 2 |

Bundle version là `2.0.0`, migration revision là `0001_initial_schema`. Các con số này
là evidence của artifact hiện tại, không phải constant để hard-code vào business logic.
Seed release đã áp dụng bộ lọc nhãn không giống tên bác sĩ; kết quả hiện là 82 doctor demo
và 771 booking session.

### Không được commit

- `.env`, API key, password, TLS/SSH/private key;
- Docker container/image/volume của laptop/server;
- PostgreSQL dump/backup;
- log, trace export, feedback thật, hội thoại, booking state thật;
- raw patient data, số điện thoại, email, BHYT ID, bệnh án;
- file cache, node_modules, virtualenv, test artifact.

Git không thể mang theo `hera_postgres_data`. Dev clone repo nhận seed chuẩn, sau đó tạo
volume mới. Muốn chuyển state phát sinh giữa hai server phải backup/restore PostgreSQL.

## 3. Dựng DB + migration + seed bằng một lệnh

Từ repository, sau khi có `.env` hợp lệ, lệnh dành riêng cho database là:

```bash
make db-bootstrap
```

Lệnh validate data, build backend, start DB, migrate và seed nhưng chưa cần start toàn bộ
frontend. Muốn start cả ứng dụng dùng `make up` hoặc `docker compose up -d --build --wait`.

Luồng thực tế:

```text
db healthy
  -> migrate: alembic upgrade head
  -> seed: checksum + schema contract + idempotent upsert
  -> backend readiness
  -> frontend healthy
```

Kiểm:

```bash
docker compose ps --all
curl -fsS http://127.0.0.1:8080/readyz
```

`migrate` và `seed` là one-shot service nên trạng thái đúng là `Exited (0)`.

Chạy riêng:

```bash
make migrate
make seed
make smoke
```

## 4. Seed archive được bảo vệ thế nào?

`seed_postgres.py` kiểm trước khi ghi:

1. file gzip tồn tại và là JSON đúng;
2. SHA-256 file khớp sidecar;
3. format đúng `hera-postgres-seed-v1`;
4. bundle version tồn tại và đúng version release mong đợi;
5. Alembic revision trong archive khớp application;
6. danh sách table đúng allowlist, không thiếu/không trùng;
7. primary key và column payload đúng contract;
8. row count trong archive khớp metadata;
9. manifest hash trong archive khớp `bundle_meta.integrity_json`;
10. vector chỉ dùng `Vietnamese_Embedding` và 1024 chiều.

Khi ghi DB, script:

- mở transaction;
- lấy PostgreSQL advisory transaction lock để hai seeder không chạy đè nhau;
- xác nhận DB đã ở đúng Alembic revision;
- dùng `INSERT ... ON CONFLICT ... DO UPDATE` theo primary key;
- kiểm row count sau seed;
- ghi archive SHA, manifest SHA, revision và timestamp vào `bundle_meta`;
- rollback toàn transaction nếu bất kỳ bước nào lỗi.

Chạy lại cùng archive là idempotent: không nhân bản row. Nếu DB đã có bundle/manifest
khác, script dừng thay vì tự ghi đè.

Verify offline, không gọi model:

```bash
.venv/bin/python apps/backend/scripts/verify_release_assets.py \
  --seed-archive apps/backend/data/hera_postgres_seed.json.gz \
  --expected-bundle-version 2.0.0
```

## 5. Raw source hiện có dùng thế nào?

Tên file có thể giữ metadata nguồn cũ, nhưng UI coi giá/BHYT là dữ liệu hiện hành của
demo và không hiển thị năm. Lịch luôn dựa vào ngày thật trong record.

| Source | Vai trò |
|---|---|
| `data/gia_dich_vu_ky_thuat_2025.json` | Bảng giá theo dịch vụ và CS1/CS2; normalize thành catalog + price point |
| `data/BHYT.json` | Quy tắc/tier BHYT hộ gia đình; không suy luận quyền lợi cá nhân |
| `data/source/official-knowledge.json` | Nguồn/fact/template/channel curated để clean clone tự generate |
| `data/schedules/<năm>/<week>/Lịch khám bệnh Bác sĩ khu TN1 Cơ Sở 1.json` | Lịch CS1 khu TN1 |
| `data/schedules/<năm>/<week>/Lịch khám bệnh Bác sĩ khu TN Cơ Sở 2.json` | Lịch CS2 khu TN |
| `data/schedules/<năm>/<week>/Lịch khám bệnh Bác sĩ Đa Khoa Cơ Sở 2.json` | Lịch CS2 đa khoa |
| `data/test-fixtures/13...22.json` | Synthetic paraphrase/scenario/evaluation input; test-only |

Mỗi tuần hiện có đúng ba tài liệu theo ba nguồn trên. Folder tuần dùng dạng
`YYYY-MM-DD_to_YYYY-MM-DD`. Generator phát hiện các tuần, chuẩn hóa ngày/cơ sở/phòng/
bác sĩ và tạo registry + entry. Không suy diễn appointment slot từ roster.

Ngày lịch sớm nhất là mốc “hôm nay” của demo; nhiều tuần tiếp theo chứng minh khả năng
tra ngày sau/tuần sau.

## 6. Từng file generated dùng để làm gì?

`data/generated` không được runtime đọc. Đây là output staging/evidence dùng trước khi
đóng seed archive.

| File/nhóm | Nội dung | Có đi vào runtime seed? |
|---|---|---:|
| `00-manifest.json` | Exact file set, byte count, SHA-256, raw input hash, counts, load order | Metadata/integrity |
| `01-sources-facts-and-templates.json` | Nguồn, fact, fixed response, support channel | Có |
| `02-...` đến `07-...service-prices...json` | Giá chia batch để review/import | Có |
| `08-bhyt-household-contributions.json` | Policy + contribution tiers | Có |
| `09-schedule-document-registry.json` | Một record cho mỗi tài liệu lịch | Có |
| `10-schedule-entries.json` | Entry lịch đã normalize | Có |
| `11-booking-capacity-config.json` | Rule capacity MVP có provenance rõ | Có |
| `12-import-issues.json` | Danh sách điểm cần người duyệt xem lại | Không; review-only |
| `13-...` đến `15-...faq-paraphrases...json` | Câu hỏi diễn đạt lại để test retrieval | Không; test-only |
| `16-...` đến `17-...conversation-scenarios...json` | Kịch bản multi-turn | Không; test-only |
| `18-...` đến `22-...evaluation-cases...json` | Golden/evaluation cases | Không; test-only |
| `23-validation-report.json` | Kết quả validation và manifest SHA | Evidence |

Không xóa/chỉnh riêng một shard rồi tiếp tục dùng manifest cũ. Validator yêu cầu exact
file set, byte count và hash.

## 7. Cập nhật hoặc bổ sung dữ liệu nguồn

Với các loại dữ liệu dự án đã hỗ trợ, gồm bảng giá dịch vụ kỹ thuật, BHYT hộ gia
đình, lịch bác sĩ và cấu hình capacity, dev không sửa backend theo từng dòng dữ
liệu. Backend chỉ đọc PostgreSQL canonical. Khi dữ liệu nguồn thay đổi, luồng
đúng là cập nhật raw/source, build lại `data/generated`, đóng lại seed
PostgreSQL rồi chạy validation.

Nói ngắn gọn: thêm một dòng giá hoặc thêm một tuần lịch không được kéo theo sửa
code. Nếu sau khi thêm dữ liệu mà phải sửa code theo tên dịch vụ cụ thể, đó là
lỗi ở pipeline chuẩn hóa/ranking và phải bổ sung test regression trước khi merge.

### 7.1. Quy trình bắt buộc

1. Tạo branch/change request và ghi nguồn, owner, thời điểm nhận, phạm vi.
2. Giữ bản raw bất biến; không sửa trực tiếp file raw cũ để che thay đổi.
3. Với lịch mới, tạo đúng folder tuần và đủ ba file theo convention.
4. Tạo lại output deterministic từ repository root:

   ```bash
   make data-generate
   ```

   Có thể xóa toàn bộ `data/generated` trước khi chạy; generator chỉ đọc
   `data/source`, raw giá/BHYT/schedules và `data/test-fixtures`, không đọc output cũ.
5. Kiểm `00-manifest.json`, `12-import-issues.json` và
   `23-validation-report.json`. Mọi tài liệu lịch release phải accepted, không còn
   record bắt buộc review.
6. Data owner duyệt thay đổi giá/BHYT/lịch/capacity; lưu evidence không nhạy cảm.
7. Reconcile dữ liệu runtime vào PostgreSQL canonical bằng migration/ETL được review.
   Không sửa production row tùy tiện.
8. Export deterministic từ canonical PostgreSQL:

   ```bash
   make data-export CONFIRM_DATA_EXPORT=YES
   ```

   Nếu generated manifest mới đã được data owner duyệt và canonical PG đã reconcile,
   expert mới được dùng:

   ```bash
   make data-rebind-export \
     CONFIRM_DATA_EXPORT=YES \
     CONFIRM_DATA_REBIND=YES
   ```

9. `make data-validate` phải chứng minh raw/generated/seed hash và count khớp.
10. Migrate + seed vào PostgreSQL staging rỗng, chạy `/readyz`, smoke, evaluation và
    stress booking.
11. Backup môi trường đích, deploy release có checksum, theo dõi gate/metric.

### 7.2. Tooling và giới hạn

Repository hiện có:

- `make data-generate`: source/test fixture -> generated;
- `make generated-validate`: raw hash + generated exact-set, chưa so seed;
- `make data-validate`: generated manifest + seed/checksum;
- `make data-import`: migration + seed đã commit -> PostgreSQL;
- `make data-export`: canonical PostgreSQL -> deterministic seed;
- `make data-rebind-export`: expert-only bind reviewed PG rows với manifest mới;
- `make data-reset-dev`: backup rồi reset project dev/demo/test riêng.

Importer hiện tại xử lý các lane đã được định nghĩa trong manifest: giá kỹ thuật,
BHYT hộ gia đình, lịch bác sĩ, capacity, source/fact/template. Chỉ khi thêm một
loại dữ liệu hoàn toàn mới, ví dụ danh mục khoa chính thức hoặc quyền lợi BHYT cá
nhân, mới cần migration/ETL có review, stable ID và test trước khi export.
Exporter cố ý không export conversation/feedback/hold/audit runtime.

### 7.3. Không sửa code theo từng dòng dữ liệu

Những phần sau phải sinh từ data hoặc chạy bằng truy vấn tổng quát:

- tên dịch vụ, tên bác sĩ, cơ sở, phòng khám, ngày khám;
- `display_name_search`, `retrieval_text`, source/citation và checksum;
- ID bản ghi, ID giá theo cơ sở, booking session/capacity;
- kết quả ranking dựa trên exact match, token coverage, BM25/trigram và reranker.

Những phần được phép cố định trong code chỉ là contract chung: tên bảng, schema,
ngưỡng an toàn, cache namespace, timeout và allowlist lane dữ liệu. Không được
thêm điều kiện kiểu “nếu dịch vụ A thì trả dòng B”.

## 8. Validation và staging gates

Một bundle chỉ được promote khi:

- raw path an toàn, file tồn tại, byte count/hash khớp;
- generated exact-set/hash pass;
- không có schedule document bắt buộc review;
- mọi service price có amount hợp lệ và facility rõ;
- BHYT tiers có thứ tự/rate/amount nhất quán;
- schedule date nằm đúng week folder và facility/source;
- doctor alias không gây mapping mơ hồ;
- capacity rule có source/prototype flag rõ;
- vector model/dimension khớp;
- PostgreSQL row count khớp manifest;
- `/readyz` trả HTTP 200, mọi check true;
- booking stress không vượt capacity;
- smoke không gọi model vẫn pass structured/emergency/booking.

Staging phải dùng database/volume riêng, không trỏ vào production. Không dùng
`ALLOW_REVIEW_ONLY_DATA=true` để vượt gate.

### Đánh giá release hiện tại

Integrity/reproducibility đã pass, nhưng domain completeness chưa đủ production:

- chỉ 11 official facts; còn thiếu quy trình khám/nhập viện/tái khám, giờ làm việc đầy
  đủ, khoa/chuyên khoa/danh bạ bác sĩ, hướng dẫn BHYT tổng quát và dịch vụ bệnh viện;
- seed hiện tại có 771 booking session dùng rule prototype capacity 20 sau khi loại nhãn
  không giống bác sĩ. Đây vẫn chưa phải quota bệnh viện;
- 226/1.008 named schedule assignment chưa map doctor canonical;
- 104 schedule row là review-only, không được dùng để trả runtime;
- 56 trường hợp tên/cơ sở giá cần disambiguation;
- chưa có hospital booking/capacity API.

Ưu tiên xin dữ liệu:

1. quy trình khám/nhập viện/tái khám + giờ làm việc;
2. danh bạ khoa/chuyên khoa/bác sĩ và alias;
3. lịch/capacity/booking API được duyệt;
4. hướng dẫn BHYT authoritative;
5. danh mục dịch vụ và support channel đã xác minh.

### Minimal real-data acquisition pack (P0)

Không cần một “training dataset” lớn. HERA cần một gói dữ liệu nhỏ, có cấu trúc, cập nhật
được và có người phê duyệt. Synthetic fixture vẫn chỉ dùng test.

| File đề nghị | Field tối thiểu | Mục đích |
|---|---|---|
| `doctor-master.json` | `doctor_id`, `display_name`, `aliases[]`, `title`, `department_id`, `facility_codes[]`, `active`, `effective_from/to`, `source_id`, `approved_by/at` | Map lịch/booking đúng bác sĩ |
| `booking-availability.json` hoặc API | `upstream_session_id`, `doctor_id`, `service_date`, `session_key`, `start/end`, `facility`, `room`, `capacity`, `booked/remaining`, `status`, `updated_at` | Thay capacity 20 prototype |
| `departments-facilities-hours.json` | department/facility ID, tên/alias, địa chỉ, ngày làm việc, open/close/break, holiday exception, effective dates, source/approval | Giờ làm việc, khoa/cơ sở |
| `procedures.json` | `procedure_id`, type (khám/nhập viện/tái khám), title, ordered steps, required documents, location, exceptions, source/effective/approval | Trả quy trình đúng |
| `emergency-guidance.json` | symptom trigger đã duyệt, exact instruction, emergency location/hotline, prohibited advice, source/effective/approval | Emergency deterministic |
| `bhyt-official.json` | `policy_id`, scope, legal source, valid dates, base amount, tier order/rate/monthly/annual, conditions, source URL/hash, approval | Loại bỏ BHYT curated runtime input |
| `hospital-services.json` | service/department IDs, display name/alias, facility, description, referral/contact, source/approval | Dịch vụ chuyên môn |
| `support-channels.json` | channel ID/type/label/target, purpose, hours, source, active, approval | Handoff chính xác |

Không đưa tên/số điện thoại/bệnh án bệnh nhân vào pack. Booking availability chỉ cần số
đếm aggregate/session ID.

Lưu ý: các tier BHYT hiện hành trong release đang được curated trong generator. Muốn bỏ
phần generated runtime input này phải nhận `bhyt-official.json` từ nguồn chính thức, có
hash, hiệu lực và approval; không dùng synthetic paraphrase làm bằng chứng.

## 9. Upsert, thay bundle và import lỗi

### Cùng bundle/manifest

`make seed` có thể chạy lại an toàn. Primary key conflict cập nhật column mutable và row
count phải khớp. Runtime table như conversation/feedback/hold không bị seed lại.

### Khác bundle/manifest

Seeder mặc định dừng. Đây là hành vi đúng. Cách an toàn nhất là:

1. backup;
2. thử release trên DB staging rỗng;
3. maintenance window;
4. dùng migration + quy trình data promotion được duyệt;
5. readiness/smoke rồi mở traffic.

`--replace-reference-data` là tùy chọn phá hủy: implementation truncate cả reference và
runtime tables trước khi nạp lại. Chỉ dùng trên DB test/demo dùng một lần, hoặc khi đã có
backup và phê duyệt maintenance rõ ràng. Không có Make target tự động cho hành vi này.

### Khi import thất bại

- Không sửa DB dở dang: transaction seeder đã rollback.
- Giữ backend cũ/traffic ở release cũ.
- Lưu error type, bundle SHA, revision và thời điểm; không lưu secret/raw patient data.
- So sánh archive checksum, manifest, migration revision và table contract.
- Sửa từ raw/staging, regenerate toàn bundle; không patch row trực tiếp.
- Nếu replace/restore đã bắt đầu và lỗi, giữ frontend/backend dừng theo runbook, dùng
  pre-operation backup để phục hồi.
- Chỉ promote lại sau toàn bộ gates pass.

## 10. Backup PostgreSQL

Trên Ubuntu/WSL:

```bash
make backup
```

Hoặc:

```bash
BACKUP_DIR="$HOME/hera-backups" bash scripts/backup.sh
```

Script:

- tạo custom-format `pg_dump`;
- kiểm dump bằng `pg_restore --list`;
- ghi SHA-256 sidecar;
- permission directory 700, file 600;
- không in DB password.

Backup chứa dữ liệu phát sinh và có thể nhạy cảm. Mã hóa, lưu ngoài repo/server nếu có
thể, đặt retention và test restore định kỳ. Không raw-copy thư mục volume PostgreSQL đang
chạy.

## 11. Restore

Restore là destructive và script bắt buộc confirmation:

```bash
make restore \
  RESTORE_FILE=/secure/path/hera-postgresql-<timestamp>.dump \
  CONFIRM_RESTORE=YES
```

Script kiểm sidecar checksum + cấu trúc dump, tự tạo pre-restore backup, dừng
frontend/backend, restore clean, migrate, start, smoke. Nếu lỗi giữa chừng, app giữ dừng
để không phục vụ dữ liệu nửa vời và in đường dẫn recovery backup.

Không restore thẳng production chỉ để “test backup”. Dùng server/project/database tách
biệt rồi đối chiếu readiness, counts và smoke.

## 12. Reset môi trường test/demo

### Reset project disposable bằng guard script

Chỉ dùng dedicated project có prefix `hera-dev`, `hera-demo` hoặc `hera-test`:

```bash
make data-reset-dev \
  CONFIRM_DATA_RESET=YES \
  DEV_PROJECT_NAME=hera-dev
```

Script từ chối project `hera`, từ chối `ENVIRONMENT=production`, kiểm mọi volume có đúng
project prefix, tự backup nếu DB đã tồn tại, rồi mới `down -v`, migrate và seed lại.
Stress dùng project `hera-stress` riêng và tự cleanup.

### Reset production

Không có khái niệm “reset production”. Dùng backup/restore hoặc release migration có
change record. `docker compose down -v` trên production là xóa dữ liệu.

## 13. Rollback dữ liệu/release

Rollback image chỉ an toàn khi schema backward-compatible. `scripts/rollback.sh` yêu cầu:

- `CONFIRM_ROLLBACK=YES`;
- `CONFIRM_SCHEMA_COMPATIBLE=YES`;
- metadata release hiện tại/trước;
- image trước còn có local;
- pre-rollback PostgreSQL backup.

```bash
make rollback CONFIRM_ROLLBACK=YES CONFIRM_SCHEMA_COMPATIBLE=YES
```

Nếu bundle/schema không tương thích, restore backup cùng release trong maintenance window,
không chỉ đổi image.

## 14. Dữ liệu nhạy cảm tuyệt đối không commit

Trước commit, hỏi: “file này có cho phép nhận diện bệnh nhân, credential hoặc state vận
hành không?”. Nếu có hoặc không chắc, không commit.

Danh sách cấm:

- tên/số điện thoại/email/địa chỉ người bệnh;
- CCCD, mã BHYT, hồ sơ/bệnh án, triệu chứng gắn danh tính;
- raw chat/feedback thật;
- booking token, Authorization header, session ID thật;
- API key, password, private key, cookie;
- PostgreSQL dump/volume export;
- production log/trace/metric export có identifier.

Kiểm:

```bash
git status --short
git diff --cached --stat
git diff --cached
git check-ignore .env
```

CI có gitleaks nhưng không thay thế review. Nếu secret từng được commit, xóa file ở commit
mới là chưa đủ: revoke/rotate secret ngay và làm sạch history theo quy trình security.
