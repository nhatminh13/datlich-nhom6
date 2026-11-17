# Hệ thống đặt lịch hẹn – Nhóm 6 (Dự án 08)

Ứng dụng web đặt lịch cho **Tiệm tóc An Nhiên** (bối cảnh giả định: một cơ sở, 3 thợ).
Học phần **Đồ án 1** – Trường Quốc tế, ĐHQG Hà Nội · GVHD: **Thầy Lê Xuân Hải**.

## Thành viên
| Họ tên | MSSV | Phụ trách |
| --- | --- | --- |
| Bùi Nhật Minh | 25071101 | FR01–FR03, thiết kế CSDL/ERD |
| Dương Trọng Nghĩa | 25071122 | FR04–FR06, quy tắc chống trùng lịch |

## Chức năng
| Mã | Chức năng | Trạng thái |
| --- | --- | --- |
| FR01 | Đăng ký, đăng nhập, phân quyền 3 vai trò (Khách hàng / Nhân viên / Quản trị), kiểm tra quyền ở máy chủ | ✅ |
| FR02 | Quản lý dịch vụ (tên, thời lượng, giá) và nhân viên (tài khoản, dịch vụ đảm nhận) | ✅ |
| FR03 | Cấu hình giờ làm việc theo tuần và thời gian nghỉ của từng nhân viên | ✅ |
| FR04 | Hiển thị khung giờ trống theo dịch vụ – thợ – ngày (bước 15 phút) | ✅ |
| FR05 | Đặt, xem, hủy, đổi lịch; tự tính giờ kết thúc; chặn chồng lấn, kể cả khi đặt đồng thời | ✅ |
| FR06 | Nhân viên xác nhận / hoàn tất; lọc theo ngày, trạng thái, thợ, khách; thống kê số lượt theo ngày | ✅ |

Quy tắc chính: chỉ đặt trong giờ làm việc, không trùng thời gian nghỉ, không chồng lấn lịch đang hiệu lực
của cùng thợ, không đặt quá khứ, đặt trước tối đa 30 ngày, khách chỉ hủy/đổi trước giờ hẹn ≥ 2 giờ,
nhân viên/quản trị hủy phải có lý do. Mọi thay đổi được ghi vào nhật ký lịch hẹn.

## Công nghệ
Python 3.10+, Django 5, MySQL 8 (hoặc SQLite để chạy thử nhanh), Bootstrap 5.

## Cài đặt và chạy
```bash
git clone <đường dẫn repository>
cd datlich-nhom6
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo        # tạo dữ liệu & tài khoản mẫu
python manage.py runserver        # mở http://127.0.0.1:8000
```

### Dùng MySQL
1. Chạy `docs/create_database.sql` bằng tài khoản root.
2. `pip install mysqlclient`
3. Sao chép `.env.example` thành `.env`, đặt `DB_ENGINE=mysql` và thông tin kết nối.
4. `python manage.py migrate` rồi `python manage.py seed_demo`.

## Tài khoản mẫu (mật khẩu chung: `demo1234`)
| Vai trò | Tên đăng nhập |
| --- | --- |
| Quản trị | `admin` |
| Nhân viên | `tho_an`, `tho_binh`, `tho_cuong` |
| Khách hàng | `khach1`, `khach2` |

Gợi ý demo: đăng nhập `khach1` → **Đặt lịch** → chọn dịch vụ, thợ, ngày → chọn giờ → xác nhận.
Đăng nhập `tho_an` → **Lịch làm việc** → Xác nhận / Hoàn tất. Đăng nhập `admin` → Dịch vụ, Nhân viên
(giờ làm & nghỉ), Thống kê.

## Kiểm thử
```bash
python manage.py test booking
```
11 test case cho: tính giờ kết thúc, ngoài giờ làm, chồng lấn (kể cả giờ bắt đầu khác nhau), lịch nối tiếp,
lịch đã hủy giải phóng khung giờ, thời gian nghỉ, đổi lịch lỗi giữ lịch cũ, luồng trạng thái, phân quyền.

## Cấu trúc thư mục
```
datlich-nhom6/
├── config/                 # cấu hình Django (settings, urls)
├── booking/
│   ├── models.py           # 7 bảng: users, services, staff, availabilities, time_offs, appointments, appointment_logs
│   ├── services.py         # nghiệp vụ: lịch trống, đặt/đổi/hủy, xác nhận/hoàn tất, chống trùng
│   ├── views.py, urls.py, forms.py
│   ├── templates/booking/  # giao diện
│   ├── static/booking/     # CSS
│   ├── management/commands/seed_demo.py
│   └── tests.py
├── docs/                   # ERD, script tạo CSDL
├── requirements.txt
└── .env.example
```

## Ghi chú sử dụng AI
Nhóm sử dụng trợ lý AI (Claude) để hỗ trợ soạn khung mã nguồn, giao diện và test case; nhóm đã đọc lại,
chạy thử và chịu trách nhiệm toàn bộ nội dung nộp.
