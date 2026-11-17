-- Tạo CSDL MySQL cho hệ thống đặt lịch (chạy bằng tài khoản root)
CREATE DATABASE IF NOT EXISTS datlich CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'datlich_user'@'localhost' IDENTIFIED BY 'matkhau';
GRANT ALL PRIVILEGES ON datlich.* TO 'datlich_user'@'localhost';
FLUSH PRIVILEGES;
-- Các bảng được tạo tự động bằng: python manage.py migrate
