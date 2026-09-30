# Hướng dẫn Checkpoint 3 — Incident Challenge

Mục tiêu của CP3 là chứng minh một chuỗi điều tra nhất quán:

> **Metric bất thường → log có `correlation_id` → trace cùng ID → span gây ảnh hưởng → root cause → hành động xử lý**

CP3 đạt tối đa 15 điểm. Validator không thay thế ba evidence runtime bắt buộc.

## 1. Quy tắc an toàn

- `config/challenge.json` là file riêng do Lab Coach cấp. Không mở để chép nội dung, không sửa, không chia sẻ, không force-add, commit hoặc push.
- Không suy đoán trước incident chính thức. Chỉ kết luận sau khi metric, log và trace cùng chỉ về một nguyên nhân.
- Không dùng evidence hoặc challenge của người khác.
- Practice dùng `--scenario`; challenge chính thức phải bỏ `--scenario`.
- Chỉ tắt incident sau khi đã tạo traffic và thu đủ evidence.

Kiểm tra file challenge tồn tại và vẫn bị Git bỏ qua mà không đọc nội dung:

```powershell
Test-Path .\config\challenge.json
git check-ignore -v .\config\challenge.json
git ls-files --error-unmatch .\config\challenge.json
```

Kết quả mong đợi: lệnh đầu là `True`, lệnh thứ hai chỉ ra rule `.gitignore`, lệnh cuối thất bại vì file không được track.

## 2. Kiểm tra trước khi chạy

Kích hoạt môi trường và kiểm tra API:

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\Activate.ps1
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 4
```

Nếu API chưa chạy, mở terminal riêng tại root repo:

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

Trước challenge, `/health` phải có:

- `ok: true`;
- `tracing_enabled: true`;
- cả ba incident đều là `false`.

Giữ terminal API mở trong toàn bộ quá trình.

## 3. Practice tùy chọn

Practice dùng một trong ba scenario công khai, không dùng làm kết luận cho challenge chính thức:

```powershell
python scripts/inject_incident.py --scenario rag_slow
python scripts/load_test.py --concurrency 5
python scripts/inject_incident.py --scenario rag_slow --disable
```

Có thể thay `rag_slow` bằng `tool_fail` hoặc `cost_spike`. Sau practice, kiểm tra `/health` để chắc chắn mọi incident đã tắt.

## 4. Chạy challenge chính thức

Ghi lại thời điểm bắt đầu để khoanh đúng time range:

```powershell
$cp3Start = Get-Date
$cp3Start.ToString('yyyy-MM-dd HH:mm:ss zzz')
```

Bật incident từ file challenge riêng, sau đó tạo traffic đúng cohort:

```powershell
python scripts/inject_incident.py
python scripts/load_test.py --challenge --concurrency 5
```

Lưu lại ngay từ output:

- `Challenge ID`;
- cohort;
- các `correlation_id` trả về;
- thời điểm bắt đầu và kết thúc lượt chạy.

Không mở `config/challenge.json` để lấy các giá trị này. Script `load_test.py --challenge` đã in Challenge ID và cohort cần dùng.

## 5. Điều tra theo Metrics → Logs → Traces

### Bước 1 — Metrics

Xem snapshot API và tạo lại dashboard từ log hiện tại:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/metrics | ConvertTo-Json -Depth 6
python scripts/run_dashboard.py
```

Mở `submission/evidence/dashboard.html`, đặt time range bao phủ lượt challenge và tìm triệu chứng nổi bật:

- latency/TTFT tăng;
- error hoặc retrieval failure tăng;
- token/cost tăng bất thường;
- quality giảm.

Chụp ảnh có tên:

```text
submission/evidence/12-incident-metric.png
```

Ảnh phải đọc được metric, đơn vị, giá trị cụ thể và time range. Không chỉ ghi “latency cao” hoặc “có lỗi”.

### Bước 2 — Logs

Đọc JSONL bằng PowerShell và xếp các request bất thường lên đầu:

```powershell
$logs = Get-Content .\data\logs.jsonl |
  ForEach-Object { $_ | ConvertFrom-Json }

$logs |
  Where-Object event -eq 'response_sent' |
  Sort-Object latency_ms -Descending |
  Select-Object -First 10 ts,event,correlation_id,feature,latency_ms,ttft_ms,cost_usd,tokens_out,quality_score,tool_success |
  Format-Table -AutoSize

$logs |
  Where-Object event -eq 'request_failed' |
  Select-Object ts,event,correlation_id,feature,error_type,error_message |
  Format-Table -AutoSize
```

Chọn một request đúng time range và phù hợp với metric bất thường. Sau đó thay giá trị mẫu dưới đây bằng ID thật:

```powershell
$cid = 'req-THAY-BANG-ID-THAT'
$logs |
  Where-Object correlation_id -eq $cid |
  ConvertTo-Json -Depth 6
```

Chụp log line rõ timestamp, event, giá trị bất thường và `correlation_id`:

```text
submission/evidence/13-incident-log.png
```

### Bước 3 — Traces

Trong Langfuse:

1. Mở **Tracing** và chọn đúng project cá nhân.
2. Giới hạn time range trùng với metric/log.
3. Tìm trace bằng `correlation_id` đã chọn trong metadata hoặc tên/ID trace.
4. Mở trace và kiểm tra waterfall.
5. So sánh span `retrieval` và `generation`: duration, status/error, token và cost.
6. Ghi lại **Trace ID** và tên span gây ảnh hưởng.

Chụp ảnh sao cho thấy cùng `correlation_id`, Trace ID và span bất thường:

```text
submission/evidence/14-incident-trace.png
```

Ảnh Langfuse trace không được gọi là “log”; log chuẩn của bài là `data/logs.jsonl`.

## 6. Cách kết luận root cause

Chỉ dùng bảng này để đối chiếu tín hiệu, không dùng để đoán incident chính thức:

| Metric | Log | Trace | Kết luận có thể kiểm chứng |
|---|---|---|---|
| Latency/TTFT tăng | request chậm, cùng CID | span `retrieval` kéo dài | Bottleneck ở retrieval/dependency |
| Error/retrieval success xấu | `request_failed` hoặc tool thất bại | span retrieval/tool có error | Lỗi retrieval/tool |
| Cost/token tăng | `tokens_out` và `cost_usd` cao | span `generation` có output token/cost cao | Regression ở generation/token budget |

Root cause hợp lệ phải trả lời đủ:

- thành phần nào hỏng hoặc chậm;
- bằng chứng định lượng nào chứng minh;
- vì sao metric, log và trace cùng thuộc một request/time range;
- fix action khôi phục ngay;
- preventive measure ngăn tái diễn.

Ví dụ phân biệt hai loại hành động:

- **Fix action:** rollback prompt/model, tắt feature lỗi, giảm output budget, retry hoặc chuyển fallback.
- **Preventive measure:** alert theo SLO, timeout/circuit breaker, regression test, token cap hoặc canary rollout.

## 7. Tắt incident sau khi thu evidence

```powershell
python scripts/inject_incident.py --disable
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 4
```

Hoàn thành khi cả ba incident trở lại `false`.

## 8. Điền báo cáo

Điền các trường CP3 có sẵn trong `submission/REPORT.md`; không để giá trị suy đoán:

```text
Challenge ID: <từ output load_test --challenge>
Time range: <bắt đầu–kết thúc, kèm timezone>
Metric: <tên, giá trị, đơn vị, baseline/threshold để so sánh>
Log: <timestamp, event, correlation_id, trường bất thường>
Trace ID: <ID thật trên Langfuse>
Affected span: <retrieval hoặc generation, duration/status/token/cost>
Root cause: <một kết luận được ba lớp bằng chứng hỗ trợ>
Fix action: <hành động khôi phục ngay>
Preventive measure: <kiểm soát ngăn tái diễn>
```

Liên kết đúng ba evidence:

```markdown
![Incident metric](evidence/12-incident-metric.png)
![Incident log](evidence/13-incident-log.png)
![Incident trace](evidence/14-incident-trace.png)
```

Sau khi CP3 thực sự hoàn tất, xóa câu “CP3 challenge chưa thực hiện” ở mục hạn chế của report.

## 9. Kiểm tra hoàn thành

```powershell
python -m pytest -q
python scripts/validate_logs.py
python scripts/validate_dashboard.py
git status --short
git check-ignore -v .\config\challenge.json
```

Checklist:

- [ ] Có Challenge ID và time range chính xác.
- [ ] `12-incident-metric.png` có metric cụ thể, đơn vị và time range.
- [ ] `13-incident-log.png` có log line và `correlation_id`.
- [ ] `14-incident-trace.png` có cùng `correlation_id`, Trace ID và span bị ảnh hưởng.
- [ ] Root cause nhất quán qua metric, log và trace.
- [ ] Có fix action và preventive measure riêng biệt, khả thi.
- [ ] Incident đã tắt sau khi điều tra.
- [ ] `config/challenge.json` vẫn bị ignore và không xuất hiện trong Git.
- [ ] Không lộ API key, secret, PII hoặc nội dung challenge riêng.

## Trạng thái repo khi viết hướng dẫn

- `config/challenge.json`: đã tồn tại và không cần mở nội dung.
- API `/health`: hoạt động.
- Langfuse tracing: đang bật.
- Incident: cả ba đang tắt.

