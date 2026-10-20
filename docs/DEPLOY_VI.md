# Chạy và deploy CashBridge

Có 3 cách, xếp theo độ ổn định khi demo cho giám khảo.

| Cách | Khi nào dùng | Ưu | Nhược |
|---|---|---|---|
| Local (`make run`) | Dev, quay video | Đủ tính năng (OCR, PDF, scikit-learn) | Chỉ máy mình xem được |
| **Render (Docker)** | **Buổi chấm, link gửi BTC** | 1 tiến trình nên trạng thái demo nhất quán; có OCR | Gói free ngủ sau ~15 phút, lần đầu mở mất ~30–60 giây |
| Vercel (serverless) | Link xem nhanh, landing | Nhanh, CDN, không ngủ | Bản gọn: không đọc PDF/ảnh (dán text hoặc TXT); mỗi instance giữ ca demo riêng |

## 1. Chạy local

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
make test && make trust
make run            # http://localhost:8000
```

Tài khoản demo (bấm một lần trên màn đăng nhập, hoặc dùng nút "Xem với vai trò" trong trang Tổng quan):

| Vai trò | Tài khoản | Mật mã |
|---|---|---|
| Kế toán trưởng (lập hồ sơ) | `sme.lan` Nguyễn Thị Lan · `sme.olivia` Olivia Bennett | `lan-demo-2026` · `olivia-demo-2026` |
| Giám đốc (duyệt OTP) | `sme.minh` Trần Văn Minh · `sme.chen` Chen Wei 陈伟 | `minh-demo-2026` · `chen-demo-2026` |
| Ngân hàng (thẩm định) | `bank.lihua` Li Hua 李华 · `bank.daniel` Daniel Hughes | `lihua-demo-2026` · `daniel-demo-2026` |

Mã OTP của Giám đốc: thêm secret `JBSWY3DPEHPK3PXP` vào Google Authenticator / Microsoft Authenticator (nhập tay, Base32, 30 giây).

Giao diện có EN / VI / 中文 và Sáng / Tối (nút trên thanh trên cùng; mặc định theo hệ điều hành).

## 2. Render (khuyến nghị cho buổi chấm)

1. Đẩy repo lên GitHub (`.env` không bị commit).
2. Vào render.com → **New** → **Blueprint** → chọn repo. Render đọc `render.yaml`, build `Dockerfile`, tự sinh `CASHBRIDGE_SESSION_SECRET`.
3. Chờ build xong, mở URL `https://<tên>.onrender.com`. Health check: `/api/health`.
4. Trước giờ chấm 5 phút, mở link một lần để "đánh thức" dịch vụ.

## 3. Vercel

**Qua giao diện web**
1. Đẩy repo lên GitHub.
2. vercel.com → **Add New… → Project** → Import repo. Framework Preset: **Other**. Không cần Build Command.
3. **Environment Variables**: thêm `CASHBRIDGE_SESSION_SECRET` = chuỗi ngẫu nhiên ≥ 32 ký tự (ví dụ chạy `python -c "import secrets;print(secrets.token_urlsafe(48))"`). Có thể để trống khi demo, hệ thống tự sinh theo deployment, nhưng nên đặt.
4. **Deploy**. Mở `https://<project>.vercel.app`.

**Qua CLI**
```bash
npm i -g vercel
vercel            # lần đầu: đăng nhập, chọn scope, link project
vercel env add CASHBRIDGE_SESSION_SECRET
vercel --prod
```

Cách hoạt động: `vercel.json` phục vụ `/`, `/app`, `/assets/*` từ CDN; mọi đường dẫn khác (`/api/*`, `/docs`) đi vào hàm Python `vercel_app.py`. Hàm cài `requirements.txt` bản gọn (~155 MB, dưới giới hạn 250 MB): không có scikit-learn (mô hình rủi ro dùng bộ giải NumPy tương đương, có test so khớp), không có PyMuPDF/Tesseract. File runtime ghi vào `/tmp`.

Lưu ý khi demo trên Vercel: nếu Vercel chạy nhiều instance song song, một instance có thể chưa thấy hồ sơ vừa lập ở instance khác. Nếu gặp, bấm *Nhật ký & độ tin cậy → Đặt lại demo* rồi chạy lại một lượt, hoặc dùng Render cho buổi chấm.

## 4. Tách frontend (Vercel) và API (Render)

1. Build giao diện với `VITE_API_BASE=https://<api>.onrender.com npm run build` (trong `frontend/`).
2. Trên Render đặt `CASHBRIDGE_ALLOWED_ORIGINS=https://<project>.vercel.app`.
3. Trong `vercel.json`, thêm origin API vào `connect-src` của header CSP.

## 5. Chế độ production (khi dùng dữ liệu thật)

Đặt `CASHBRIDGE_ENV=production`. Ứng dụng sẽ **từ chối khởi động** nếu:
- `OTP_SECRET` trống hoặc là secret demo;
- `CASHBRIDGE_SESSION_SECRET` ngắn hơn 32 ký tự;
- chưa cấu hình tài khoản (`CASHBRIDGE_USERS_JSON` hoặc `CASHBRIDGE_USERS_FILE`; băm mật mã bằng `python scripts/hash_passcode.py`).

Ở chế độ này đăng nhập demo, đặt lại demo và các màn giả mạo đều tắt (404). Đây vẫn chưa phải chứng nhận bảo mật production: còn thiếu OIDC/MFA, lưu trữ bền vững và kiểm thử xâm nhập độc lập.
