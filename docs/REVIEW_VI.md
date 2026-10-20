# CashBridge: đánh giá code, những gì đã sửa, và nên làm gì tiếp

Ngày 19/10/2026, cập nhật lần 2 cùng ngày (mục 3b). Phạm vi: toàn bộ mã nguồn CashBridge (Python + UI), đối chiếu với bản phân tích chiến lược trước đó, 5 repo tham khảo (Helm, invoice-to-pay, closegate, Kaching, notebook EDA) và trang GreenLoop `index.html`. Mọi số liệu dưới đây lấy từ chạy code thật trên dữ liệu SYNTHETIC trong repo.

## 1. Kết luận ngắn

Giữ Topic E và giữ phần lõi. Bản phân tích chiến lược trước đó đúng hướng (một workflow liền mạch, bằng chứng gắn với từng con số, độ tin cậy đo được). Đọc code kỹ thì có thêm ba vấn đề mà bản đó chưa thấy, và một trong số đó giám khảo sẽ thấy ngay trên biểu đồ:

1. **Gói tài trợ chỉ "lấp" được tuần 7.** Khoản factoring USD 48.000 phủ thiếu hụt tuần 7 (USD 43.882), nhưng tuần 8 số dư lại âm (−USD 27.458 sau khi nhận tiền) và tới tuần 13 vẫn thiếu khoảng USD 152.500. Lý do: dự báo 13 tuần chỉ có hóa đơn đang mở, không có doanh số mới, trong khi chi phí cố định USD 38.000/tuần chạy đều. Thư đề nghị vay cũ nói "covers the shortfall", dễ bị bắt bẻ.
2. **Gần như toàn bộ API SME không có xác thực.** `/api/approve`, `/api/prepare_pack`, `/api/reset_demo`… ai biết URL cũng gọi được. Khi deploy công khai, người lạ có thể reset demo giữa buổi chấm. Nút chọn "Bank" trên UI chỉ là giao diện.
3. **Không có phân tách người lập và người duyệt.** Ai có mã OTP là duyệt được, kể cả người vừa lập hồ sơ.

Ba vấn đề trên đã được sửa (mục 3). Ở vòng 2, dữ liệu tổng hợp đã được hiệu chỉnh cho khớp nhau, và Lõi điều phối (Intelligence Core) được thêm vào (mục 3b). Vấn đề 1 giờ có câu trả lời mạnh hơn: kịch bản cơ sở được phủ hết 13 tuần, còn rủi ro ở các quý xấu được đo bằng mô phỏng.

## 2. Phát hiện chi tiết từ code

| # | Phát hiện | Mức độ | File | Trạng thái |
|---|---|---|---|---|
| 1 | Forecast chỉ gồm hóa đơn mở; sau tuần 7 số dư tiếp tục giảm tới −USD 151.195 (tuần 13). Gói factoring không giữ được số dư dương sau tuần 7 | Cao (Task completion) | `core/forecasting_engine.py`, `agents/coordinator.py` | Đã sửa (vòng 2): dữ liệu khớp nhau, thêm đơn hàng đã xác nhận; khoản ứng giữ tuần 7–13 không âm |
| 2 | Ba nguồn dữ liệu tổng hợp không khớp nhau: doanh thu sổ cái USD 4,62 triệu/năm; lịch sử thanh toán ~USD 88k/tháng (~1,05 triệu/năm); `financial_analytics.json` ~USD 330k/tháng; chi phí cố định USD 38k/tuần (~1,98 triệu/năm) | Cao (giám khảo tinh ý sẽ hỏi) | `data/sandbox_inputs/*.json` | Đã sửa (vòng 2): doanh thu 4,62 triệu, phải thu 948 nghìn (DSO 75), lịch sử 4,4 triệu, chi phí khớp file phân tích |
| 3 | Route SME không xác thực; reset demo công khai | Cao (Security 30%) | `api/main.py` | Đã sửa: phiên ký HMAC, phân quyền, tenant |
| 4 | Không có SoD (preparer = approver được) | Cao | `agents/coordinator.py` | Đã sửa ở 2 lớp |
| 5 | OTP secret công khai làm giá trị mặc định khi thiếu biến môi trường, không có chế độ production | Trung bình | `config/settings.py` | Đã sửa: `CASHBRIDGE_ENV=production` từ chối khởi động |
| 6 | Test có sẵn bị fail (`Vary` header do CORS middleware thêm `Origin`) | Thấp | `tests/test_policy_security.py` | Đã sửa |
| 7 | `.gitignore` bỏ `DECISIONS.md` và `buildplan.md`, nhưng README trỏ tới chúng: đẩy lên GitHub là mất | Trung bình | `.gitignore` | Đã sửa |
| 8 | Hai UI song song (React chưa build được + bản fallback), README mô tả lẫn lộn | Trung bình (Interaction) | `ui/web/` | Thay bằng 1 UI mới, có landing và 2 cổng |
| 9 | Mô hình xác suất trả đúng hạn chỉ có 36 bản ghi. Backtest walk-forward: Brier 0,201 so với 0,214 của mức cơ sở (tốt hơn 6,3%, n=18) | Trung bình | `agents/buyer_risk_agent.py` | Vòng 2: lịch sử 185 hóa đơn, Brier 0,091 so với 0,146 (tốt hơn 37,8%, n=167). Vẫn là dữ liệu tổng hợp: đừng claim "ML dự báo chính xác" |
| 10 | "LLM tool planning disabled": an toàn nhưng thiếu tính agent | Trung bình (Innovation) | `agents/decision_copilot.py` | Thêm Autopilot có planner được kiểm soát |
| 11 | Dockerfile Python 3.11 với numpy 2.5; không nhận `PORT` | Thấp | `Dockerfile` | Đã chuyển 3.12, nhận `PORT` |
| 12 | Thiếu Tesseract thì báo "Invalid image file" (sai nguyên nhân) | Thấp | `contracts/extraction.py` | Báo đúng lỗi |
| 13 | Bộ phụ thuộc ~470 MB (scikit-learn + scipy + PyMuPDF), vượt giới hạn hàm serverless | Chặn deploy Vercel | `requirements.txt` | Tách bản gọn ~155 MB, có bộ giải NumPy thay scikit-learn |

## 3. Những gì đã làm trong bản này

**Bảo mật và tuân thủ (30%)**
- `security/auth.py`: đăng nhập, token ký HMAC-SHA256 (8 giờ, thu hồi được khi đăng xuất), giới hạn đăng nhập sai, 3 vai trò: `sme_accountant` (lập), `sme_director` (duyệt), `bank_reviewer` (thẩm định). Mọi route kiểm tra quyền và tenant ở máy chủ.
- Phân tách người lập / người duyệt ở 2 lớp: ma trận quyền và `Coordinator.approve(approver=...)`. Lệnh tự duyệt bị từ chối trước khi kiểm tra OTP nên không "đốt" mã.
- `config/runtime_mode.py`: chế độ `production` từ chối khởi động nếu dùng OTP demo, thiếu session secret hoặc chưa cấu hình tài khoản; tắt đăng nhập demo, reset và các màn trình diễn giả mạo.
- Header bảo mật (CSP `self`, nosniff, chống nhúng iframe), CORS cấu hình được.

**Hoàn thành tác vụ (40%)**
- `agents/autopilot.py`: agent 6 bước `analyze_cash_gap → verify_receivables → compare_funding_options → stress_test → prepare_funding_pack → request_approval`. Agent chọn bước tiếp theo nhưng chỉ trong bảng chuyển trạng thái cho phép; planner bị "chiếm quyền" (đề xuất `transfer_funds`, bỏ qua bước xác minh…) bị từ chối và ghi nhật ký.
- `core/funding_coverage.py`: kiểm tra phương án có giữ số dư dương sau khi nhận tiền và trả nợ không. Đây là chỗ agent "biết khi nào không nên tuyên bố đã xong".
- Sổ bằng chứng: mỗi con số mang nhãn `VERIFIED / CALCULATED / MODEL_ESTIMATE / ASSUMPTION / NEEDS_HUMAN / NOT_VERIFIABLE_HERE`. Kiểm tra tài trợ trùng ở ngân hàng khác và KYC người mua luôn là `NOT_VERIFIABLE_HERE`.
- Kết thúc đúng trong cả trường hợp nên dừng: không thiếu tiền thì `MONITOR`; không hóa đơn nào qua 3-way match thì `HUMAN_REVIEW_REQUIRED`; hóa đơn tốt nhất đã được tài trợ thì chọn hóa đơn khác (INV-1037), không cầm cố lại.

**Đổi mới và tương tác (30%)**
- Cổng ngân hàng thật sự: chỉ thấy hồ sơ Giám đốc đã phát hành bằng OTP; tự tính lại hash chứng từ, hash gói, hash hành động OTP, kiểm tra SoD và cả hai chuỗi nhật ký; ghi quyết định có lý do. Giám đốc có thể trả hồ sơ, kế toán làm lại.
- UI mới: landing với biểu đồ dòng tiền sống, modal đăng nhập 2 phía (SME | Bank) có tài khoản demo một chạm như GreenLoop (tên Việt / Anh / Trung), trang Tổng quan kiểu dashboard (thẻ KPI, cột số dư 13 tuần, donut tập trung khách hàng, thanh lãi suất các phương án, thanh nguyên nhân thiếu hụt, donut đối chiếu 3 bên), nút "Xem với vai trò" để đổi người dùng một chạm, 3 ngôn ngữ EN / VI / 中文, giao diện sáng/tối theo bảng màu graphite + vàng của dashboard cũ.

**Độ tin cậy đo được**
- `make trust` chạy `eval/trust_scorecard.py`: 24 ca tấn công (24/24 xử lý đúng, gồm 4 ca của Lõi điều phối), 5 kịch bản agent (5/5), backtest mô hình thanh toán, tóm tắt benchmark planner. Kết quả ở `data/execution_evidence/trust_scorecard.md`.
- Test: từ 1 test fail và ~420 test, nay toàn bộ pass với 4 file test mới (auth/RBAC, Autopilot, cổng ngân hàng, scorecard).

## 3b. Vòng 2: dữ liệu khớp nhau và Lõi điều phối

**Dữ liệu (vấn đề 1 và 2)**
- Lấy doanh thu sổ cái USD 4,62 triệu (VND 120 tỷ) làm mốc. Các nguồn khác được kéo về mốc này:
  - Lịch sử thanh toán: 185 hóa đơn, khoảng 4,4 triệu. Harbor Living là buyer mới nên cố ý không có lịch sử.
  - Chi phí: cố định USD 63.500/tuần, lương cuối tháng 42.000, khớp với file phân tích theo tháng.
  - Phải thu: 948 nghìn (DSO 75), khớp sổ cái và bảng cân đối.
- Dự báo giờ tính thêm **đơn hàng đã xác nhận nhưng chưa xuất hóa đơn**, ở mức 90% khả năng giao hàng. Các đơn này không bao giờ được thế chấp.
- Kết quả: tuần 7 vẫn thiếu, USD 42.832. Khoản ứng USD 48.000 giữ mọi tuần từ 7 đến 13 không âm. Câu chuyện demo giữ nguyên.

**Lõi điều phối (`agents/intelligence_core.py`, trang "Lõi điều phối")**
- Bộ mô phỏng 2.000 quý. Một khoản ứng chỉ giữ không âm khoảng 28% số quý. Kế hoạch của Core (vay cầu nối + factoring INV-1030 + INV-1053, giải ngân tuần 2) đạt khoảng 87%. Mục tiêu đặt là 90%, nên Core báo thẳng là chưa đạt.
- Planner chỉ chọn trong tập hành động đóng, tối đa 3 hồ sơ. Một bộ kiểm tra độc lập từ chối các trường hợp sau:
  - thế chấp đơn hàng;
  - hóa đơn chưa xác minh hoặc có xác suất trả trễ cao;
  - vay quá mức cần;
  - hành động lạ.
- Học có kiểm soát:
  - Bộ nhớ ca được băm nối chuỗi.
  - Mỗi lần trượt mục tiêu được quy về một nguyên nhân.
  - Mô hình mới phải thắng bản đang dùng trên các quý giữ lại để kiểm tra.
  - Người kích hoạt phải khác người đề xuất.
- Chi tiết, số benchmark và cách trả lời giám khảo: [`INTELLIGENCE_CORE_VI.md`](INTELLIGENCE_CORE_VI.md).

## 3c. Vòng 3 (v4): xử lý 4 bản góp ý

| Góp ý | Quyết định | Đã làm / lý do |
|---|---|---|
| Kiểm thử automation chưa đủ (P0) | Làm | Có test cho cả 11 loại tác vụ: không loại nào gửi email, hoàn tiền hay ghi sổ; dữ liệu sai bị từ chối; hàng đợi idempotent. Test này **bắt được một lỗi thật**: `cash_alert` từ chối số dư âm, tức hỏng đúng lúc cần cảnh báo. Đã sửa. |
| Không chạy hết được bộ test | Làm | Thêm `make test-fast` (khoảng 1 phút). Bộ đầy đủ khoảng 2 phút, 491 test pass. |
| Xác minh benchmark (P0) | Làm | Test chạy benchmark nhỏ 2 lần phải ra kết quả giống hệt nhau, và kiểm tra file benchmark đã commit khớp với số từng ca. |
| Hiện planner đã cân nhắc gì và vì sao (P1) | Làm | Mỗi phương án có một dòng lý do; trang hiện tổng số phương án đã chấm, bị từ chối và đạt mục tiêu. |
| Độ ổn định chỉ 65–68% | Làm một phần | Giữ kế hoạch đang dùng nếu chênh lệch chỉ là nhiễu. Planner có học: 68% → 78%. Vẫn thấp hơn workflow cố định; ghi rõ là giới hạn. |
| Cảnh báo chủ động, Executive Digest (P1); Digital Twin; "chỉ làm phiền sếp khi cần" | Làm bản gọn | Sự kiện → lập lại kế hoạch → Hộp thư Giám đốc hoặc tóm tắt (mục 6b trong `INTELLIGENCE_CORE_VI.md`). Không phải digital twin đầy đủ: chưa nối với ERP hay ngân hàng thật. |
| Decision Memory | Đã có từ v3 | Bộ nhớ ca, quy nguyên nhân, học qua cổng duyệt. |
| Financing Passport, Evidence layer | Đã có phần lõi | Hồ sơ có băm, ngân hàng tự xác minh, sổ bằng chứng gắn nguồn. Chưa có chữ ký số, chia sẻ chọn lọc, hay bấm vào con số trên dashboard để truy nguồn. |
| Self-healing (hoãn chi, thu nợ sớm) | Chưa làm | Cần mô hình hiệu quả cho từng đòn bẩy. Nếu thêm số giả định chưa kiểm chứng, Core sẽ luôn chọn "hoãn chi" vì chi phí bằng 0. |
| Fraud knowledge graph | Không làm | Không kịp làm cho chắc trước hạn nộp. |
| LendingClub, SBA, Polish, CORD, DocILE, IEEE-CIS, CFPB… | Không làm | (1) Máy này bị chặn tải từ SBA, Zenodo, UCI, HuggingFace. (2) Các bộ này dự báo thứ khác: vỡ nợ người vay cá nhân Mỹ, phá sản công ty Ba Lan. Mô hình của CashBridge dự báo *buyer có trả hóa đơn đúng hạn không*. (3) Ghép vào sát hạn nộp chỉ tạo ra con số không kiểm chứng được. Nếu sau cuộc thi muốn làm, SBA 7(a) là ứng viên duy nhất hợp lý, dùng làm mô hình tham chiếu phía ngân hàng và ghi rõ là dữ liệu Mỹ. |
| Tích hợp email, lịch, ERP, payment sandbox (P2) | Không làm | Không có kết nối, và ngoài phạm vi Topic E lúc này. |
| Deploy cloud (P0) | Nhóm tự làm | Cần tài khoản Render hoặc Vercel của nhóm; các bước có trong `DEPLOY_VI.md`. |

Lưu ý khi pitch:
- Không nói "tự xử lý cả doanh nghiệp 24/7". Phần CSKH, hoàn tiền, email, nhắc việc chỉ tạo bản nháp và chờ người duyệt.
- Điểm 88/100 trong bản góp ý là ước lượng, không phải điểm chính thức.

## 3d. Vòng 4 (v5): góp ý về giao diện

| Góp ý | Quyết định | Đã làm / lý do |
|---|---|---|
| Trang Lõi điều phối quá dày, Giám đốc khó đọc | Làm | Tách 3 tab: *Quyết định* / *Phân tích* / *Bằng chứng & mô hình*. Không xóa gì. Tab Quyết định có câu tiêu đề, 4 KPI, Hộp thư Giám đốc, kế hoạch đề xuất kèm 2 lý do, và 1 biểu đồ. |
| Trang chủ theo vai trò | Làm | Giám đốc vào Trung tâm quyết định, kế toán vào Tổng quan có hàng ô việc, ngân hàng vào hồ sơ đến. Quyền vẫn do server kiểm, không dựa vào menu. |
| Hộp thư có ưu tiên, gom cảnh báo | Làm | Điểm ưu tiên = thiệt hại × độ chắc chắn ÷ số tuần còn lại; có hạn chót. Việc đã quyết và bản tóm tắt được thu gọn. |
| Từ chối truy cập phải được ghi lại | Làm | Mọi 401/403 vào chuỗi nhật ký băm, kèm người, vai trò và tổ chức (ca EVID-03). |
| Source React không khớp giao diện demo | Đúng, và nặng hơn góp ý nói | `make ui` sẽ ghi đè giao diện thật bằng bản React cũ. Đã gỡ toàn bộ project React và lệnh `make ui`; có test chặn việc chúng quay lại. Góp ý "React dùng state `sme \| bank`" là đọc code cũ đó; UI thật dùng vai trò từ phiên đăng nhập. |
| Sau khi có sự kiện, KPI không khớp | Sửa | Trung tâm quyết định luôn tính trên trạng thái hiện tại (hồ sơ thật + các sự kiện). |
| Ảnh mẫu (dashboard tài chính tối) | Học bố cục, không chép | Ô việc chờ có số đếm, badge trên menu. Giữ bảng màu graphite + vàng nhóm đã chọn, không đổi sang emerald. |
| What-if tương tác | Đã có | Thanh trượt ở *Dự báo dòng tiền* (thu chậm, cọc, thuế quan, tỷ giá), tính lại bằng engine. Tab Phân tích có nút dẫn tới. |
| Thêm vai trò Auditor, CSKH, nhân viên; command palette; global search | Không làm | Backend chưa có quyền tương ứng; thêm menu không có quyền thật chỉ là giao diện. |
| Benchmark vận hành (thời gian xử lý, số lần làm phiền sếp) | Một phần | Mỗi sự kiện ghi thời gian từ lúc có sự kiện tới lúc có đề xuất (khoảng 0,5 giây), và số sự kiện so với số cảnh báo tới Giám đốc. Chưa có benchmark so với quy trình thủ công. |

## 3e. Vòng 5 (v6): Decision Trace, benchmark vận hành, cài đặt, nghiên cứu, roadmap 100 điểm

| Góp ý | Quyết định | Đã làm / lý do |
|---|---|---|
| Bản Premium (charcoal–emerald, menu theo vai trò) | Giữ | Đây là giao diện nhóm chọn; v6 xây trên bản này. Thay cho ghi chú ở 3d về bảng màu graphite + vàng. |
| Decision Trace (vì sao ra đề xuất này) | Làm | 5 bước dựng lại từ đúng lần chạy đang hiển thị: rủi ro → chứng từ → kịch bản → đề xuất (kèm 2 phương án thua và lý do) → phê duyệt. |
| Benchmark vận hành (100 sự kiện) | Làm | Báo Giám đốc 100 / 19 / **7** lần (báo mọi sự kiện / theo số tiền / CashBridge), bỏ sót 0 / 1 / 0. Lần chạy đầu báo cả tin tốt (khách trả sớm) nên đã sửa luật: chỉ báo khi phương án đang áp dụng xấu đi hoặc không dùng được nữa. |
| Văn phong "giống AI", số liệu mô phỏng trông như thật | Làm | Viết lại các câu dài dịch từ tiếng Anh; thêm nhãn *Mô phỏng*; test nội dung (đủ 3 ngôn ngữ, placeholder khớp, cấm cụm sáo rỗng). |
| Học logic từ `index.html` mẫu: cài đặt, nút đăng xuất | Làm | Cài đặt thành **trang trong menu** (Hệ thống › Cài đặt) cho mọi vai trò; khối **Tài khoản** ở cuối menu: về trang giới thiệu, đổi tài khoản, đăng xuất, thẻ người dùng. Tùy chọn hiển thị áp dụng ngay, lưu trên máy; chính sách tổ chức chỉ xem, lấy từ server. Đăng xuất hủy phiên trên server rồi báo ở trang chủ. |
| Chỉnh biểu đồ rủi ro | Làm | Đường đề xuất nổi bật (dày 3px), "Không làm gì" xám nét đứt, "Một khoản ứng" giữ màu cam nhưng nhạt hơn; nhãn ở cuối đường; đánh dấu tuần rủi ro cao nhất; tooltip có chênh lệch; ghi "Càng thấp càng tốt"; chế độ Đơn giản chỉ còn 2 đường. |
| Tooltip bị kẹt trên màn hình (ảnh chụp dài) | Sửa lỗi thật | Khi phần tử bị vẽ lại, tooltip không nhận `pointerout` nên đứng yên. Nay ẩn khi click, cuộn, đổi trang/ngôn ngữ/giao diện. Thanh trên và menu nằm giữa ảnh là do công cụ chụp cuộn ghép ảnh (thanh trên dính đầu trang), không phải lỗi bố cục. |
| Paper nghiên cứu + `RESEARCH_AND_EVALUATION.md` | Làm | Nối từng paper với module, baseline, số đo. Trích dẫn đã kiểm tra trên trang nhà xuất bản; 1 nguồn (Schmid) không mở được nên không trích. Thêm CVaR 95%. Không làm XGBoost/SHAP, TFT: không có dữ liệu thật để huấn luyện và kiểm chứng. |
| Roadmap 100/100: planner 0/40 quý đạt 90% | Làm phần chứng minh | **Giấy chứng nhận khả thi**: nếu có tiền miễn phí bằng trần vay từ tuần 1 thì 40/40 quý đạt 90%. Vậy thiếu không phải vì thiếu tiền mà vì giới hạn ≤ 3 hồ sơ, khoản phải trả trong 13 tuần và thời điểm giải ngân. Nới giới hạn là quyết định chính sách của con người; hệ thống chỉ chỉ ra. |
| Calibration, ablation | Làm | Trong chính mô hình của planner, tự tin quá mức chỉ −1,9 điểm (Monte Carlo trung thực); chênh lệch ở thế giới ẩn là lỗi mô hình, learning giảm một nửa. Ablation: bỏ "biết phương án đang áp dụng" → giữ phương án 57,5% thay vì 77,5%; bỏ kiểm tra phương án đang áp dụng → 11 cảnh báo thay vì 7. |
| Tách claim 3 tầng | Làm | Đã làm & kiểm chứng / sandbox / roadmap trong README và `RESEARCH_AND_EVALUATION.md`. |
| Dữ liệu thật (SBA, DocILE…), OCR định vị, cloud worker có retry/DLQ, usability test | Không làm trong hạn | Ghi là roadmap. Làm vội mà không kiểm chứng được thì mất điểm hơn được. |
| Chỉnh sửa theo ngữ cảnh (sửa số tại chỗ, có lịch sử) | Chưa làm | Mỗi số trọng yếu đã có nguồn, phép tính, hash; sửa tại chỗ cần quy trình duyệt riêng để không phá khóa số. |

## 4. Học gì từ các repo tham khảo (và giới hạn license)

| Repo | License | Lấy gì | Không lấy |
|---|---|---|---|
| Helm Finance Agent | Không có file LICENSE | Ý tưởng: một điểm nghẽn duy nhất cho mọi hành động ra ngoài, hàng đợi duyệt, trích dẫn nguồn → hand-off của Autopilot | Không chép code |
| closegate | Apache-2.0 | Phân tầng theo khả năng đảo ngược, SoD, harness đánh giá nhiều chiều → SoD 2 lớp + trust scorecard | Không cần MCP server cho demo |
| invoice-to-pay-agent | MIT | Định tuyến ngoại lệ, kiểm tra trùng mờ (cùng bên bán + số tiền + ngày) | Đề xuất thêm ở P1 |
| Kaching (cùng cuộc thi) | Chỉ để chấm thi, cấm sao chép | So sánh định vị: họ có Financing Readiness Index và PIN 2 pha; CashBridge khác ở chỗ ngân hàng tự xác minh hash và agent kiểm tra độ phủ từng tuần | Không dùng code hay cấu trúc điểm |
| Notebook EDA | Không rõ | Khung Descriptive → Diagnostic → Predictive → Prescriptive | Gợi ý cho tab Financial health (P1) |
| GreenLoop `index.html` | Của nhóm | Landing + modal đăng nhập có tài khoản demo theo vai trò | Viết lại theo nhận diện CashBridge |

## 5. Nên làm gì tiếp (theo thứ tự)

**P0, trước khi nộp**
1. ~~Hiệu chỉnh dữ liệu seed~~: đã làm ở vòng 2 (mục 3b). Nếu đổi thêm số, chạy `make seed story eval bench trust` rồi cập nhật README/slide.
2. **Deploy 2 nơi**: Render (Docker, 1 tiến trình, ổn định cho buổi chấm) và Vercel (preview nhanh). Đặt `CASHBRIDGE_SESSION_SECRET`. Xem `docs/DEPLOY_VI.md`.
3. **Quay video 3 phút** theo đúng flow trong README (Nguyễn Thị Lan chạy Autopilot → Chen Wei 陈伟 duyệt OTP → Li Hua 李华 xác minh và quyết định), nhấn vào khung "What it covers, what can still go wrong" và mở trang Lõi điều phối (28% → 87%).

**P1, nếu còn thời gian**
4. ~~Kế hoạch tài trợ nhiều hóa đơn~~: Lõi điều phối đã đề xuất tổ hợp tới 3 hồ sơ. Còn thiếu: cho kế toán soạn các hồ sơ bổ sung ngay từ kế hoạch (hiện mỗi ca chỉ một hồ sơ).
5. Điểm "sẵn sàng tài trợ" có giải thích từng thành phần, tính từ bằng chứng đã xác minh (khác cách của Kaching: điểm phải truy ngược được tới evidence ID).
6. Phát hiện hóa đơn gần trùng (cùng bên mua, số tiền, ngày; số hóa đơn khác) trước khi đăng ký.
7. Tab Financial health theo 4 tầng của notebook EDA.
8. LLM tùy chọn chỉ để diễn giải kết quả Autopilot, đi qua number lock sẵn có; vẫn không được chọn công cụ.

**P2, hướng production**
9. Lưu trạng thái vào SQLite/Postgres để chạy nhiều instance (Vercel hiện mỗi instance một ca demo riêng).
10. OIDC thay tài khoản cấu hình tay; MFA thật cho Giám đốc.
11. Sổ đăng ký hóa đơn dùng chung giữa nhiều bên cho vay (mock 2 lender để demo chống tài trợ trùng thật sự).

## 6. Câu hỏi giám khảo có thể hỏi và cách trả lời

- *"Khoản vay có giải quyết được vấn đề không?"* Trong kịch bản cơ sở thì có: tuần 7 đến 13 không âm. Nhưng trên 2.000 quý mô phỏng, một khoản ứng chỉ giữ được khoảng 28%. Lõi điều phối đề xuất kế hoạch 3 hồ sơ đạt khoảng 87%, chi phí dự kiến khoảng USD 4.400, và nói rõ là chưa đạt mục tiêu 90%. Giám đốc quyết định có thêm hồ sơ hay không.
- *"AI có tự học rồi tự quyết không?"* Không. Nó chỉ học hiệu chỉnh mô hình thế giới, chạy offline. Bản mới phải thắng trên các quý giữ lại và do một người khác duyệt. Giới hạn chính sách không học được. Benchmark: học giảm mức tự tin quá đà từ khoảng 19 xuống khoảng 9 điểm phần trăm, nhưng tăng tỷ lệ thành công rất ít. Chúng tôi nói đúng như vậy.
- *"Agent có tự quyết không?"* Agent chọn bước trong một bảng chuyển trạng thái; nó lập được hồ sơ nhưng không nộp được và không có công cụ chuyển tiền. Có test chứng minh planner bị chiếm quyền vẫn bị chặn.
- *"Làm sao ngân hàng tin hồ sơ?"* Ngân hàng tự tính lại mọi hash từ chứng từ, kiểm tra OTP gắn đúng hành động, người lập khác người duyệt, chuỗi nhật ký nguyên vẹn. Thứ không chứng minh được (tài trợ trùng ở nơi khác, KYC) được ghi rõ là không kiểm được.
- *"Mô hình ML tốt cỡ nào?"* Tốt hơn mức cơ sở 37,8% theo Brier trên 167 dự đoán ngoài mẫu. Đây là dữ liệu tổng hợp do chính chúng tôi sinh ra, nên con số chỉ chứng minh pipeline chạy đúng, không chứng minh độ chính xác ngoài đời. Con số này nằm trong scorecard.

## 7. Giới hạn còn lại (nói thẳng trong pitch)

Dữ liệu tổng hợp; mô hình thế giới của Lõi điều phối và "thế giới kiểm tra ẩn" đều do nhóm viết, nên benchmark chỉ có giá trị trong mô phỏng; bên cho vay, ngân hàng và KYC là mock; sổ đăng ký hóa đơn chỉ trong một cài đặt; chế độ demo dùng mật mã công khai; Vercel chạy nhiều instance nên trạng thái demo không chia sẻ giữa các instance; đây không phải chứng nhận bảo mật production.
