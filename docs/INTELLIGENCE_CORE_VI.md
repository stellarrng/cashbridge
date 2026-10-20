# Lõi điều phối (Intelligence Core): đã làm gì, đo được gì, còn thiếu gì

Ngày 19/10/2026. Mọi số liệu lấy từ code chạy trên dữ liệu SYNTHETIC. Benchmark là MÔ PHỎNG.

## 1. Ý tưởng gốc và cách làm trong code

Ý tưởng ban đầu: một bộ điều phối đứng sau dashboard. Nó không nói chuyện với người dùng, chỉ nhận dữ liệu có cấu trúc, tự lập kế hoạch, và học từ kết quả. Bản này làm đúng ba lớp đã đề xuất, nhưng tách bạch trách nhiệm từng lớp.

| Lớp | Câu hỏi | Trong CashBridge |
|---|---|---|
| A. Dự báo | Không làm gì thì chuyện gì có thể xảy ra? | Mô hình xác suất trả đúng hạn (hồi quy logistic, 185 hóa đơn) + `core/scenario_simulator.py` (2.000 quý mô phỏng) |
| B. Lập kế hoạch | Kế hoạch được phép nào đạt mục tiêu với chi phí thấp nhất? | `agents/intelligence_core.py`: liệt kê mọi kế hoạch, chấm trên cùng bộ đường mô phỏng, chọn; nói thẳng khi không kế hoạch nào đạt |
| C. Quản trị | Kế hoạch đó có được phép không? | `validate_plan` độc lập, gatekeeper theo tầng, nhật ký băm, mỗi hồ sơ vẫn do kế toán soạn và Giám đốc duyệt OTP |

LLM giao tiếp với người dùng **không** đi vào lõi. Mục tiêu chỉ là mẫu cố định: giữ mọi tuần không âm, hoặc giữ trên mức đệm, ở 80/85/90/95% số đường. Câu chữ người dùng gõ không chọn được mục tiêu hay công cụ. Có test chứng minh điều này.

## 2. Trạng thái có cấu trúc (`cb.state.v1`)

Mỗi lần lập kế hoạch, Core dựng một trạng thái gồm:
- tiền hiện có, mức đệm;
- kịch bản cơ sở: tuần âm đầu tiên, mức thiếu, số dư từng tuần;
- rủi ro khi không làm gì: xác suất âm theo tuần, phân vị 10/50/90, thiếu hụt kỳ vọng và ở phân vị 95;
- phải thu: tỷ trọng buyer lớn nhất, hóa đơn được thế chấp và lý do loại từng hóa đơn;
- đơn hàng đã xác nhận (không thế chấp được);
- các giới hạn;
- phiên bản mô hình thế giới.

## 3. Lập kế hoạch

- **Hành động được phép:**
  - factoring 1–3 hóa đơn;
  - vay cầu nối;
  - vay kèm 1–2 hóa đơn;
  - xin giảm cọc PO-2214 xuống 15% (cần nhà cung cấp đồng ý; mô phỏng giả định chỉ thành công ở 60% số đường).
- **Thời điểm giải ngân:** tuần đầu tiên có ≥ 10% số đường âm, hoặc tuần âm đầu tiên của kịch bản cơ sở.
- **Giới hạn mà planner không đổi được:**
  - tối đa 3 hồ sơ;
  - tổng tiền ≤ 1,5 lần mức thiếu ở phân vị 95;
  - không thế chấp đơn hàng, hóa đơn chưa xác minh, hóa đơn ngoại tệ, hóa đơn có xác suất đúng hạn dưới 50%, hoặc hóa đơn đến hạn trong vòng 14 ngày sau giải ngân.
- **Cách chọn:** lấy kế hoạch rẻ nhất đạt mục tiêu. Nếu không kế hoạch nào đạt, lấy kế hoạch rẻ nhất trong khoảng 2 sai số chuẩn của mức tốt nhất, để không trả tiền cho khác biệt chỉ là nhiễu mô phỏng.
- **Chi phí factoring** tính lãi tới tuần buyer thực sự trả trên từng đường. Lần chạy đầu không làm vậy, và planner đã chọn đúng những hóa đơn trả trễ nhất (lựa chọn bất lợi). Đã sửa, và ghi ở DECISIONS 81.

**Kết quả trên ca demo** (mô hình gốc, 2.000 đường):

| | Đường không âm tuần nào |
|---|---|
| Không làm gì | khoảng 8% |
| Workflow cố định: factoring INV-1030 ở tuần 7 | khoảng 28–29% |
| Core: vay cầu nối + factoring INV-1030 + INV-1053, giải ngân tuần 2 | khoảng 87%; 89% nếu thêm xin giảm cọc (đây là kế hoạch trang Lõi điều phối chọn), chi phí dự kiến khoảng USD 4.400 |

Mục tiêu 90% chưa đạt, và Core báo đúng như vậy.

## 4. Học, khác với nhớ

- **Bộ nhớ ca** (`CaseMemory`): JSONL băm nối chuỗi, lưu kế hoạch kèm dự đoán, sau đó là kết quả. Sửa một dòng thì `verify()` báo hỏng. Truy vấn "các quý tương tự" theo khoảng cách chuẩn hóa trên 6 đặc trưng.
- **Quy nguyên nhân** (`attribute_outcome`): so đường thực tế với kỳ vọng tới tuần đáy. Mỗi lần trượt được gắn một trong các nguyên nhân sau, kèm bài học:
  - buyer trả chậm hơn mô hình;
  - đơn hàng giao trễ;
  - chi phí vượt;
  - khoản tài trợ nhỏ hơn khoảng thiếu;
  - mục tiêu quá hẹp (chỉ nhìn tuần âm đầu tiên).
- **Học** (`WorldModelLearner`): chỉ hiệu chỉnh mô hình thế giới, gồm độ lệch logit theo buyer (prior Gauss) và hệ số tin cậy giao hàng (prior Beta). Học offline trên các kết quả đã ghi. Giới hạn chính sách không nằm trong phần được học.
- **Cổng chấp nhận:** đánh giá giữ lại từng quý (leave-one-quarter-out). Bản mới phải tăng log-likelihood ≥ 0,002 mỗi quan sát **và** thắng ở đa số quý.
- **Kích hoạt** (`ModelRegistry`):
  - đề xuất chỉ được lưu dạng "chờ duyệt";
  - kích hoạt là thao tác L2 `activate_model_update`, cần một người đứng tên;
  - người đó phải khác người đề xuất;
  - đề xuất không qua cổng thì không kích hoạt được.

  Trong demo, kế toán đề xuất, Giám đốc duyệt.

Về dữ liệu kết quả: demo chưa có kết quả thật, nên bộ nhớ được nạp sẵn 8 quý SIMULATED. Mỗi quý là danh mục hiện tại bị xáo trộn, phát lại trong một **thế giới kiểm tra ẩn** do nhóm viết: Oakline trả chậm hơn lịch sử (logit −1,2), Harbor hơi chậm (−0,4), đơn hàng chỉ giao được 80% so với mức khai. Nút "Cho quý này diễn ra" thêm một quý nữa theo cùng cách.

## 5. Benchmark (`make bench`, MÔ PHỎNG)

Huấn luyện trên 8 quý, kiểm tra trên 40 quý mới. Mỗi kế hoạch được chấm trên 1.000 đường của thế giới ẩn, dùng seed khác với seed lúc lập kế hoạch.

| | A. Workflow cố định | B. Planner + bộ nhớ | C. Planner + học |
|---|---|---|---|
| Đường không âm tuần nào (trung bình) | 8,7% | 64,9% | 66,8% |
| Chi phí tài trợ dự kiến (trung bình) | USD 960 | USD 4.086 | USD 4.012 |
| Hồ sơ cần duyệt (trung bình) | 0,9 | 3,0 | 3,0 |
| Vi phạm chính sách | 6 | 0 | 0 |
| Tự tin quá mức (dự đoán − thực tế) | +20,6 điểm % | +19,3 điểm % | +9,3 điểm % |
| Giữ nguyên kế hoạch khi đầu vào lệch 3% (lập lại có biết kế hoạch đang dùng) | 80% | 55% | 77,5% |
| Kết quả lệch ≤ 5 điểm khi đầu vào lệch 3% | 92,5% | 70% | 77,5% |

Cổng học: log-likelihood −0,3925 → −0,3676, thắng 7/8 quý giữ lại, được chấp nhận.

Ước lượng học được so với thế giới ẩn:

| | Học được | Thế giới ẩn |
|---|---|---|
| Oakline (logit) | −0,514 | −1,2 |
| Hệ số giao hàng | 0,81 | 0,8 |

Bộ học cũng đẩy Kyoto (+0,53) và Shenzhen (+0,36) lên, trong khi giá trị thật là 0. Lý do: giả định "buyer chậm cả quý" làm giảm xác suất của cả những buyer gần như luôn trả đúng hạn, nên bộ học bù ngược lại.

**Đọc kết quả cho trung thực:**
1. Phần lớn cải thiện đến từ **lập kế hoạch cho đường xấu** (A → B), với chi phí gấp khoảng 4 lần. Đó là đánh đổi thật, không phải lợi ích miễn phí.
2. Học chủ yếu làm **xác suất planner nói ra gần với thực tế hơn** (tự tin quá mức giảm từ 19 xuống 9 điểm). Tỷ lệ thành công tăng rất ít, vì tập kế hoạch bị giới hạn 3 hồ sơ.
3. Workflow cố định có 6 vi phạm: ở vài quý nó cầm cố hóa đơn mà quy tắc mới không cho phép.
4. Độ ổn định còn vừa phải. Từ bản v4, khi lập lại kế hoạch, Core giữ kế hoạch đang dùng nếu phương án mới chỉ hơn trong mức nhiễu mô phỏng (2 sai số chuẩn) và đắt hơn không quá 10%. Nhờ vậy, planner có học tăng từ 68% lên 78%. Khi đổi seed ngẫu nhiên ở mục tiêu 85–95%, các phương án gần bằng nhau vẫn có thể đổi chỗ. Đây là giới hạn của mô phỏng 1.000 đường.
5. Chưa ca nào đạt 90% trong thế giới ẩn. Với dữ liệu này, chỉ tài trợ thôi là không đủ.

## 6. Định vị nghiên cứu (chưa phải tuyên bố novelty)

Câu hỏi kỹ thuật cụ thể: *một planner nội bộ có thể phối hợp các agent tài chính, chấm kế hoạch trên mô phỏng và học có kiểm soát từ kết quả để cải thiện quyết định thanh khoản cho SME, mà vẫn giữ tính toán xác định và kiểm toán được không?*

Bản này cho bằng chứng **trong mô phỏng do nhóm viết**. Trước khi viết "đóng góp mới" trong bài thi, nhóm cần tự đọc ProFinAgent (ICML 2026), TS-Agent (ICAIF 2025) và các công trình về learning from interaction, rồi chỉ ra chính xác phần nào khác. Các paper này t chưa kiểm chứng được từ đây.

## 6b. Sự kiện và Hộp thư Giám đốc (v4)

Đây là bản gọn của ý "Digital Twin + chỉ làm phiền sếp khi cần quyết định".

- **Danh mục sự kiện cố định**, không nhận văn bản tự do:
  - Oakline trả mọi hóa đơn trễ 30 ngày;
  - Harbor hủy đơn SO-2303;
  - nhà cung cấp đòi cọc 40%;
  - Kyoto trả sớm INV-1033.

  Khi chạy thật, sự kiện sẽ đến từ sao kê ngân hàng, ERP và bộ đọc email. Trong demo chúng là nút bấm.
- **Sự kiện chỉ cập nhật một bản sao (twin)** của đầu vào, không đụng vào hồ sơ thật. Core lập lại kế hoạch ngay, có biết kế hoạch đang dùng.
- **Quy tắc báo động:** chỉ gửi vào Hộp thư Giám đốc khi gặp một trong ba trường hợp:
  1. kế hoạch đề xuất thay đổi, cần hồ sơ hoặc phê duyệt mới;
  2. kế hoạch đang dùng tụt quá 5 điểm dưới mục tiêu và không phương án nào cứu được;
  3. tuần âm đầu tiên bị kéo sớm hơn.

  Mọi trường hợp khác vào bản tóm tắt.
- **Giám đốc quyết định** "Chấp nhận kế hoạch mới" hoặc "Giữ kế hoạch hiện tại". Đây là thao tác L2 có tên người, được ghi vào nhật ký. Kế toán bấm thì bị từ chối (ca CORE-04).
- **Ví dụ trên ca demo:**
  - Kyoto trả sớm và nhà cung cấp tăng cọc: vào tóm tắt. Kế hoạch đang dùng vẫn ổn, giữ nguyên.
  - Oakline trễ 30 ngày: vào hộp thư. Tuần âm đầu tiên kéo từ 7 về 4, kế hoạch đang dùng tụt từ 85% xuống khoảng 10%, phương án tốt nhất chỉ còn khoảng 18%. Đây là quyết định ngoài tài trợ, và hệ thống nói rõ điều đó.

Mỗi phương án đã chấm giờ có một dòng giải thích vì sao không được chọn: thiếu mục tiêu, đắt hơn, nhiều hồ sơ hơn, hay phụ thuộc nhà cung cấp. Trang cũng hiện tổng số phương án đã chấm, bị từ chối và đạt mục tiêu.

## 7. Còn thiếu / hướng tiếp theo

- Soạn các hồ sơ bổ sung ngay từ kế hoạch của Core. Hiện mỗi ca chỉ một hồ sơ; các hồ sơ thêm chỉ được liệt kê.
- Thêm hành động không tài trợ: đẩy thu nợ có mục tiêu, giãn chi, chiết khấu thanh toán sớm có điều kiện. Phải có mô hình hiệu quả thì mới đưa vào.
- Tăng độ ổn định bằng tiêu chí phá hòa và chi phí đổi kế hoạch.
- Contextual bandit hoặc học chính sách: chỉ làm khi có kết quả thật đủ nhiều, và vẫn qua cổng offline và người duyệt như hiện tại.
- Thay giả định "buyer chậm cả quý" bằng ước lượng từ dữ liệu nhiều doanh nghiệp, khi có.

## 8. Cách demo trong 2 phút (v6)

1. Đăng nhập **Trần Văn Minh** (Giám đốc) → vào thẳng **Trung tâm quyết định**. Chỉ 4 ô KPI (có nhãn *Mô phỏng*) và biểu đồ "Xác suất số dư âm theo tuần": đường đề xuất đậm, "Không làm gì" xám, ghi chú tuần rủi ro cao nhất.
2. Mở **Đề xuất này được đưa ra như thế nào** (Decision Trace), bước 4: phương án, 2 phương án thua và lý do, CVaR 95%, và **vì sao chưa đạt 90%** (giấy chứng nhận khả thi: nới từng giới hạn trên cùng bộ kịch bản; chỉ để chẩn đoán).
3. *Giả lập sự kiện*: **Kyoto trả sớm INV-1033** (vào tóm tắt, không làm phiền), rồi **Oakline trả trễ 30 ngày** (vào Hộp thư Giám đốc, mức HIGH, có hạn chót). Bấm **Chấp nhận kế hoạch mới** (L2, ghi tên).
4. Tab **Bằng chứng & mô hình**: benchmark planner (A/B/C, CVaR, ablation, calibration, vì sao 0/40 đạt 90%) và benchmark vận hành (100 sự kiện → 7 lần báo Giám đốc, 0 bỏ sót). Nút **Cho quý này diễn ra (mô phỏng)** → đề xuất cập nhật mô hình; kế toán đề xuất, Giám đốc mới được duyệt (CORE-02).
5. Menu **Hệ thống › Cài đặt**: chế độ Đơn giản (ẩn tab phân tích), cỡ chữ, tương phản; chính sách tổ chức chỉ xem. Cuối menu: **Đăng xuất** (hủy phiên trên server).

## 9. Giấy chứng nhận khả thi và CVaR (v6)

- **Tiền cần thêm từ tuần 1** để đạt mục tiêu có công thức đóng: phân vị (1 − α) của (ngưỡng − số dư thấp nhất khi không làm gì). Không khoản tài trợ nào đến muộn hơn, tốn phí hoặc phải trả trong 13 tuần làm tốt hơn với cùng số tiền.
- 4 phép thử, mỗi phép nới **một** giới hạn: thêm hồ sơ nhưng vẫn dưới trần vay; tiền miễn phí bằng trần vay; dùng mọi nguồn hợp lệ; rút vốn từ tuần 1. Kết luận: `REACHABLE`, `LIMITED_BY_POLICY_OR_SOURCES` hoặc `NOT_REACHABLE_WITH_FINANCING`.
- Benchmark: tiền miễn phí bằng trần vay đạt 90% ở 40/40 quý → thiếu không do thiếu tiền, mà do ≤ 3 hồ sơ, khoản phải trả trong kỳ và thời điểm. Nới giới hạn là việc của người làm chính sách.
- **CVaR 95%** = thiếu hụt trung bình trong 5% kịch bản xấu nhất. Chỉ báo cáo, không đưa vào hàm mục tiêu vì hệ số đánh đổi phải do chính sách tín dụng đặt.
- Đã thử thêm tuần rút vốn sớm hơn (`DRAW_LEAD`): +0,5 đến +1,5 điểm, tốn thêm khoảng 60% thời gian → không bật.
