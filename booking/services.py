"""Nghiệp vụ đặt lịch: tính lịch trống, đặt, đổi, hủy, xác nhận, hoàn tất.

Mọi kiểm tra quy tắc (BR) thực hiện ở máy chủ. Đặt/đổi lịch chạy trong một giao dịch
và khóa dòng nhân viên (SELECT ... FOR UPDATE) để hai yêu cầu đồng thời không thể
cùng lấy một khung giờ.
"""
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Appointment, AppointmentLog, Service, Staff

Status = Appointment.Status


class BookingError(Exception):
    """Lỗi nghiệp vụ – thông điệp hiển thị trực tiếp cho người dùng."""


def compute_end(start, service):
    # BR01: giờ kết thúc = giờ bắt đầu + thời lượng dịch vụ (máy chủ tự tính)
    return start + timedelta(minutes=service.duration_minutes)


def _overlaps(a_start, a_end, b_start, b_end):
    # BR05: hai khoảng [a_start, a_end) và [b_start, b_end) chồng lấn khi a_start < b_end và b_start < a_end
    return a_start < b_end and b_start < a_end


def validate_slot(staff, service, start, exclude_id=None):
    """Kiểm tra một khung giờ có hợp lệ không. Trả về giờ kết thúc hoặc ném BookingError."""
    now = timezone.now()
    if start <= now:
        raise BookingError("Không thể đặt lịch vào thời điểm đã qua.")
    if start > now + timedelta(days=settings.BOOKING_MAX_DAYS_AHEAD):
        raise BookingError(f"Chỉ được đặt trước tối đa {settings.BOOKING_MAX_DAYS_AHEAD} ngày.")
    if not service.is_active:
        raise BookingError("Dịch vụ này hiện không còn cung cấp.")
    if not staff.is_active:
        raise BookingError("Nhân viên này hiện không nhận lịch.")
    if not staff.services.filter(pk=service.pk).exists():
        raise BookingError("Nhân viên không thực hiện dịch vụ đã chọn.")

    end = compute_end(start, service)
    local_start, local_end = timezone.localtime(start), timezone.localtime(end)
    if local_start.date() != local_end.date():
        raise BookingError("Lịch hẹn phải kết thúc trong cùng ngày.")

    # BR03: phải nằm trọn trong một ca làm việc của nhân viên
    windows = staff.availabilities.filter(weekday=local_start.weekday())
    if not any(w.start_time <= local_start.time() and local_end.time() <= w.end_time for w in windows):
        raise BookingError("Khung giờ nằm ngoài giờ làm việc của nhân viên.")

    # BR04: không rơi vào thời gian nghỉ
    if staff.time_offs.filter(start__lt=end, end__gt=start).exists():
        raise BookingError("Nhân viên nghỉ trong khoảng thời gian này.")

    # BR05: không chồng lấn với lịch đang hiệu lực của cùng nhân viên
    clash = Appointment.objects.filter(
        staff=staff, status__in=Appointment.ACTIVE_STATUSES, start__lt=end, end__gt=start
    )
    if exclude_id:
        clash = clash.exclude(pk=exclude_id)
    if clash.exists():
        raise BookingError("Khung giờ này vừa có người đặt. Vui lòng chọn giờ khác.")
    return end


def available_slots(staff, service, day, exclude_id=None):
    """Danh sách giờ bắt đầu còn trống của nhân viên cho dịch vụ trong ngày `day`."""
    if not (staff.is_active and service.is_active and staff.services.filter(pk=service.pk).exists()):
        return []
    tz = timezone.get_current_timezone()
    now = timezone.now()
    step = timedelta(minutes=settings.BOOKING_SLOT_STEP_MINUTES)
    duration = timedelta(minutes=service.duration_minutes)
    day_start = timezone.make_aware(datetime.combine(day, datetime.min.time()), tz)
    day_end = day_start + timedelta(days=1)
    if day_start > now + timedelta(days=settings.BOOKING_MAX_DAYS_AHEAD):
        return []

    busy = list(
        Appointment.objects.filter(staff=staff, status__in=Appointment.ACTIVE_STATUSES,
                                   start__lt=day_end, end__gt=day_start)
        .exclude(pk=exclude_id).values_list("start", "end")
    )
    busy += list(staff.time_offs.filter(start__lt=day_end, end__gt=day_start).values_list("start", "end"))

    slots = []
    for w in staff.availabilities.filter(weekday=day.weekday()):
        cur = timezone.make_aware(datetime.combine(day, w.start_time), tz)
        win_end = timezone.make_aware(datetime.combine(day, w.end_time), tz)
        while cur + duration <= win_end:
            if cur > now and not any(_overlaps(cur, cur + duration, b0, b1) for b0, b1 in busy):
                slots.append(cur)
            cur += step
    return sorted(slots)


def _log(appt, actor, action, old_status="", detail=""):
    AppointmentLog.objects.create(appointment=appt, actor=actor, action=action,
                                  old_status=old_status, new_status=appt.status, detail=detail)


def create_appointment(customer, staff_id, service_id, start, note=""):
    with transaction.atomic():
        staff = Staff.objects.select_for_update().get(pk=staff_id)  # khóa dòng nhân viên
        service = Service.objects.get(pk=service_id)
        end = validate_slot(staff, service, start)
        appt = Appointment.objects.create(customer=customer, staff=staff, service=service,
                                          start=start, end=end, note=note, status=Status.PENDING)
        _log(appt, customer, "CREATE", detail=f"Đặt lịch {timezone.localtime(start):%d/%m/%Y %H:%M}")
    return appt


# ---------- Phân quyền trên từng lịch hẹn ----------

def can_view(user, appt):
    if user.is_admin_role:
        return True
    if user.is_staff_member:
        return appt.staff.user_id == user.id
    return appt.customer_id == user.id


def _customer_deadline_ok(appt):
    return appt.start - timezone.now() >= timedelta(hours=settings.CANCEL_DEADLINE_HOURS)


def can_customer_change(user, appt):
    return (user.is_customer and appt.customer_id == user.id and appt.is_active
            and _customer_deadline_ok(appt))


def reschedule_appointment(appt, actor, new_start):
    if not can_customer_change(actor, appt) and not actor.is_admin_role:
        raise BookingError(f"Chỉ được đổi lịch đang hiệu lực và trước giờ hẹn ít nhất "
                           f"{settings.CANCEL_DEADLINE_HOURS} giờ.")
    with transaction.atomic():
        staff = Staff.objects.select_for_update().get(pk=appt.staff_id)
        appt = Appointment.objects.select_for_update().get(pk=appt.pk)
        end = validate_slot(staff, appt.service, new_start, exclude_id=appt.pk)  # lỗi -> giữ nguyên lịch cũ
        old_status, old_start = appt.status, appt.start
        appt.start, appt.end, appt.status = new_start, end, Status.PENDING
        appt.save()
        _log(appt, actor, "RESCHEDULE", old_status,
             f"{timezone.localtime(old_start):%d/%m %H:%M} → {timezone.localtime(new_start):%d/%m %H:%M}")
    return appt


def cancel_appointment(appt, actor, reason=""):
    if not appt.is_active:
        raise BookingError("Lịch hẹn này không còn ở trạng thái có thể hủy.")
    if actor.is_customer:
        if not can_customer_change(actor, appt):
            raise BookingError(f"Chỉ được hủy trước giờ hẹn ít nhất {settings.CANCEL_DEADLINE_HOURS} giờ.")
    elif actor.is_staff_member:
        if appt.staff.user_id != actor.id:
            raise BookingError("Bạn không có quyền hủy lịch này.")
        if not reason.strip():
            raise BookingError("Nhân viên hủy lịch phải nhập lý do.")
    elif actor.is_admin_role:
        if not reason.strip():
            raise BookingError("Quản trị hủy lịch phải nhập lý do.")
    else:
        raise BookingError("Bạn không có quyền hủy lịch này.")
    old = appt.status
    appt.status, appt.cancel_reason = Status.CANCELLED, reason.strip()
    appt.save()
    _log(appt, actor, "CANCEL", old, reason.strip())
    return appt


def _check_handler(appt, actor):
    if not (actor.is_admin_role or (actor.is_staff_member and appt.staff.user_id == actor.id)):
        raise BookingError("Bạn không có quyền xử lý lịch này.")


def confirm_appointment(appt, actor):
    _check_handler(appt, actor)
    if appt.status != Status.PENDING:
        raise BookingError("Chỉ xác nhận được lịch đang chờ xác nhận.")
    appt.status = Status.CONFIRMED
    appt.save()
    _log(appt, actor, "CONFIRM", Status.PENDING)
    return appt


def complete_appointment(appt, actor):
    _check_handler(appt, actor)
    if appt.status != Status.CONFIRMED:
        raise BookingError("Chỉ hoàn tất được lịch đã xác nhận.")
    if appt.start > timezone.now():
        raise BookingError("Chưa đến giờ hẹn nên chưa thể hoàn tất.")
    appt.status = Status.COMPLETED
    appt.save()
    _log(appt, actor, "COMPLETE", Status.CONFIRMED)
    return appt
