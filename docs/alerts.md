# Alert và Runbook — K4-L3B Day 13

Mỗi alert dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-2A202602853`

---

## Alert 1

- **Tên:** `HighLatencyP95`
- **Severity:** `warning`
- **Duration:** `5m`
- **Kênh thông báo:** Slack `#k4-l3b-alerts`
- **SLI/SLO liên quan:** SLO `fast_successful_requests` — `p95(response_sent.latency_ms) <= 3000ms`
- **Điều kiện và thời gian duy trì:** `p95(latency_ms) > 3000ms` kéo dài ít nhất 5 phút
- **Ảnh hưởng tới người dùng:** Người dùng phải chờ quá 3 giây để nhận câu trả lời, gây trải nghiệm chậm chạp và có thể dẫn đến timeout phía client.
- **Ba bước kiểm tra đầu tiên:**
  1. Mở panel **Latency percentiles and TTFT** trên dashboard, xác nhận P95/P99 đang vượt ngưỡng và khoảng thời gian bắt đầu tăng.
  2. Lọc `data/logs.jsonl` với `event == "response_sent" and latency_ms > 3000`, lấy một `correlation_id` bất thường.
  3. Tìm trace có cùng `correlation_id` trên Langfuse, so sánh thời gian span `retrieval` và `generation` để xác định bước gây chậm.
- **Mitigation tạm thời:** Nếu span `rag_slow` bất thường → kiểm tra vector store; nếu generation chậm → rollback prompt về version nhẹ hơn hoặc giảm `max_tokens`.
- **Owner:** `student-2A202602853`

---

## Alert 2

- **Tên:** `HighErrorRate`
- **Severity:** `critical`
- **Duration:** `3m`
- **Kênh thông báo:** Slack `#k4-l3b-alerts`
- **SLI/SLO liên quan:** Guardrail `error_rate_pct_max: 2%` — tỷ lệ `request_failed / request_received * 100 > 2`
- **Điều kiện và thời gian duy trì:** Error rate vượt 2% kéo dài ít nhất 3 phút
- **Ảnh hưởng tới người dùng:** Hơn 1/50 request trả về lỗi thay vì câu trả lời, người dùng nhận HTTP 500 và không thể sử dụng dịch vụ.
- **Ba bước kiểm tra đầu tiên:**
  1. Mở panel **Error rate and retrieval success** trên dashboard, xem `error_rate_pct` và breakdown theo `error_type`.
  2. Lọc `data/logs.jsonl` với `event == "request_failed"`, lấy `correlation_id` và `error_type` của các request lỗi.
  3. Tìm trace cùng `correlation_id` trên Langfuse, kiểm tra span `retrieval` có `tool_success=false` hay `generation` raise exception.
- **Mitigation tạm thời:** Nếu `error_type=RuntimeError` từ vector store → kiểm tra incident `tool_fail`; nếu là lỗi LLM → rollback prompt hoặc giảm tải bằng cách tắt tính năng liên quan.
- **Owner:** `student-2A202602853`

---

## Alert 3

- **Tên:** `LowRetrievalSuccessRate`
- **Severity:** `warning`
- **Duration:** `5m`
- **Kênh thông báo:** Slack `#k4-l3b-alerts`
- **SLI/SLO liên quan:** Guardrail `retrieval_success_rate_pct_min: 90%` — tỷ lệ `tool_success=true` trong các request có retrieval
- **Điều kiện và thời gian duy trì:** Retrieval success rate dưới 90% kéo dài ít nhất 5 phút
- **Ảnh hưởng tới người dùng:** RAG pipeline không trả về document phù hợp, LLM phải dùng fallback dẫn đến câu trả lời chất lượng thấp và `quality_score` giảm.
- **Ba bước kiểm tra đầu tiên:**
  1. Mở panel **Error rate and retrieval success** trên dashboard, xem `tool_success_rate_pct` theo thời gian.
  2. Lọc `data/logs.jsonl` với `tool_success == false`, lấy `correlation_id` và ghi lại thời điểm bắt đầu giảm.
  3. Tìm trace cùng `correlation_id`, kiểm tra span retrieval có metadata `doc_count=0` hoặc có exception từ vector store.
- **Mitigation tạm thời:** Kiểm tra trạng thái vector store (incident `tool_fail` / `rag_slow`); nếu chỉ một phần corpus bị ảnh hưởng thì xem xét route query sang fallback corpus; nếu toàn bộ lỗi thì escalate on-call.
- **Owner:** `student-2A202602853`
