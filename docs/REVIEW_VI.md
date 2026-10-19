# CashBridge: đánh giá code, những gì đã sửa, và nên làm gì tiếp

Ngày 19/10/2026. Phạm vi: toàn bộ mã nguồn CashBridge (Python + UI), đối chiếu với bản phân tích chiến lược trước đó, 5 repo tham khảo (Helm, invoice-to-pay, closegate, Kaching, notebook EDA) và trang GreenLoop `index.html`. Mọi số liệu dưới đây lấy từ chạy code thật trên dữ liệu SYNTHETIC trong repo.

## 1. Kết luận ngắn

Giữ Topic E và giữ phần lõi. Bản phân tích chiến lược trước đó đúng hướng (một workflow liền mạch, bằng chứng gắn với từng con số, độ tin cậy đo được). Đọc code kỹ thì có thêm ba vấn đề mà bản đó chưa thấy, và một trong số đó giám khảo sẽ thấy ngay trên biểu đồ:

1. **Gói tài trợ chỉ "lấp" được tuần 7.** Khoản factoring USD 48.000 phủ thiếu hụt tuần 7 (USD 43.882), nhưng tuần 8 số dư lại âm (−USD 27.458 sau khi nhận tiền) và tới tuần 13 vẫn thiếu khoảng USD 152.500. Lý do: dự báo 13 tuần chỉ có hóa đơn đang mở, không có doanh số mới, trong khi chi phí cố định USD 38.000/tuần chạy đều. Thư đề nghị vay cũ nói "covers the shortfall", dễ bị bắt bẻ.
2. **Gần như toàn bộ API SME không có xác thực.** `/api/approve`, `/api/prepare_pack`, `/api/reset_demo`… ai biết URL cũng gọi được. Khi deploy công khai, người lạ có thể reset demo giữa buổi chấm. Nút chọn "Bank" trên UI chỉ là giao diện.
3. **Không có phân tách người lập và người duyệt.** Ai có mã OTP là duyệt được, kể cả người vừa lập hồ sơ.

Ba vấn đề trên đã được sửa trong bản này (mục 3). Việc còn lại quan trọng nhất là **hiệu chỉnh dữ liệu tổng hợp cho nhất quán** (mục 5, P0), vì đó là quyết định về câu chuyện demo, nên để nhóm quyết.

## 2. Phát hiện chi tiết từ code

| # | Phát hiện | Mức độ | File | Trạng thái |
|---|---|---|---|---|
| 1 | Forecast chỉ gồm hóa đơn mở; sau tuần 7 số dư tiếp tục giảm tới −USD 151.195 (tuần 13). Gói factoring không giữ được số dư dương sau tuần 7 | Cao (Task completion) | `core/forecasting_engine.py`, `agents/coordinator.py` | Agent giờ kiểm tra độ phủ từng tuần và nói thẳng; dữ liệu seed vẫn cần nhóm hiệu chỉnh |
| 2 | Ba nguồn dữ liệu tổng hợp không khớp nhau: doanh thu sổ cái USD 4,62 triệu/năm; lịch sử thanh toán ~USD 88k/tháng (~1,05 triệu/năm); `financial_analytics.json` ~USD 330k/tháng; chi phí cố định USD 38k/tuần (~1,98 triệu/năm) | Cao (giám khảo tinh ý sẽ hỏi) | `data/sandbox_inputs/*.json` | Ghi nhận, đề xuất P0 |
| 3 | Route SME không xác thực; reset demo công khai | Cao (Security 30%) | `api/main.py` | Đã sửa: phiên ký HMAC, phân quyền, tenant |
| 4 | Không có SoD (preparer = approver được) | Cao | `agents/coordinator.py` | Đã sửa ở 2 lớp |
| 5 | OTP secret công khai làm giá trị mặc định khi thiếu biến môi trường, không có chế độ production | Trung bình | `config/settings.py` | Đã sửa: `CASHBRIDGE_ENV=production` từ chối khởi động |
| 6 | Test có sẵn bị fail (`Vary` header do CORS middleware thêm `Origin`) | Thấp | `tests/test_policy_security.py` | Đã sửa |
| 7 | `.gitignore` bỏ `DECISIONS.md` và `buildplan.md`, nhưng README trỏ tới chúng: đẩy lên GitHub là mất | Trung bình | `.gitignore` | Đã sửa |
| 8 | Hai UI song song (React chưa build được + bản fallback), README mô tả lẫn lộn | Trung bình (Interaction) | `ui/web/` | Thay bằng 1 UI mới, có landing và 2 cổng |
| 9 | Mô hình xác suất trả đúng hạn chỉ có 36 bản ghi. Backtest walk-forward: Brier 0,201 so với 0,214 của mức cơ sở (tốt hơn 6,3%, n=18) | Trung bình | `agents/buyer_risk_agent.py` | Đã đo và công bố trung thực; đừng claim "ML dự báo chính xác" |
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
- `make trust` chạy `eval/trust_scorecard.py`: 20 ca tấn công (20/20 xử lý đúng), 5 kịch bản agent (5/5), backtest mô hình thanh toán. Kết quả ở `data/execution_evidence/trust_scorecard.md`.
- Test: từ 1 test fail và ~420 test, nay toàn bộ pass với 4 file test mới (auth/RBAC, Autopilot, cổng ngân hàng, scorecard).

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
1. **Hiệu chỉnh dữ liệu seed** cho 3 nguồn khớp nhau và để sau khoản ứng trước, dòng tiền hồi phục trong 13 tuần. Cách ít đụng nhất: thêm các hóa đơn đã phát hành đến hạn tuần 8–13 cho các buyer ngoài Oakline (giữ tuần 7 và USD 43,9k), hoặc giảm `weekly_fixed_costs_usd` và đưa doanh thu sổ cái về mức của lịch sử thanh toán. Sau đó chạy `make story && make eval && make trust` và cập nhật số trong README/slide. Cần nhóm quyết vì mọi con số trong pitch sẽ đổi.
2. **Deploy 2 nơi**: Render (Docker, 1 tiến trình, ổn định cho buổi chấm) và Vercel (preview nhanh). Đặt `CASHBRIDGE_SESSION_SECRET`. Xem `docs/DEPLOY_VI.md`.
3. **Quay video 3 phút** theo đúng flow trong README (Nguyễn Thị Lan chạy Autopilot → Chen Wei 陈伟 duyệt OTP → Li Hua 李华 xác minh và quyết định), nhấn vào khung "What this does not fix".

**P1, nếu còn thời gian**
4. Kế hoạch tài trợ nhiều hóa đơn: agent đề xuất danh mục hóa đơn (INV-1037, INV-1026…) và lịch nhận tiền để phủ tới tuần 13, mỗi hóa đơn vẫn một gói và một lần duyệt.
5. Điểm "sẵn sàng tài trợ" có giải thích từng thành phần, tính từ bằng chứng đã xác minh (khác cách của Kaching: điểm phải truy ngược được tới evidence ID).
6. Phát hiện hóa đơn gần trùng (cùng bên mua, số tiền, ngày; số hóa đơn khác) trước khi đăng ký.
7. Tab Financial health theo 4 tầng của notebook EDA.
8. LLM tùy chọn chỉ để diễn giải kết quả Autopilot, đi qua number lock sẵn có; vẫn không được chọn công cụ.

**P2, hướng production**
9. Lưu trạng thái vào SQLite/Postgres để chạy nhiều instance (Vercel hiện mỗi instance một ca demo riêng).
10. OIDC thay tài khoản cấu hình tay; MFA thật cho Giám đốc.
11. Sổ đăng ký hóa đơn dùng chung giữa nhiều bên cho vay (mock 2 lender để demo chống tài trợ trùng thật sự).

## 6. Câu hỏi giám khảo có thể hỏi và cách trả lời

- *"Khoản vay có giải quyết được vấn đề không?"* Không hoàn toàn, và hệ thống nói điều đó: nó phủ tuần 7, còn thiếu hụt cấu trúc do chi phí vượt thu. Agent đề xuất đòn bẩy không vay (thu nhanh 15 ngày + giảm cọc) và để Giám đốc quyết định phần còn lại. (Sau khi hiệu chỉnh seed ở P0, câu trả lời sẽ mạnh hơn.)
- *"Agent có tự quyết không?"* Agent chọn bước trong một bảng chuyển trạng thái; nó lập được hồ sơ nhưng không nộp được và không có công cụ chuyển tiền. Có test chứng minh planner bị chiếm quyền vẫn bị chặn.
- *"Làm sao ngân hàng tin hồ sơ?"* Ngân hàng tự tính lại mọi hash từ chứng từ, kiểm tra OTP gắn đúng hành động, người lập khác người duyệt, chuỗi nhật ký nguyên vẹn. Thứ không chứng minh được (tài trợ trùng ở nơi khác, KYC) được ghi rõ là không kiểm được.
- *"Mô hình ML tốt cỡ nào?"* Tốt hơn mức cơ sở 6,3% theo Brier trên 18 dự đoán ngoài mẫu: chỉ mang tính tham khảo. Con số này nằm trong scorecard, không giấu.

## 7. Giới hạn còn lại (nói thẳng trong pitch)

Dữ liệu tổng hợp; bên cho vay, ngân hàng và KYC là mock; sổ đăng ký hóa đơn chỉ trong một cài đặt; chế độ demo dùng mật mã công khai; Vercel chạy nhiều instance nên trạng thái demo không chia sẻ giữa các instance; đây không phải chứng nhận bảo mật production.
