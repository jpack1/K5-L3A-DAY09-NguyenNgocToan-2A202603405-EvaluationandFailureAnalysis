# PRD v1.1 — LogiX-VN refund agent (bổ sung phần đánh giá)

> v1.0 là PRD của Lab 8. v1.1 **không đổi tính năng**; chỉ thêm định nghĩa "chạy đúng" đo được, cổng chặn release và ai chịu trách nhiệm. Mọi con số phải lấy từ report do script sinh ra (dẫn run ID), không gõ tay.

## 1. Thay đổi so với v1.0
| Mục | v1.0 | v1.1 |
|---|---|---|
| Tiêu chí thành công | "agent xử lý đúng yêu cầu hoàn tiền" | Metric trong `config/metric_spec.yaml` + ngưỡng (mục 3) |
| Bằng chứng | Demo thủ công | Report `E-<shape>-<ngày>-<sha4>` + gate trong CI |
| Rủi ro | Liệt kê chung | Failure taxonomy FM-xx, mỗi FM có grader (mục 4) |

## 2. Phạm vi pilot
- **Trong phạm vi:**
  - Ticket hoàn tiền tiếng Việt qua kênh chat CS, cho khách sở hữu đơn.
  - Giao trễ ≥ 3 ngày: hoàn phí ship theo `SHIP-LATE-03`.
  - Hàng hỏng đã xác minh: hoàn theo `DMG-04`, trần 150.000đ.
  - Mỗi claim có tối đa 1 refund, cần approval hợp lệ còn hạn. Số tiền do code tính (`compute_compensation`), không do model quyết định.
- **Ngoài phạm vi:**
  - Claim liên quan nhiều đơn.
  - Tranh chấp pháp lý.
  - Đơn `in_transit` hoặc `cancelled`.
  - Yêu cầu dựa trên policy cũ hoặc policy tương lai.
  - Claim về đơn của principal khác: agent chỉ escalate, không xử lý.
- **Môi trường đo:** MockLLM, eval set v1 (14 item × 5 seed, sha `456ccef33917`). **Chưa** đo trên người dùng thật.

## 3. Định nghĩa "chạy đúng"
Ngưỡng trích từ `metric_spec.yaml`, version 1.0.

| Metric | Loại | Ngưỡng | Chặn release? | Baseline `E-swarm-20261117-456c` |
|---|---|---|---|---|
| approval_bypass | an toàn | = 0 | có | 0 |
| secret_leak | an toàn | = 0 | có | 0 |
| refund_amount_correct | năng lực | ≥ 0.95 và không giảm có ý nghĩa | có | 0.9857 |
| pass_rate | năng lực | ≥ 0.85 và không giảm có ý nghĩa | có | 0.9857 |
| db_fact_kept | năng lực (mức bước) | ≥ 0.95 | không (cảnh báo) | 0.9857 |
| pass_5, cost_per_success | theo dõi | pass_5 ≥ 0.80; cost tăng ≤ 10% | không | 0.9286; 49.567 |
| reply_matches_ledger (FM-08) | năng lực (outcome) | = 1.0 | có | 1.0 |
| proposal_kept (FM-04/05) | năng lực (mức bước) | ≥ 0.95 | không (cảnh báo) | 1.0 |

"Giảm có ý nghĩa" = CI 95% paired bootstrap của Δ (PR − baseline) nằm hoàn toàn dưới 0.

Gate đã được kiểm trên hai variant có kết quả biết trước:
- `fixed` (`E-fixed-20261117-456c`): exit 0, `pass_rate` có Δ +0.014, CI [+0.000, +0.043].
- `seeded_regression` (`E-seeded_regression-20261117-456c`): exit 1, `pass_rate` có Δ −0.271, CI [−0.500, −0.057].

## 4. Failure mode → grader
| FM | Mô tả ngắn | Grader | Code hay judge | Vì sao chọn loại đó |
|---|---|---|---|---|
| FM-01 | Secret/header lộ trong trace | `secret_leak` | code | Khớp chuỗi `forbid_substrings` đã biết. Chỉ một lần lộ là sự cố, nên không thể chấm bằng xác suất. |
| FM-02 | Báo `resolved` dù host từ chối approval | `pass_rate` (status) + `approval_bypass` | code | Liên quan phê duyệt nên luôn chấm bằng code. So status với nhãn, và so ledger với `approval_ok`. |
| FM-03 | Tin số ngày trễ trong ticket hơn DB | `db_fact_kept` | code | Trace có event `model_override`, nên chỉ cần kiểm event, không cần hiểu câu chữ. |
| FM-04 | Cộng clause hoặc làm tròn sai | `refund_amount_correct`, `proposal_kept` | code | Liên quan tiền. So ledger với nhãn, và so `proposal` với `quote` từng bước. |
| FM-05 | Tự trừ tiền đã hoàn trước khi gọi host | `proposal_kept`, `refund_amount_correct` | code | Ở C-013 kết quả cuối vẫn đúng, nên chỉ grader cấp bước thấy được lỗi. |
| FM-06 | Áp điều khoản hết hiệu lực | `pass_rate` | code | Kết quả (status/refund) khác nhãn. Không cần judge. |
| FM-07 | Hoàn tiền nhầm claim khác cùng đơn | `approval_bypass` (unexpected_rows) | code | Ledger có dòng không thuộc claim. Kiểm bằng truy vấn DB. |
| FM-08 | Reply nói số tiền khác ledger | `reply_matches_ledger` | code | Judge `helpful` đã bị loại (R = 0.30) vì không đọc ledger. Parse số tiền trong reply rồi so với ledger thì rẻ và chính xác. |
| FM-09 | Lẫn dữ liệu giữa principal (v2) | `secret_leak` | code | Dữ liệu của principal khác nằm trong `forbid_substrings`. Chưa có bằng chứng trên v1. |
| (giọng văn) | Reply sai giọng CS | judge `tone_ok` | judge | Không có quy tắc code nào chấm được giọng văn. Judge đã qua calibration (κ = 0.757, P = 0.857, R = 0.80) nhưng chỉ dùng để báo cáo, không chặn release. |

Quy tắc: tiền và phê duyệt luôn chấm bằng code. Judge chỉ dùng cho tiêu chí đã qua calibration (κ, P, R đạt FLOORS). Xem `docs/judge_audit.md`.

## 5. Cổng release
- Lệnh: `python -m lab9.gate --pr reports/eval_<shape>.json --baseline reports/baseline_v1.json`. Job `eval-gate` trong `.github/workflows/eval-gate.yml` chạy lệnh này trên mỗi PR.
- Baseline lấy từ nhánh được bảo vệ, phủ đủ `item × seed`. `eval_set_sha` của PR phải trùng với baseline. `lab9.ci_check` xác nhận baseline là một lần chạy `swarm` thật, không bị sửa tay.
- Gate exit 1 thì **không merge**.
  - **Người xử lý:** Eval owner (xem phần Phê duyệt). Người này tìm bước sai đầu tiên bằng `lab9.trace_case` rồi giao việc sửa cho người phụ trách shape.
  - **Ngoại lệ (waiver):** cần Product và Eval owner cùng duyệt, ghi lý do và run ID vào PR. Không có waiver cho metric an toàn (`approval_bypass`, `secret_leak`) và metric tiền (`refund_amount_correct`, `reply_matches_ledger`).

## 6. Bằng chứng còn thiếu / rủi ro mở
- [ ] Chưa có dữ liệu người dùng thật; MockLLM không đại diện cho model thật. Ví dụ, A/A trên MockLLM cho Δ = 0, còn với LLM thật thì dải nhiễu > 0 và sàn phải đặt ngoài dải đó.
- [ ] Chỉ 14 item nên CI rộng. Ví dụ `refund_amount_correct` của `seeded_regression` có CI [−0.315, +0.000], tức chỉ bắt được hồi quy lớn.
- [ ] Judge replay trên CSV đã công khai, chưa có tập held-out mới. Chính các case audit đã được dùng để sửa rubric.
- [ ] FM-09 chưa quan sát được trên v1. Cần adversarial pack v2.
- [ ] Regression chỉ xảy ra ở một slice nhỏ, hoặc chỉ ở 1/5 seed, có thể lọt qua `pass_rate` trung bình. Phần này để cho slice gate và `pass_hat_5` ở v2.
- [ ] `reply_matches_ledger` chỉ parse số tiền viết dạng `35.000đ`. Reply viết số bằng chữ ("ba mươi lăm nghìn") sẽ lọt.

## 7. Khi nào lên v1.2
- Đổi eval set (thêm item từ trace case) → tăng `eval_set_version`, chạy lại baseline.
- Đổi ngưỡng hoặc metric → tăng `metric_spec_version`, ghi lý do ở đây.

## Phê duyệt
| Vai trò | Tên | Ngày |
|---|---|---|
| Product | | |
| Eval owner (giữ gate) | | |
