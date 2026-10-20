# Independent User Acceptance Test (UAT) — giao thức cho 3 vai trò

**Mục đích:** chứng minh người không tham gia phát triển (kế toán SME, giám đốc SME, cán bộ tín dụng) **tự hoàn thành** nhiệm vụ trên CashBridge mà không cần nhóm hướng dẫn. Kết quả UAT là bằng chứng cho tiêu chí Innovation & Interaction; **không được điền số liệu giả**: chưa chạy thì báo cáo ghi "chưa thực hiện".

## 1. Người tham gia

| Vai trò | Số người tối thiểu | Tiêu chí chọn | Không được |
|---|---|---|---|
| Kế toán trưởng (`sme.lan`) | 2–3 | Từng lập báo cáo dòng tiền hoặc hồ sơ vay | Thành viên nhóm, người đã xem demo |
| Giám đốc (`sme.minh`) | 2–3 | Từng duyệt chi hoặc ký hồ sơ vay | như trên |
| Cán bộ tín dụng (`bank.lihua`) | 2–3 | Từng thẩm định hồ sơ doanh nghiệp | như trên |

5 người/vai trò phát hiện phần lớn lỗi usability nghiêm trọng; 2–3 người/vai trò là mức tối thiểu trước ngày nộp.

## 2. Quy tắc phiên test (không hướng dẫn)

1. Người điều phối chỉ đọc **thẻ nhiệm vụ** bên dưới, không chỉ chỗ bấm, không giải thích thuật ngữ.
2. Người tham gia nói to suy nghĩ (think-aloud). Ghi màn hình + âm thanh nếu được đồng ý (xin đồng ý bằng văn bản).
3. Nếu người tham gia bí quá **2 phút**, điều phối viên được gợi ý **một lần** → ghi `assists = 1`, nhiệm vụ **không** tính là "tự hoàn thành".
4. Môi trường: bản demo đã deploy (link Render) hoặc `make run`, dữ liệu SYNTHETIC, ngôn ngữ người tham gia chọn (EN/VI/中文).
5. Reset trước mỗi người: nút "Reset demo" hoặc khởi động lại server.

## 3. Thẻ nhiệm vụ

| ID | Vai trò | Thẻ nhiệm vụ (đọc nguyên văn) | Hoàn thành khi | Lỗi nghiêm trọng |
|---|---|---|---|---|
| A1 | Kế toán | "Công ty sắp thiếu tiền. Hãy tìm tuần nào thiếu và thiếu bao nhiêu." | Nói đúng tuần 7 và khoảng $42.8k | — |
| A2 | Kế toán | "Chuẩn bị hồ sơ xin tài trợ rẻ nhất phù hợp và gửi cho giám đốc duyệt." | Trạng thái *awaiting approval* | Chọn phương án không đủ điều kiện |
| A3 | Kế toán | "Ngân hàng yêu cầu bổ sung vận đơn. Hãy gửi tệp này cho họ." (đưa file mẫu) | Yêu cầu chuyển *submitted* | Gửi nhầm yêu cầu |
| D1 | Giám đốc | "Có hồ sơ chờ anh/chị duyệt. Hãy xem chi phí và rủi ro rồi quyết định." | Duyệt bằng OTP **hoặc** trả lại kèm lý do | Duyệt mà không mở hồ sơ |
| D2 | Giám đốc | "Đối tác yêu cầu không chuyển nhượng hóa đơn này. Hãy rút hồ sơ khỏi ngân hàng." | Trạng thái *withdrawn* | — |
| B1 | Ngân hàng | "Có hồ sơ mới. Hãy kiểm tra tính toàn vẹn của chứng từ." | Chạy Verify, đọc được 6 ✓ + 1 "?" | Bỏ qua kiểm tra |
| B2 | Ngân hàng | "Yêu cầu doanh nghiệp bổ sung vận đơn có chữ ký, rồi chấp nhận tệp họ gửi." | Mở tệp qua CashBridge rồi yêu cầu *accepted* (v9: không mở thì hệ thống từ chối) | Chấp nhận khi chưa mở tệp |
| A4 | Kế toán (v9) | "Ngân hàng hỏi con số 60.000 USD trong hồ sơ lấy từ đâu. Hãy chỉ cho họ chứng từ và dòng chữ." | Mở được nguồn: SCAN-INV-1030, trang 2, dòng "Total Amount" | Chỉ nhầm chứng từ |
| A5 | Kế toán (v9) | "Số trên chứng từ quét sai (thực tế là 59.000 vì có giấy báo có). Hãy đề nghị sửa đúng quy trình." | Có đề nghị sửa *pending*, hồ sơ đã khóa không đổi | Tìm cách sửa trực tiếp số đã khóa |
| D3 | Giám đốc (v9) | "Kế toán đề nghị sửa một số liệu. Xem và quyết định." | Đề nghị *approved* hoặc *rejected* kèm ghi chú | Duyệt mà không xem giá trị gốc |
| B4 | Ngân hàng (v9) | "Trước khi quyết định, hãy kiểm tra số 'Funds requested' được tính thế nào." | Đọc được công thức 60.000 × 80% và nguồn là điều khoản MOCK | Coi báo giá mô phỏng là chào giá thật |
| B3 | Ngân hàng | "Ghi nhận quyết định tín dụng của anh/chị." | Có quyết định + ghi chú | — |

## 4. Đo lường cho mỗi nhiệm vụ

`completed_unaided` (0/1), `time_s` (giây), `errors` (số lần thao tác sai), `assists` (0/1), `critical_error` (0/1), `seq` (Single Ease Question 1–7: "Nhiệm vụ này dễ hay khó?"). Sau phiên: bảng SUS 10 câu (1–5).

Ghi vào `reports/uat_results.csv` theo mẫu `reports/uat_results_TEMPLATE.csv`, rồi chạy:

```bash
python eval/uat_summary.py reports/uat_results.csv     # -> reports/uat_summary.md
```

## 5. Ngưỡng chấp nhận (tự đặt, không phải chuẩn của BTC)

| Chỉ số | Ngưỡng |
|---|---|
| Tỷ lệ tự hoàn thành mỗi nhiệm vụ | ≥ 80% |
| Lỗi nghiêm trọng | 0 |
| SEQ trung vị mỗi nhiệm vụ | ≥ 5 / 7 |
| SUS trung bình mỗi vai trò | ≥ 68 (mức trung bình ngành) |

Nhiệm vụ không đạt → ghi nguyên nhân, sửa giao diện/copy, chạy lại với **người mới** (không dùng lại người đã thấy giao diện).

## 6. Đã tự động hóa được gì (không thay thế UAT)

`tests/e2e/test_browser_flow.py` kiểm tra mọi luồng trên chạy được trên Chromium, không có khóa dịch thô ở 3 ngôn ngữ, không tràn ngang trên điện thoại 375 px, và **hành động tiếp theo của từng vai trò nằm ngay trên màn hình đầu** (laptop và điện thoại). Đó là điều kiện cần để demo không cần hướng dẫn, không phải bằng chứng người dùng hiểu được khuyến nghị.
