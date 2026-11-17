"""Mô hình dữ liệu – 7 bảng chính theo thiết kế ERD tuần 3.

users, services, staff, availabilities, time_offs, appointments, appointment_logs
(+ bảng nối staff_services do quan hệ nhiều-nhiều Nhân viên – Dịch vụ).
"""
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Khách hàng"
        STAFF = "STAFF", "Nhân viên"
        ADMIN = "ADMIN", "Quản trị"

    role = models.CharField("Vai trò", max_length=10, choices=Role.choices, default=Role.CUSTOMER)
    phone = models.CharField("Số điện thoại", max_length=15, blank=True)

    class Meta:
        db_table = "users"
        verbose_name = "Người dùng"
        verbose_name_plural = "Người dùng"

    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER

    @property
    def is_staff_member(self):
        return self.role == self.Role.STAFF

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    def display_name(self):
        return self.get_full_name() or self.username


class Service(models.Model):
    name = models.CharField("Tên dịch vụ", max_length=100, unique=True)
    description = models.CharField("Mô tả", max_length=255, blank=True)
    duration_minutes = models.PositiveIntegerField("Thời lượng (phút)")
    price = models.PositiveIntegerField("Giá (VNĐ)", default=0)
    is_active = models.BooleanField("Đang cung cấp", default=True)

    class Meta:
        db_table = "services"
        ordering = ["name"]
        verbose_name = "Dịch vụ"
        verbose_name_plural = "Dịch vụ"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(duration_minutes__gte=15) & models.Q(duration_minutes__lte=240),
                name="service_duration_15_240",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.duration_minutes} phút)"


class Staff(models.Model):
    user = models.OneToOneField(User, on_delete=models.PROTECT, related_name="staff_profile")
    title = models.CharField("Chức danh", max_length=50, default="Thợ tóc")
    services = models.ManyToManyField(Service, related_name="staff_members", db_table="staff_services",
                                      verbose_name="Dịch vụ đảm nhận")
    is_active = models.BooleanField("Đang làm việc", default=True)

    class Meta:
        db_table = "staff"
        verbose_name = "Nhân viên"
        verbose_name_plural = "Nhân viên"

    def __str__(self):
        return self.user.display_name()


class Availability(models.Model):
    """Giờ làm việc lặp lại hằng tuần của một nhân viên."""
    WEEKDAYS = [(0, "Thứ 2"), (1, "Thứ 3"), (2, "Thứ 4"), (3, "Thứ 5"), (4, "Thứ 6"), (5, "Thứ 7"), (6, "Chủ nhật")]

    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="availabilities")
    weekday = models.PositiveSmallIntegerField("Thứ", choices=WEEKDAYS)
    start_time = models.TimeField("Bắt đầu")
    end_time = models.TimeField("Kết thúc")

    class Meta:
        db_table = "availabilities"
        ordering = ["weekday", "start_time"]
        verbose_name = "Giờ làm việc"
        verbose_name_plural = "Giờ làm việc"
        constraints = [
            models.CheckConstraint(condition=models.Q(end_time__gt=models.F("start_time")),
                                   name="availability_end_after_start"),
            models.UniqueConstraint(fields=["staff", "weekday", "start_time"], name="availability_unique_start"),
        ]

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("Giờ kết thúc phải sau giờ bắt đầu.")
        if self.staff_id and self.start_time and self.end_time:
            overlap = Availability.objects.filter(
                staff_id=self.staff_id, weekday=self.weekday,
                start_time__lt=self.end_time, end_time__gt=self.start_time,
            ).exclude(pk=self.pk)
            if overlap.exists():
                raise ValidationError("Khung giờ này chồng lên một ca làm khác của nhân viên trong cùng ngày.")

    def __str__(self):
        return f"{self.get_weekday_display()} {self.start_time:%H:%M}–{self.end_time:%H:%M}"


class TimeOff(models.Model):
    """Thời gian nghỉ (nghỉ phép, nghỉ đột xuất) – không nhận lịch."""
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name="time_offs")
    start = models.DateTimeField("Từ")
    end = models.DateTimeField("Đến")
    reason = models.CharField("Lý do", max_length=255, blank=True)

    class Meta:
        db_table = "time_offs"
        ordering = ["start"]
        verbose_name = "Thời gian nghỉ"
        verbose_name_plural = "Thời gian nghỉ"
        constraints = [
            models.CheckConstraint(condition=models.Q(end__gt=models.F("start")), name="timeoff_end_after_start"),
        ]

    def clean(self):
        if self.start and self.end and self.end <= self.start:
            raise ValidationError("Thời điểm kết thúc phải sau thời điểm bắt đầu.")


class Appointment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Chờ xác nhận"
        CONFIRMED = "CONFIRMED", "Đã xác nhận"
        COMPLETED = "COMPLETED", "Hoàn tất"
        CANCELLED = "CANCELLED", "Đã hủy"

    ACTIVE_STATUSES = [Status.PENDING, Status.CONFIRMED]

    customer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="appointments")
    staff = models.ForeignKey(Staff, on_delete=models.PROTECT, related_name="appointments")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="appointments")
    start = models.DateTimeField("Bắt đầu")
    end = models.DateTimeField("Kết thúc")
    status = models.CharField("Trạng thái", max_length=10, choices=Status.choices, default=Status.PENDING)
    note = models.CharField("Ghi chú", max_length=255, blank=True)
    cancel_reason = models.CharField("Lý do hủy", max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "appointments"
        ordering = ["start"]
        verbose_name = "Lịch hẹn"
        verbose_name_plural = "Lịch hẹn"
        indexes = [models.Index(fields=["staff", "start", "end"], name="appt_staff_time_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(end__gt=models.F("start")), name="appointment_end_after_start"),
        ]

    @property
    def is_active(self):
        return self.status in self.ACTIVE_STATUSES

    def __str__(self):
        return f"#{self.pk} {self.service.name} – {self.staff}"


class AppointmentLog(models.Model):
    """Nhật ký thay đổi trạng thái/thời gian của lịch hẹn (truy vết)."""
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="logs")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="+")
    ACTIONS = [("CREATE", "Đặt lịch"), ("CONFIRM", "Xác nhận"), ("COMPLETE", "Hoàn tất"),
               ("CANCEL", "Hủy lịch"), ("RESCHEDULE", "Đổi lịch")]
    action = models.CharField("Thao tác", max_length=20, choices=ACTIONS)
    old_status = models.CharField(max_length=10, blank=True)
    new_status = models.CharField(max_length=10, blank=True)
    detail = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "appointment_logs"
        ordering = ["-created_at"]
        verbose_name = "Nhật ký lịch hẹn"
        verbose_name_plural = "Nhật ký lịch hẹn"
