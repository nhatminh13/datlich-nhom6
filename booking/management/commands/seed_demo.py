"""Tạo dữ liệu mẫu để demo: python manage.py seed_demo [--reset]"""
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from booking.models import Appointment, AppointmentLog, Availability, Service, Staff, TimeOff, User

PASSWORD = "demo1234"


class Command(BaseCommand):
    help = "Tạo tài khoản, dịch vụ, nhân viên, giờ làm và lịch hẹn mẫu"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Xóa dữ liệu cũ trước khi tạo")

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["reset"]:
            AppointmentLog.objects.all().delete()
            Appointment.objects.all().delete()
            TimeOff.objects.all().delete()
            Availability.objects.all().delete()
            Staff.objects.all().delete()
            Service.objects.all().delete()
            User.objects.all().delete()
        if User.objects.filter(username="admin").exists():
            self.stdout.write(self.style.WARNING("Dữ liệu mẫu đã có. Dùng --reset để tạo lại."))
            return

        def mk_user(username, name, role, phone="", **kw):
            u = User(username=username, first_name=name, role=role, phone=phone, **kw)
            u.set_password(PASSWORD)
            u.save()
            return u

        mk_user("admin", "Chủ tiệm An Nhiên", User.Role.ADMIN, "0900000000", is_staff=True, is_superuser=True)
        services = {n: Service.objects.create(name=n, description=d, duration_minutes=m, price=p) for n, d, m, p in [
            ("Cắt tóc nam", "Cắt, tạo kiểu cơ bản", 30, 80000),
            ("Cắt tóc nữ", "Cắt, sấy tạo kiểu", 45, 120000),
            ("Gội đầu dưỡng sinh", "Gội, massage đầu cổ vai", 30, 70000),
            ("Uốn tóc", "Uốn lạnh/nóng, đã gồm gội", 90, 450000),
            ("Nhuộm tóc", "Nhuộm màu thời trang", 90, 400000),
            ("Cạo mặt", "Cạo mặt, đắp khăn nóng", 15, 40000),
        ]}
        staff_specs = [
            ("tho_an", "Nguyễn Văn An", ["Cắt tóc nam", "Gội đầu dưỡng sinh", "Cạo mặt"]),
            ("tho_binh", "Trần Thị Bình", ["Cắt tóc nữ", "Uốn tóc", "Nhuộm tóc", "Gội đầu dưỡng sinh"]),
            ("tho_cuong", "Lê Minh Cường", ["Cắt tóc nam", "Cắt tóc nữ", "Nhuộm tóc", "Cạo mặt"]),
        ]
        staff = []
        for uname, name, svs in staff_specs:
            s = Staff.objects.create(user=mk_user(uname, name, User.Role.STAFF, "0911111111"))
            s.services.set([services[x] for x in svs])
            for wd in range(6):  # Thứ 2 – Thứ 7
                Availability.objects.create(staff=s, weekday=wd, start_time=time(8), end_time=time(12))
                Availability.objects.create(staff=s, weekday=wd, start_time=time(13), end_time=time(20))
            staff.append(s)
        # Thợ Cường làm thêm sáng Chủ nhật
        Availability.objects.create(staff=staff[2], weekday=6, start_time=time(8), end_time=time(12))

        c1 = mk_user("khach1", "Phạm Thu Hà", User.Role.CUSTOMER, "0987654321")
        c2 = mk_user("khach2", "Đỗ Quang Huy", User.Role.CUSTOMER, "0976543210")

        tz = timezone.get_current_timezone()
        today = timezone.localdate()

        def at(day_offset, h, m=0):
            return timezone.make_aware(datetime.combine(today + timedelta(days=day_offset), time(h, m)), tz)

        def appt(cust, st, sv, start, status):
            sv = services[sv]
            a = Appointment.objects.create(customer=cust, staff=st, service=sv, start=start,
                                           end=start + timedelta(minutes=sv.duration_minutes), status=status)
            AppointmentLog.objects.create(appointment=a, actor=cust, action="CREATE", new_status=status)

        S = Appointment.Status
        # Quá khứ – đã hoàn tất / đã hủy (dữ liệu cho thống kê)
        for d in range(-6, 0):
            appt(c1 if d % 2 else c2, staff[d % 3], "Cắt tóc nam" if d % 3 != 1 else "Cắt tóc nữ", at(d, 9), S.COMPLETED)
            appt(c2, staff[1], "Gội đầu dưỡng sinh", at(d, 14), S.COMPLETED if d % 2 else S.CANCELLED)
        # Hôm nay: một lịch đã xác nhận vào sáng sớm (có thể bấm Hoàn tất)
        appt(c1, staff[0], "Cắt tóc nam", at(0, 8), S.CONFIRMED)
        # Tương lai
        appt(c1, staff[0], "Cắt tóc nam", at(1, 9), S.PENDING)
        appt(c2, staff[1], "Uốn tóc", at(1, 14), S.CONFIRMED)
        appt(c2, staff[2], "Nhuộm tóc", at(2, 10), S.PENDING)
        appt(c1, staff[1], "Cắt tóc nữ", at(3, 15, 30), S.PENDING)
        # Thời gian nghỉ mẫu
        TimeOff.objects.create(staff=staff[2], start=at(4, 8), end=at(4, 20), reason="Nghỉ phép")

        self.stdout.write(self.style.SUCCESS(
            f"Đã tạo dữ liệu mẫu. Mật khẩu chung: {PASSWORD}\n"
            "  Quản trị: admin | Nhân viên: tho_an, tho_binh, tho_cuong | Khách hàng: khach1, khach2"))
