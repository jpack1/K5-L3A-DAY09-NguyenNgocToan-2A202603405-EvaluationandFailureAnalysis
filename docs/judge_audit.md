# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (tp 24, fp 4, fn 6, tn 66) | **dùng**, chỉ làm metric báo cáo, không blocking |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Trượt** κ và R (tp 9, fp 0, fn 21, tn 70) | **loại**, không dùng làm gate |

Tỉ lệ FAIL quan sát được và sau hiệu chỉnh Rogan-Gladen:
- tone: 0.28 → 0.30.
- helpful: 0.09 → 0.30. Judge helpful báo thấp hơn tỉ lệ lỗi thật hơn 3 lần.

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | tone H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em", dùng "nha" là quá suồng sã với khách đang khiếu nại. Rubric cần ghi rõ cách xưng hô: dùng "LogiX" và "anh/chị", cấm "em/bạn/nha". |
| 2 | tone H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | Người | Judge chỉ nhìn kính ngữ mở đầu ("Dạ, vui lòng") mà bỏ qua câu mang giọng ra lệnh. Rubric cần thêm: câu nào ra lệnh hoặc chặn khách liên hệ thì FAIL, dù có kính ngữ. |
| 3 | tone H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì "thiếu xin lỗi". Rubric phải nói rõ ngắn gọn, đủ ý thì PASS và xin lỗi là không bắt buộc. Không sửa thì judge sẽ thưởng cho reply dài dòng. |
| 4 | tone H-051 "…đã refund 90.000đ…" | FAIL | PASS | Người | Style guide CS LogiX cho phép từ "refund". Thêm vào rubric danh sách từ mượn được phép. |
| 5 | tone H-081 "…chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** | Ghi chú nói người gán nhãn đọc nhầm ticket. Sửa nhãn người thành FAIL; sau khi sửa, κ của tone còn tăng thêm. |
| 6 | tone H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | Người | Reply hứa một khoản hệ thống không ghi. Đây là lỗi nội dung (gần FM-08) chứ không phải lỗi giọng văn, nên nên chấm bằng code chứ không giao cho judge tone. |
| 7 | helpful HL-015 "…đã hoàn 55.000đ cho đơn O-112" (ledger 40.000đ) | PASS | FAIL | Người | Judge không thấy ledger nên không thể biết số tiền sai. 18/21 FN của helpful là đúng kiểu này, tức FM-08. |
| 8 | helpful HL-016/HL-028/HL-090 (xin lỗi lặp lại 2 lần, số tiền sai) | PASS | FAIL | Người | Judge thiên vị reply dài và nhiều lời xin lỗi (verbosity bias). Ngay cả khi số tiền sai, reply dài vẫn được PASS. |
| 9 | helpful HL-047/HL-091/HL-097 "Ok bạn, đơn O-xxx xử lý rồi nhé." | PASS | FAIL | Người | Reply không nói kết quả hay số tiền, tức là không giúp được khách, vậy mà judge vẫn PASS. |

## Kết luận
- **Loại `helpful`.** Precision = 1.0 nhưng con số này đánh lừa: judge gần như luôn chấm PASS (chỉ 9/100 FAIL), nên bỏ sót 21/30 lỗi thật (R = 0.30, κ = 0.375). Phần lớn FN là reply báo số tiền khác ledger (FM-08). Judge chỉ đọc reply, không đọc ledger, nên về nguyên tắc không thể bắt được lỗi này. Nếu dùng làm gate, judge sẽ cho qua đúng loại lỗi gây thiệt hại tiền. FM-08 phải chấm bằng code: parse số tiền trong reply rồi so với `refund_vnd` trong ledger (metric M3).
- **Giữ `tone_ok`, nhưng không blocking.** Judge đạt cả ba sàn, nhưng 4 FP và 6 FN cho thấy rubric còn mơ hồ ở cách xưng hô, giọng ra lệnh, độ dài và từ mượn. Cần sửa rubric theo các case 1–4 và sửa nhãn người ở H-081.
- **Rủi ro còn lại:** judge chỉ mới được kiểm trên dữ liệu replay công khai, và chính các case audit ở trên đã được dùng để sửa rubric. Vì vậy các số đo trên lạc quan hơn thực tế. Cần một bộ nhãn người mới, chưa từng dùng để chỉnh rubric (held-out thật), để đo lại.
