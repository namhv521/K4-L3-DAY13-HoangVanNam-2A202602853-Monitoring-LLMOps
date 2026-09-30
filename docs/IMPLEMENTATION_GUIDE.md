# Hướng dẫn hoàn thành Day 13 Monitoring & LLMOps

Tài liệu này áp dụng cho trạng thái hiện tại của repository. Mục tiêu cuối là chứng minh được chuỗi:

```text
Metrics -> Logs -> Traces -> Root cause
```

## 1. Trạng thái hiện tại

Kết quả kiểm tra local ngày 30/09/2026:

| Hạng mục | Trạng thái |
|---|---|
| Public tests | `22 passed` |
| Log validator trên `data/logs.jsonl` hiện có | `100/100`, 135 records, 60 correlation IDs, 0 PII leak |
| Dashboard contract | `6/6 panel` hợp lệ |
| Correlation ID, log enrichment và PII scrub | Đã có trong source |
| Retrieval/generation child observations | Đã được thêm trong working tree, cần xác minh trên Langfuse thật |
| SLO, ba alert và runbook | Đã điền, cần đối chiếu với evidence cuối |
| Dashboard HTML local | Đã có script nhưng chưa được Git theo dõi và còn hai điểm cần sửa trước khi nộp |
| Langfuse traces, prompt v1/v2 và rollback | Chưa có bằng chứng xác minh trong repo |
| `submission/evidence/` | Chưa có evidence runtime |
| `submission/REPORT.md` | Mới điền baseline, các phần kết quả cuối còn trống |
| Challenge chính thức | Chỉ làm sau khi Lab Coach cấp `config/challenge.json` |

Không xóa hoặc ghi đè các thay đổi đang làm dở. Trước mỗi checkpoint, chạy `git status --short` để biết chính xác file nào thuộc phần việc của mình.

## 2. Luồng hệ thống cần hiểu

```text
POST /chat
  -> CorrelationIdMiddleware
     -> clear context cũ
     -> nhận hoặc sinh req-<8-hex>
  -> app.main.chat
     -> bind user/session/feature/model/env
     -> log request_received
  -> LabAgent.run
     -> retrieval span
     -> lấy prompt theo name/label
     -> generation span + token/cost
     -> cập nhật in-memory metrics
  -> log response_sent hoặc request_failed
  -> trả x-request-id cho client
```

Hai nguồn quan sát khác nhau:

- `data/logs.jsonl`: structured logs và nguồn của dashboard.
- Langfuse: trace tree, observations và prompt versions.

`correlation_id` là khóa nối hai nguồn này.

## 3. Chuẩn bị và chạy ứng dụng

Chạy từ thư mục gốc repository bằng PowerShell.

```powershell
$env:PYTHONUTF8='1'
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Nếu chưa có `.env`:

```powershell
Copy-Item .env.example .env
```

Điền key của project Langfuse cá nhân vào `.env`; không chụp, commit hoặc chia sẻ key. Project phải có tên `day13-k4-l3b-<MSSV>`.

Terminal 1:

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --env-file .env
```

Terminal 2:

```powershell
$env:PYTHONUTF8='1'
Invoke-RestMethod http://127.0.0.1:8000/health
.\.venv\Scripts\python.exe scripts/load_test.py --concurrency 5
Invoke-RestMethod http://127.0.0.1:8000/metrics
```

`/health` phải trả `ok: true`. Khi đã cấu hình đủ hai Langfuse key, `tracing_enabled` phải là `true`.

## 4. CP1 - Logging và PII

Các file chính:

- `app/middleware.py`: tạo và truyền correlation ID.
- `app/main.py`: bind metadata trước `request_received`.
- `app/logging_config.py`: scrub trước khi ghi JSONL.
- `app/pii.py`: pattern email, điện thoại Việt Nam, CCCD và thẻ.

Trước khi tạo kết quả cuối, lưu output validator baseline rồi làm sạch log cũ để validator không đọc lẫn dữ liệu trước khi sửa:

```powershell
.\.venv\Scripts\python.exe scripts/validate_logs.py |
  Tee-Object submission/evidence/00-baseline-log-validator.txt
Remove-Item -LiteralPath data/logs.jsonl
```

Khởi động lại API, chạy load test và kiểm tra:

```powershell
.\.venv\Scripts\python.exe scripts/load_test.py --concurrency 5
.\.venv\Scripts\python.exe scripts/validate_logs.py
```

Điều kiện đạt:

- ít nhất hai `correlation_id` khác nhau;
- không thiếu `user_id_hash`, `session_id`, `feature`, `model` trên API log;
- không còn PII thô;
- validator tối thiểu `80/100`, mục tiêu hiện tại là giữ `100/100`.

Để lấy evidence PII, chỉ dùng dữ liệu giả. Gửi một request có email/điện thoại mẫu, sau đó chứng minh log chỉ còn `[REDACTED_...]`:

```powershell
$body = @{
  user_id = 'student-demo'
  session_id = 'pii-demo'
  feature = 'qa'
  message = 'Lien he demo@example.com hoac 090 123 4567'
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/chat -ContentType 'application/json' -Body $body
Select-String -Path data/logs.jsonl -Pattern 'pii-demo'
```

## 5. CP2 - Traces và prompt versioning

### 5.1 Xác minh trace tree

Sau khi chạy tối thiểu 10 requests, mở đúng project Langfuse cá nhân. Mỗi request phải có cấu trúc gần như sau:

```text
day13-agent-request
└── lab-agent-run
    ├── retrieval
    └── generation
```

Kiểm tra trên một trace:

- metadata có `correlation_id`, `feature`, `model`;
- agent span có `prompt_name`, `prompt_label`, `prompt_version`, `prompt_source`;
- generation có model, input/output tokens và cost;
- không có raw prompt/output chứa PII.

Nếu metadata ghi `prompt_source=local`, app chưa bật Langfuse. Nếu là `local-fallback`, app đã bật nhưng lấy managed prompt thất bại.

### 5.2 Tạo prompt v1/v2

Trong Langfuse, tạo text prompt `day13-chat` với đúng ba biến:

```text
Feature={{feature}}
Docs={{docs}}
Question={{message}}
```

Thực hiện theo thứ tự:

1. Tạo v1, gắn `baseline` và `production`.
2. Tạo v2, thay đổi nhẹ format, gắn `candidate`.
3. Đặt `LANGFUSE_PROMPT_LABEL=baseline`, khởi động lại API và chạy một request.
4. Đặt label thành `candidate`, khởi động lại API và chạy lại cùng input.
5. So sánh hai trace IDs và prompt version.
6. Chuyển `production` sang v2, tạo trace; sau đó rollback `production` về v1 và chụp evidence.

Không hard-code version vào source và không dùng ảnh/trace của người khác.

## 6. CP2 - Dashboard, SLO và alerts

Contract chuẩn nằm ở `config/dashboard.yaml`. Dashboard runtime phải có đúng sáu panel:

1. latency P50/P95/P99 và TTFT P95;
2. traffic;
3. error rate và retrieval success;
4. cost;
5. input/output tokens;
6. quality score.

Kiểm tra contract:

```powershell
.\.venv\Scripts\python.exe scripts/validate_dashboard.py
```

Tạo dashboard HTML local:

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe scripts/run_dashboard.py
Start-Process submission/evidence/dashboard.html
```

Trước khi dùng ảnh dashboard để nộp, cần xử lý hai điểm trong script hiện tại:

- script ghi nhãn `Time range: 60 min` nhưng đang tính trên toàn bộ log; cần lọc record theo timestamp trong 60 phút gần nhất;
- Windows console dùng CP1252 có thể gây `UnicodeEncodeError`; giữ `$env:PYTHONUTF8='1'` hoặc gọi helper UTF-8 giống các script CLI khác.

Dashboard HTML dùng Chart.js từ CDN, vì vậy trình duyệt cần mạng khi mở file. Ảnh evidence phải nhìn thấy dữ liệu, time range, đơn vị và threshold.

Đối chiếu:

- `config/slo.yaml`: target 99.5% thì error budget là 0.5%; số request được phép vi phạm bằng `total_requests * 0.005`.
- `config/alert_rules.yaml`: ba alert phải có condition, duration, severity, owner, Slack channel và runbook.
- `docs/alerts.md`: mỗi runbook phải đi từ panel -> log/correlation ID -> trace -> mitigation.

## 7. Practice incident trước challenge

Không cần `config/challenge.json` khi practice. Ví dụ kiểm tra tail latency:

```powershell
.\.venv\Scripts\python.exe scripts/inject_incident.py --scenario rag_slow
.\.venv\Scripts\python.exe scripts/load_test.py --concurrency 5
Invoke-RestMethod http://127.0.0.1:8000/metrics
.\.venv\Scripts\python.exe scripts/run_dashboard.py
.\.venv\Scripts\python.exe scripts/inject_incident.py --scenario rag_slow --disable
```

Luôn tắt scenario sau khi thử. Có thể practice thêm `tool_fail` và `cost_spike`, nhưng không cần tạo thêm abstraction hoặc công cụ mới.

Quy trình điều tra:

1. Dashboard: xác định metric xấu và khoảng thời gian.
2. Log: lấy một `correlation_id` bất thường.
3. Langfuse: tìm trace cùng `correlation_id`.
4. Span: xác định retrieval hay generation gây chậm/lỗi/tăng cost.
5. Report: ghi root cause, fix action và preventive measure.

## 8. CP3 - Challenge chính thức

Chỉ bắt đầu khi Lab Coach cấp file đúng lớp. Đặt file tại `config/challenge.json`; file đã được `.gitignore`.

```powershell
.\.venv\Scripts\python.exe scripts/inject_incident.py
.\.venv\Scripts\python.exe scripts/load_test.py --challenge --concurrency 5
```

Không tự tạo, sửa, force-add, commit, push hoặc chia sẻ `config/challenge.json`. Incident chỉ đạt khi metric, log và trace cùng khớp một khoảng sự cố/request.

## 9. CP4 - Evidence và report

Lưu evidence vào `submission/evidence/` và dẫn bằng đường dẫn tương đối trong `submission/REPORT.md`.

Ưu tiên thu ngay sau từng bước:

- `01`: pytest;
- `02`: log validator;
- `03`: dashboard validator;
- `04`-`05`: structured log và PII redaction;
- `06`-`08`: trace list, waterfall và metadata;
- `09`-`10`: prompt versions và rollback;
- `11`: dashboard runtime;
- `12`-`14`: incident metric, log và trace.

Không điền kết quả cuối bằng ước lượng. Chỉ ghi số liệu/ID đã đọc lại từ output hoặc UI thật.

## 10. Kiểm tra cuối

```powershell
$env:PYTHONUTF8='1'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/validate_logs.py
.\.venv\Scripts\python.exe scripts/validate_dashboard.py
git status --short
git diff --check
git log -1 --oneline
```

Checklist:

- [ ] Tests pass trên commit cuối.
- [ ] Log validator đạt tối thiểu 80/100 và không có PII leak.
- [ ] Có tối thiểu 10 traces thuộc project cá nhân.
- [ ] Trace có root/retrieval/generation và nối được với log.
- [ ] Có prompt v1/v2, promote và rollback thật.
- [ ] Dashboard runtime đủ sáu panel và dùng đúng cửa sổ 60 phút.
- [ ] SLO, error budget, alerts và runbook khớp nhau.
- [ ] Incident evidence nối đúng metric -> log -> trace.
- [ ] `submission/REPORT.md` đã điền bằng kết quả thật.
- [ ] Không commit `.env`, secret, raw PII, `.venv`, log sinh ra hoặc `config/challenge.json`.

## 11. Thứ tự nên làm tiếp ngay

1. Sửa và kiểm tra hai vấn đề của `scripts/run_dashboard.py`.
2. Chạy API với Langfuse key cá nhân và xác minh trace tree thật.
3. Tạo prompt v1/v2, promote và rollback; lưu evidence ngay.
4. Tạo dashboard runtime từ log mới và chụp evidence.
5. Điền các phần CP1/CP2 đã xác minh vào `submission/REPORT.md`.
6. Practice incident; chờ file challenge chính thức trước khi làm CP3.
7. Chạy toàn bộ kiểm tra cuối rồi mới commit/push.
