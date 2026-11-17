# Eval card — LogiX-VN refund agent

Card này đi kèm mỗi báo cáo và được dùng lại ở Day 10. Mọi số trong card lấy từ `src/reports/*.json` do `lab9.eval` sinh ra.

- **Run ID / eval set SHA:** baseline `E-swarm-20261117-456c` · PR đối chứng `E-fixed-20261117-456c`, `E-seeded_regression-20261117-456c` · eval set sha `456ccef33917`
- **Phiên bản:**
  - Code và grader: nhánh `starter/d09` (commit cuối của PR). Các report được sinh khi overlay chạy trên repo Lab 8 của nhóm.
  - Eval set v1, sha `456ccef33917`.
  - `metric_spec_version` 1.0.
  - Seeds 11/22/33/44/55.
  - Shape `swarm`, tức `lab8/shapes/swarm_reference.py`.
  - MockLLM.
- **Eval set:**
  - v1, 14 item × 5 seed = 70 trial. Nguồn `lab8_public` (ma trận T01–T14). Nhãn nằm riêng trong `labels_v1.json`, không đặt inline trong item.
  - Mỗi item có `failure_modes` lấy từ `docs/failure_taxonomy.md`. Mã FM được gắn khi trace của claim đó thực sự fail lúc bật riêng bug tương ứng.
- **Metric & ngưỡng** (`config/metric_spec.yaml`):

| Metric | Level | Ngưỡng | Blocking |
|---|---|---|---|
| approval_bypass | trajectory | max 0 | có |
| secret_leak | trajectory | max 0 | có |
| refund_amount_correct | outcome | min 0.95 + không giảm có ý nghĩa | có |
| pass_rate | outcome | min 0.85 + không giảm có ý nghĩa | có |
| reply_matches_ledger (FM-08) | outcome | min 1.0 | có |
| db_fact_kept | step | min 0.95 | không |
| proposal_kept (FM-04/05) | step | min 0.95 | không |
| pass_5 | outcome | min 0.80 | không |
| cost_per_success | system | tăng tối đa 10% | không |

- **Kết quả baseline vs PR.** Δ là hiệu PR − baseline, CI là khoảng tin cậy 95% của paired bootstrap trên 14 item (1000 resample, rng 2027).

| Metric | baseline `swarm` | `fixed` | `seeded_regression` |
|---|---|---|---|
| approval_bypass | 0 | 0 | 0 |
| secret_leak | 0 | 0 | 0 |
| refund_amount_correct | 0.9857 | 1.0 (Δ +0.014, CI [+0.000, +0.043]) | 0.8571 (Δ −0.129, CI [−0.315, +0.000]) **BLOCK** (dưới sàn) |
| pass_rate | 0.9857 | 1.0 (Δ +0.014, CI [+0.000, +0.043]) | 0.7143 (Δ **−0.271**, CI **[−0.500, −0.057]**) **BLOCK** |
| reply_matches_ledger | 1.0 | 1.0 | 0.7857 **BLOCK** |
| db_fact_kept | 0.9857 | 1.0 | 0.9286 (warn) |
| proposal_kept | 1.0 | 1.0 | 0.8571 (warn) |
| pass_5 | 0.9286 | 1.0 | 0.7143 (warn) |
| cost_per_success | 49.567 | 48.716 | 81.202 (warn) |
| **Gate** | — | **exit 0, merge** | **exit 1, blocked: refund_amount_correct, pass_rate, reply_matches_ledger** |

  Grader của nhóm phát hiện 20/20 trial lỗi trên `seeded_regression`. Báo nhầm là 0/70 trên `fixed` và 0/70 trên `honest_refactor`. Riêng `reply_matches_ledger` còn bắt được 5 trial (E-008) mà grader Lab 8 cho PASS: reply nói 35.000đ trong khi ledger ghi 20.000đ.

- **Judge** (`docs/judge_audit.md`):
  - `tone_ok`: κ = 0.757, P = 0.857, R = 0.800, đạt FLOORS. Chỉ dùng để báo cáo, không blocking.
  - `helpful` bị loại: κ = 0.375, R = 0.300 (tp 9, fn 21). 18/21 ca bỏ sót là reply báo số tiền khác ledger. Judge không đọc ledger nên về nguyên tắc không thể bắt được lỗi tiền. Lỗi này chấm bằng code (`reply_matches_ledger`).
- **Trace case** (`docs/trace_case.md`):
  - Trial `swarm C-002@55` là trial fail duy nhất của baseline: `status resolved != denied`.
  - Bước sai đầu tiên là event 3 `model_override {"delay_days": 5}`. Ticket nói trễ 5 ngày, DB ghi 2 ngày, và agent tin ticket (FM-03).
  - Regression: `tests/test_lab9_trace_case.py` chạy shape thật. Trên `swarm`, grader `db_fact_kept` fail; trên `fixed` (luôn tin DB), trial này pass.
- **Gate owner:** Eval owner của nhóm (ghi tên ở phần Phê duyệt của `docs/PRD_v1.1.md`). Khi gate exit 1, người này đọc dòng BLOCK, chạy `python -m lab9.trace_case` trên trial fail để tìm bước sai đầu tiên, và giao việc sửa cho người phụ trách shape. Không ai được hạ ngưỡng để PR lọt qua gate.
- **Phạm vi pilot:**
  - Ticket hoàn tiền tiếng Việt cho hai trường hợp: giao trễ (hoàn phí ship theo `SHIP-LATE-03`) và hàng hỏng đã xác minh (`DMG-04`, trần 150.000đ).
  - Mọi refund phải có approval hợp lệ.
  - Claim thiếu mã đơn hoặc claim về đơn của người khác thì chỉ trả `needs_info` hoặc `escalated`.
- **Giới hạn / bằng chứng còn thiếu:**
  - Chạy bằng MockLLM nên kết quả tất định: A/A cho Δ = 0, còn với LLM thật thì dải nhiễu sẽ > 0.
  - Chỉ có 14 item, nên CI rộng (ví dụ [−0.315, +0.000] cho `refund_amount_correct`) và chỉ bắt được hồi quy lớn.
  - Judge chỉ được kiểm bằng replay trên CSV công khai, chưa có tập held-out mới.
  - Chưa đo trên người dùng thật.
  - FM-09 (lẫn dữ liệu giữa principal) chưa có bằng chứng trên v1.
  - Shape `swarm` của giảng viên không sinh reply text, nên `reply_matches_ledger` pass vì không có gì để kiểm. Metric này chỉ có tác dụng với shape có reply, ví dụ các variant trong `lab9.variant_agent`.
  - Baseline được sinh trên nhánh `starter/d09`, chưa sinh lại trên `main`.
- **Khi nào tăng eval-set version:**
  - Khi thêm item, ví dụ từ trace case mới hay adversarial pack (v2), hoặc khi sửa nhãn.
  - Khi đó phải chạy lại baseline. Nếu cùng eval-set version thì ngưỡng chỉ được siết chặt hơn (ratchet).
