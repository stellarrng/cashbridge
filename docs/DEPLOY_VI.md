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
- chưa cấu hình tài khoản (`CASHBRIDGE_USERS_JSON` hoặc `CASHBRIDGE_USERS_FILE`; băm mật mã bằng `python scripts/hash_passcode.py`);
- (v9) thiếu `CASHBRIDGE_VAULT_KEY` (khóa 32 byte, base64, dùng mã hóa chứng từ tải lên);
- (v9) `CASHBRIDGE_ENV` có giá trị lạ hoặc gõ sai (`prd`, `staging`, `Production `…): hệ thống coi là PRODUCTION và áp mọi kiểm tra trên,
  không bao giờ tự rơi về chế độ demo.

Ở chế độ này đăng nhập demo, đặt lại demo và các màn giả mạo đều tắt (404). Đây vẫn chưa phải chứng nhận bảo mật production: còn thiếu OIDC/MFA, lưu trữ bền vững và kiểm thử xâm nhập độc lập.

## v8: kiểm tra sau khi deploy (bắt buộc trước khi gửi link cho BTC)

```bash
# 1. Kiểm tra cục bộ chế độ PRODUCTION qua HTTPS thật (CA tạm), khởi động lại, quét log:
make deploy-check                      # -> reports/deploy_verification.md (27/27 khi viết tài liệu này)

# 2. Kiểm tra bản đã deploy (Render/Vercel/Fly):
python scripts/deploy_smoke.py --base-url https://<host> --expect demo        # link demo cho giám khảo
python scripts/deploy_smoke.py --base-url https://<host> --expect production \
    --user <tài-khoản> --passcode <mật-mã> --json reports/deploy_smoke.json
```

Smoke test kiểm tra: HTTPS + HSTS, CSP, không lộ tài khoản demo / OTP demo / API docs ở production, CORS đóng,
401 trên mọi route cần đăng nhập (kể cả token giả), không lộ stack trace, giới hạn kích thước body, chặn path traversal,
ranh giới vai trò SME/ngân hàng và token hết hiệu lực sau khi đăng xuất. Chỉ đọc; không lập hay duyệt hồ sơ.

Lưu ý production:
- Data Reliability Gate **luôn bật**: cần `CASHBRIDGE_QUALITY_MANIFEST_PATH` + chữ ký xác thực nguồn
  (`CASHBRIDGE_SOURCE_ATTESTATIONS_PATH`, `CASHBRIDGE_ATTESTATION_KEY`), nếu không mọi hành động tài trợ trả 409.
- Đặt `CASHBRIDGE_SESSION_SECRET` cố định để phiên không mất khi khởi động lại; đặt `CASHBRIDGE_TRUST_PROXY=1` sau proxy.
- Log, audit và dữ liệu workspace/queue nằm trong `CASHBRIDGE_RUNTIME_DIR` (volume `runtime` trong docker-compose);
  khi khởi động lại, audit log cũ được lưu vào `evidence/archive/<thời điểm>/` kèm MANIFEST và kết quả kiểm tra chuỗi hash.

## v9: chứng từ mã hóa, phiên dùng chung, bộ chuyển đổi bên cho vay

```bash
# Khóa kho chứng từ (giữ cẩn thận: mất khóa = không đọc lại được chứng từ đã lưu)
python -c "import base64,secrets;print(base64.b64encode(secrets.token_bytes(32)).decode())"   # -> CASHBRIDGE_VAULT_KEY
```

- **Kho chứng từ**: tệp SME tải lên được kiểm tra theo byte đầu (PDF/PNG/JPEG/văn bản, ≤ 10 MB), máy chủ tự tính SHA-256,
  lưu mã hóa AES-256-GCM trong `<runtime>/vault/`. Ngân hàng chỉ mở được qua CashBridge (ghi audit) và phải mở đúng phiên bản
  trước khi chấp nhận. Khi Giám đốc rút hồ sơ, tệp của hồ sơ đó bị xóa. Volume `runtime` phải được sao lưu.
- **Phiên**: đăng xuất, "đăng xuất mọi thiết bị" và giới hạn đăng nhập sai nằm trong `<runtime>/sessions.sqlite3`
  (mặc định ở production), dùng chung cho mọi worker trên cùng máy (`make deploy-check` kiểm tra với 3 worker).
  Trên Vercel/serverless không có đĩa dùng chung: trạng thái này chỉ theo từng instance, cần kho ngoài (chưa kèm theo).
- **Bên cho vay**: `CASHBRIDGE_LENDER_ADAPTER=mock` (mặc định, báo giá MÔ PHỎNG từ danh mục MOCK, không phải chào giá) hoặc
  `sandbox_http` với `CASHBRIDGE_LENDER_BASE_URL` (https), `CASHBRIDGE_LENDER_API_KEY`, `CASHBRIDGE_LENDER_WEBHOOK_SECRET`.
  Webhook `POST /api/lender/webhook` phải có chữ ký HMAC (`X-Lender-Signature: t=<unix>,v1=<hex>`), trong vòng 5 phút,
  mỗi `event_id` chỉ xử lý một lần.
- Smoke test v9 kiểm thêm: các route nguồn gốc số liệu / báo giá / tệp chứng từ đòi đăng nhập, webhook không chữ ký bị 401.
