# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi nhóm 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `<shape> <claim>@<seed>`, run ID trong report |
| Triệu chứng | Grader nào fail; reply nói gì so với ledger ghi gì |
| Bước sai đầu tiên | Số thứ tự event + kind + trích payload (≤1 dòng) |
| Vì sao là bước *đầu tiên* | Các bước trước đó đúng ra sao (dẫn số event) |
| Failure mode | Mã FM-xx trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng claim@seed trên shape `fixed`: bước đó khác thế nào |
| Regression test | Tên test + grader/assert nào bắt được; đã thấy fail trên variant lỗi và pass trên `fixed` chưa |
| Chưa chắc chắn | Điều trace không chứng minh được |

## Case của nhóm: `swarm C-002@55`

```bash
cd src
python -m lab9.trace_case --shape swarm --claim C-002 --seed 55
python -m lab9.trace_case --shape fixed --claim C-002 --seed 55
```

| Trường | Nội dung |
|---|---|
| Trial | `swarm C-002@55`. Đây là trial fail duy nhất trong baseline `E-swarm-20261117-f3c2` (row `E-002`, seed 55). |
| Triệu chứng | 3 grader fail: `pass_rate` (lab8 báo `status resolved != denied`), `refund_amount_correct` và `db_fact_kept`. Ledger ghi `refund_vnd=20000`, `refund_count=1`, trong khi nhãn là 0 và 0. Shape `swarm` không sinh reply nên không có câu trả lời để so. |
| Bước sai đầu tiên | Event **3** `model_override {"delay_days": 5}`. |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng claim C-002, task `check_applicable_policy`, `facts` rỗng. Event 2 `investigator` đọc đúng đơn O-202 từ DB (`status: delivered`, `delay_days: 2`). Đến event 3, agent thay số 2 của DB bằng con số "5 ngày" khách tự khai trong ticket. Event 4 `quote` (20.000đ theo `SHIP-LATE-03`) tính đúng **dựa trên** dữ liệu đã bị thay, nên là hệ quả chứ không phải lỗi gốc. |
| Failure mode | **FM-03** ticket_trust (layer model/prompt). Bug chỉ xuất hiện khi `seed % 5 == 0`, vì vậy chỉ seed 55 fail. |
| Đối chứng | `fixed C-002@55` không có event `model_override`. Event 3 là `quote {"amount_vnd": 0, "reason": "no_entitlement"}` vì 2 ngày < 3. Kết quả: `denied`, ledger 0, lab8 PASS. |
| Regression test | `tests/test_lab9_trace_case.py` chạy shape thật trên store tạm. `test_swarm_c002_s55_overrides_db_fact` xác nhận `DbFactKept` = False, lab8 FAIL và ledger 20.000 trên `swarm`. `test_fixed_c002_s55_keeps_db_fact` xác nhận `DbFactKept` = True, lab8 PASS và ledger 0 trên `fixed`. Cả hai test đều pass, tức là test thấy lỗi trên shape có bug và không báo nhầm trên `fixed`. |
| Chưa chắc chắn | MockLLM tất định nên seed 55 lần nào cũng fail. Với LLM thật, tần suất bị ticket thuyết phục có thể khác 1/5. Trace chỉ ghi agent **đã** override, không giải thích vì sao model chọn tin ticket. Ngoài ra `db_fact_kept` chỉ bắt override có để lại event: một override không để lại event (`quiet_override`) sẽ lọt qua grader này, chỉ `refund_amount_correct` và `pass_rate` còn thấy. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
