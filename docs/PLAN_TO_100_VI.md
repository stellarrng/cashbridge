# CashBridge v9 - Lộ trình hướng tới mức điểm tối đa tại FinTechathon 2026

**Phạm vi:** Track E - SME Finance Copilot. Tiêu chí chính thức trong tài liệu BTC: Task Completion 40%, Security & Compliance 30%, Innovation & Interaction 30%. **Không có bảng điểm con chính thức được cung cấp**, nên không ai có thể xác nhận CashBridge sẽ đạt 100/100 hay bảo đảm giải thưởng. Lộ trình này tối ưu **khả năng chứng minh năng lực prototype**, không yêu cầu chuyển CashBridge thành sản phẩm fintech commercial-ready.

## A. Những gì đã có, không cần xây lại

| Tiêu chí | Điểm mạnh đã có trong v9 | Báo cáo |
|---|---|---|
| Task completion | 20/20 nhiệm vụ evaluation; 5/5 agent outcome; 11/11 step demo, workflow ba vai trò; financial accuracy tests | `data/execution_evidence/eval_report.md`, `reports/full_pytest.txt`, `data/execution_evidence/story_summary.md` |
| Security & compliance | 25/25 adversarial trust cases; OTP; RBAC; data gate; vault encryption; audit; local HTTPS 30/30 | `data/execution_evidence/trust_scorecard.md`, `reports/deploy_verification.md`, `docs/SECURITY_SELF_ASSESSMENT_2026.md` |
| Innovation & interaction | Risk-aware financing; quy trình agent phối hợp người thật; khả năng truy nguồn; 3 ngôn ngữ; responsive; benchmark baseline | `reports/risk_planner.md`, `reports/forecast_backtest.md`, `reports/ops_robustness.md`, `reports/e2e/` |
| User testing | **Nhóm xác nhận đã thực hiện** | Chưa có số liệu/phản hồi ẩn danh trong ZIP. Cần gắn evidence thật, không phải chạy lại mặc định. |

## B. Thứ tự làm để tăng *evidence readiness*, không để thêm tính năng vô ích

### P0 - Khóa bản demo nộp và chứng minh task completion 40/40-ready

1. Chốt đúng **một** phiên bản code và ghi commit/build identifier; màn hình quay video phải đúng bản đó.
2. Quay một video 3-4 phút: phát hiện cash gap -> so sánh các phương án -> Autopilot chuẩn bị hồ sơ -> Director phê duyệt -> lender MOCK yêu cầu/mở chứng từ -> quyết định -> SME nhận kết quả.
3. Đưa ít nhất **một refusal** vào video (sai OTP, accountant không được phê duyệt, hoặc missing source). Cần nhìn thấy hệ thống **không** làm hành động nguy hiểm.
4. Từ checkout sạch, chạy và lưu log `make test-report`, `make e2e`; kiểm tra lệnh start ở README chạy đúng.
5. Không cần gọi API ngân hàng thật, và **không** biến việc giải ngân thành hành động tự động. Đó là rủi ro mới, không phải yêu cầu bắt buộc của prototype.

**Definition of done:** demo chạy liên tục, có bằng chứng nhiệm vụ đã hoàn thành hoặc bị từ chối đúng luật; log có thể tái lập bằng commit tương ứng.

### P0 - Đóng gói bằng chứng security 30/30-ready

1. Dùng `docs/SECURITY_SELF_ASSESSMENT_2026.md` làm security self-assessment, trình bày rõ quyền của accountant / director / mock lender / agent.
2. Cho thấy 2 lỗi bị chặn: quyền sai và dữ liệu/hồ sơ không tin cậy; có kiểm tra trong log hoặc trace.
3. Gắn `reports/deploy_verification.md` và `data/execution_evidence/trust_scorecard.md`; nêu rõ **local production-mode test**, không gọi là certified security hoặc pentest.
4. Nếu demo có public URL, chạy `scripts/deploy_smoke.py` trên URL thật rồi lưu JSON kết quả. Nếu demo chạy offline, dùng local checks đúng phạm vi.

**Definition of done:** mỗi security claim chính có code + test + đầu ra; các hạn chế ghi rõ, không hứa bảo mật tuyệt đối.

### P0 - Đóng gói kết quả user test thật cho Innovation & Interaction 30/30-ready

1. Gom phiếu/recording/notes của **các buổi đã test**, ẩn tên thật và thông tin liên hệ.
2. Ghi participant count thực, vai trò, task đã thực hiện, độc lập hay có hướng dẫn; những chỉ số **thực sự đo** (success, error, time, SEQ, SUS nếu có).
3. Không điền số 0 cho missing observations, không tự tạo người tham gia, không tự tăng completion.
4. Nếu đúng protocol và dữ liệu đủ, tạo `reports/uat_results.csv`, chạy `python eval/uat_summary.py reports/uat_results.csv` để có `reports/uat_summary.md`.
5. Rút ra **hai usability insights thật** kèm màn hình/sửa lỗi tương ứng (hoặc ghi chưa có thay đổi). Tập trung vào hiểu cash gap, giải thích recommendation, khả năng tìm nút approval và nguồn số liệu.

**Definition of done:** judge thấy được người dùng thật đã thử những tác vụ nào, thực hiện được hay không, feedback nào làm thay đổi prototype; không cần có thành tích hoàn hảo.

### P1 - Câu chuyện innovation phải làm rõ *agent* khác dashboard

1. Chọn **1 điểm khác biệt chính**: từ cash data -> risk-aware decision -> controlled action -> lender feedback -> audit, trong một workflow.
2. So sánh công bằng với baseline đơn giản, không cần giả vờ hơn mọi competitor. Dùng: `reports/risk_planner.md` và `reports/ops_robustness.md` với nhãn SIMULATED; `reports/forecast_backtest.md` với nhãn public-data *receipts timing*.
3. Đưa Decision Trace, tình huống agent từ chối và click-to-source lên demo; giảm thuật ngữ không cần thiết.
4. Nói rõ kiến trúc: deterministic financial calculations + bounded specialist agents + human approval. Đây là một lựa chọn **trustworthy AI** chủ động, không phải yếu điểm vì AI không tự duyệt khoản vay.

**Definition of done:** trong 20-30 giây, judge hiểu tại sao đây là một financial participant có giới hạn thẩm quyền thay vì chatbot chỉ trả lời bằng chữ.

### P1 - Final submission hygiene

- `README.md`: lệnh chạy, tài khoản DEMO, giới hạn MOCK/SYNTHETIC, link tới rubric/evidence.
- `docs/FINTECHATHON_2026_SCORECARD.md`: đối chiếu 40/30/30 và giới hạn.
- `docs/SECURITY_SELF_ASSESSMENT_2026.md`: permission tiers, threat scenarios, known risks.
- `reports/BENCHMARKS.md`, `reports/full_pytest.txt`: log/evidence.
- `reports/uat_results.csv`, `reports/uat_summary.md` **nếu số liệu gốc thực sự có**; nếu không, chỉ dùng `reports/UAT_EVIDENCE_STATUS.md` và thành thật nói thiếu logs.
- Deck/video/GitHub/source code/test instructions giữ nguyên logic và số liệu; không còn script v8 nhầm rằng chỉ truyền hash mà không gửi file.

## C. Có thể đạt đủ 100/100 không?

**Có thể tạo một bộ bằng chứng đủ mạnh để tranh điểm tối đa ở từng tiêu chí; không thể bảo đảm BGK sẽ cho tuyệt đối.** Điểm cộng cuối thường đến từ việc demo dễ hiểu, số liệu được đối chiếu, luồng chạy trơn tru và bằng chứng UAT rõ ràng, chứ không phải 10 tính năng bổ sung.

Không nên ưu tiên ngay lúc này: bank integration thật, HSM/KMS, KYC thực tế, blockchain, phân tích tín dụng thật, mở thêm 5 modules. Những việc đó có thể tạo lỗi mới, khó demo và **không xuất hiện như điều kiện bắt buộc** trong rubric ba nhóm mà BTC công bố.

**Mục tiêu thực tế:** đạt "40/40-ready evidence", "30/30-ready security evidence" và "30/30-ready innovation evidence" - nghĩa là có thể chứng minh trọn vẹn nội dung trong prototype và trung thực về mọi giới hạn. Điểm chính thức hoàn toàn do BGK quyết định.
