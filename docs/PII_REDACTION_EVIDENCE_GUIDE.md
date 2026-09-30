# Bằng chứng 05 — PII redaction

Mục tiêu: gửi PII **giả**, sau đó chứng minh structured log đã thay dữ liệu gốc bằng marker `[REDACTED_...]` nhưng vẫn giữ `correlation_id`.

## 1. Gửi request kiểm thử

Chạy khi API đang mở ở `http://127.0.0.1:8000`:

```powershell
$headers = @{ 'x-request-id' = 'req-pii12345' }
$body = @{
  user_id    = 'fake-user-pii'
  session_id = 'pii-evidence-s01'
  feature    = 'qa'
  message    = 'Email demo.pii@example.test phone 0900000000 CCCD 012345678901'
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:8000/chat' `
  -Headers $headers `
  -ContentType 'application/json' `
  -Body $body
```

Các giá trị trên chỉ là dữ liệu giả dành cho test. Không thay bằng dữ liệu thật.

## 2. Lọc log theo correlation ID

```powershell
Get-Content data/logs.jsonl |
  Where-Object { $_ -match 'req-pii12345' }
```

Trong record `request_received`, cần thấy:

```text
Email [REDACTED_EMAIL] phone [REDACTED_PHONE_VN] CCCD [REDACTED_CCCD]
```

Đồng thời record vẫn phải có:

```text
"correlation_id": "req-pii12345"
```

## 3. Chụp evidence

Chụp record đã lọc sao cho cùng một ảnh thấy được `message_preview` đã che và `correlation_id`. Lưu tại:

```text
submission/evidence/05-pii-redaction.png
```

Evidence hiện tại của repo được tạo từ record có timestamp `2026-09-30T04:52:38.812452Z`.
