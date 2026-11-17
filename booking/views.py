from datetime import date, datetime, timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.http import require_POST

from . import services as svc
from .forms import AvailabilityForm, RegisterForm, ServiceForm, StaffForm, TimeOffForm
from .models import Appointment, Availability, Service, Staff, TimeOff, User

Status = Appointment.Status


def role_required(*roles):
    """Kiểm tra quyền ở máy chủ (FR01). ADMIN luôn được phép."""
    def deco(view):
        @wraps(view)
        @login_required
        def wrapper(request, *a, **kw):
            u = request.user
            if u.is_admin_role or u.role in roles:
                return view(request, *a, **kw)
            raise PermissionDenied
        return wrapper
    return deco


def _safe_next(request):
    nxt = request.POST.get("next", "")
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else ""


def _parse_day(value, default=None):
    d = parse_date(value or "")
    return d or default or timezone.localdate()


def _parse_start(value):
    dt = parse_datetime(value or "")
    if dt is None:
        return None
    return dt if timezone.is_aware(dt) else timezone.make_aware(dt)


# ---------------- Chung ----------------

def home(request):
    services = Service.objects.filter(is_active=True)
    staff = Staff.objects.filter(is_active=True).select_related("user").prefetch_related("services")
    return render(request, "booking/home.html", {"services": services, "staff_list": staff})


def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Đăng ký thành công. Bạn có thể đặt lịch ngay.")
        return redirect("book")
    return render(request, "booking/register.html", {"form": form})


# ---------------- FR04 + FR05: Khách hàng ----------------

@role_required(User.Role.CUSTOMER)
def book(request):
    services = Service.objects.filter(is_active=True)
    staff_qs = Staff.objects.filter(is_active=True).select_related("user").prefetch_related("services")
    today = timezone.localdate()
    service = staff = None
    day = _parse_day(request.GET.get("date"), today)
    slots = []

    if request.method == "POST":
        service = get_object_or_404(Service, pk=request.POST.get("service"))
        staff = get_object_or_404(Staff, pk=request.POST.get("staff"))
        start = _parse_start(request.POST.get("start"))
        if not start:
            messages.error(request, "Vui lòng chọn một khung giờ.")
        else:
            try:
                appt = svc.create_appointment(request.user, staff.pk, service.pk, start,
                                              request.POST.get("note", "")[:255])
                messages.success(request, f"Đặt lịch thành công: {service.name} với {staff} lúc "
                                          f"{timezone.localtime(appt.start):%H:%M %d/%m/%Y}. Lịch đang chờ xác nhận.")
                return redirect("appointment_detail", pk=appt.pk)
            except svc.BookingError as e:
                messages.error(request, str(e))
        day = timezone.localtime(start).date() if start else day
    else:
        if request.GET.get("service"):
            service = Service.objects.filter(pk=request.GET["service"], is_active=True).first()
        if request.GET.get("staff"):
            staff = staff_qs.filter(pk=request.GET["staff"]).first()

    if service and staff:
        slots = svc.available_slots(staff, service, day)

    return render(request, "booking/book.html", {
        "services": services, "staff_list": staff_qs, "service": service, "staff": staff,
        "day": day, "today": today, "max_day": today + timedelta(days=settings.BOOKING_MAX_DAYS_AHEAD),
        "slots": slots, "prev_day": day - timedelta(days=1), "next_day": day + timedelta(days=1),
    })


@role_required(User.Role.CUSTOMER)
def my_appointments(request):
    qs = request.user.appointments.select_related("service", "staff__user")
    now = timezone.now()
    upcoming = qs.filter(end__gte=now, status__in=Appointment.ACTIVE_STATUSES).order_by("start")
    history = qs.exclude(pk__in=upcoming).order_by("-start")
    return render(request, "booking/my_appointments.html", {"upcoming": upcoming, "history": history})


@login_required
def appointment_detail(request, pk):
    appt = get_object_or_404(Appointment.objects.select_related("service", "staff__user", "customer"), pk=pk)
    if not svc.can_view(request.user, appt):
        raise PermissionDenied
    return render(request, "booking/appointment_detail.html", {
        "a": appt, "logs": appt.logs.select_related("actor"),
        "can_change": svc.can_customer_change(request.user, appt),
        "can_handle": request.user.is_admin_role or (request.user.is_staff_member and appt.staff.user_id == request.user.id),
        "deadline_hours": settings.CANCEL_DEADLINE_HOURS,
    })


@login_required
@require_POST
def appointment_cancel(request, pk):
    appt = get_object_or_404(Appointment, pk=pk)
    if not svc.can_view(request.user, appt):
        raise PermissionDenied
    try:
        svc.cancel_appointment(appt, request.user, request.POST.get("reason", ""))
        messages.success(request, "Đã hủy lịch hẹn.")
    except svc.BookingError as e:
        messages.error(request, str(e))
    nxt = _safe_next(request)
    return redirect(nxt) if nxt else redirect("appointment_detail", pk=pk)


@login_required
def appointment_reschedule(request, pk):
    appt = get_object_or_404(Appointment.objects.select_related("service", "staff__user"), pk=pk)
    if not svc.can_view(request.user, appt):
        raise PermissionDenied
    if not (svc.can_customer_change(request.user, appt) or (request.user.is_admin_role and appt.is_active)):
        messages.error(request, f"Lịch này không thể đổi (chỉ đổi lịch đang hiệu lực, trước giờ hẹn ít nhất "
                                f"{settings.CANCEL_DEADLINE_HOURS} giờ).")
        return redirect("appointment_detail", pk=pk)
    today = timezone.localdate()
    day = _parse_day(request.GET.get("date"), timezone.localtime(appt.start).date())
    if request.method == "POST":
        start = _parse_start(request.POST.get("start"))
        if not start:
            messages.error(request, "Vui lòng chọn khung giờ mới.")
        else:
            try:
                svc.reschedule_appointment(appt, request.user, start)
                messages.success(request, "Đổi lịch thành công. Lịch mới đang chờ xác nhận lại.")
                return redirect("appointment_detail", pk=pk)
            except svc.BookingError as e:
                messages.error(request, f"{e} Lịch cũ vẫn được giữ nguyên.")
            day = timezone.localtime(start).date()
    slots = svc.available_slots(appt.staff, appt.service, day, exclude_id=appt.pk)
    return render(request, "booking/reschedule.html", {
        "a": appt, "day": day, "slots": slots, "today": today,
        "max_day": today + timedelta(days=settings.BOOKING_MAX_DAYS_AHEAD),
        "prev_day": day - timedelta(days=1), "next_day": day + timedelta(days=1),
    })


# ---------------- FR06: Nhân viên / Quản trị ----------------

def _filtered_appointments(request):
    qs = Appointment.objects.select_related("service", "staff__user", "customer")
    if request.user.is_staff_member:
        qs = qs.filter(staff__user=request.user)
    f = {
        "date": request.GET.get("date", ""), "status": request.GET.get("status", ""),
        "staff": request.GET.get("staff", ""), "q": request.GET.get("q", "").strip(),
    }
    if f["date"]:
        d = parse_date(f["date"])
        if d:
            qs = qs.filter(start__date=d)
    if f["status"] in Status.values:
        qs = qs.filter(status=f["status"])
    if f["staff"] and request.user.is_admin_role:
        qs = qs.filter(staff_id=f["staff"])
    if f["q"]:
        qs = qs.filter(Q(customer__first_name__icontains=f["q"]) | Q(customer__phone__icontains=f["q"])
                       | Q(customer__username__icontains=f["q"]))
    return qs.order_by("start"), f


@role_required(User.Role.STAFF)
def staff_schedule(request):
    if "date" not in request.GET and not request.GET:
        return redirect(f"{request.path}?date={timezone.localdate():%Y-%m-%d}")
    qs, f = _filtered_appointments(request)
    return render(request, "booking/staff_schedule.html", {
        "appointments": qs, "f": f, "statuses": Status.choices,
        "staff_list": Staff.objects.select_related("user") if request.user.is_admin_role else None,
        "now": timezone.now(),
    })


def _handle(request, pk, func, ok_msg):
    appt = get_object_or_404(Appointment, pk=pk)
    try:
        func(appt, request.user)
        messages.success(request, ok_msg)
    except svc.BookingError as e:
        messages.error(request, str(e))
    return redirect(_safe_next(request) or "staff_schedule")


@role_required(User.Role.STAFF)
@require_POST
def appointment_confirm(request, pk):
    return _handle(request, pk, svc.confirm_appointment, "Đã xác nhận lịch hẹn.")


@role_required(User.Role.STAFF)
@require_POST
def appointment_complete(request, pk):
    return _handle(request, pk, svc.complete_appointment, "Đã đánh dấu hoàn tất.")


@role_required(User.Role.STAFF)
def statistics(request):
    today = timezone.localdate()
    d_from = _parse_day(request.GET.get("from"), today - timedelta(days=6))
    d_to = _parse_day(request.GET.get("to"), today + timedelta(days=7))
    if d_to < d_from:
        d_from, d_to = d_to, d_from
    qs = Appointment.objects.filter(start__date__gte=d_from, start__date__lte=d_to)
    if request.user.is_staff_member:
        qs = qs.filter(staff__user=request.user)
    agg = dict(
        total=Count("id"),
        pending=Count("id", filter=Q(status=Status.PENDING)),
        confirmed=Count("id", filter=Q(status=Status.CONFIRMED)),
        completed=Count("id", filter=Q(status=Status.COMPLETED)),
        cancelled=Count("id", filter=Q(status=Status.CANCELLED)),
    )
    by_day = {r["day"]: r for r in qs.annotate(day=TruncDate("start")).values("day").annotate(**agg)}
    rows, peak = [], 1
    d = d_from
    while d <= d_to:
        r = by_day.get(d, {"total": 0, "pending": 0, "confirmed": 0, "completed": 0, "cancelled": 0})
        rows.append({"day": d, **{k: r[k] for k in agg}})
        peak = max(peak, r["total"])
        d += timedelta(days=1)
    for r in rows:
        r["pct"] = round(r["total"] * 100 / peak)
    by_staff = (qs.values("staff__user__first_name").annotate(**agg).order_by("-total")
                if request.user.is_admin_role else None)
    totals = qs.aggregate(**agg)
    return render(request, "booking/statistics.html", {
        "rows": rows, "by_staff": by_staff, "totals": totals, "d_from": d_from, "d_to": d_to,
    })


# ---------------- FR02 + FR03: Quản trị ----------------

@role_required()
def service_list(request):
    return render(request, "booking/service_list.html",
                  {"services": Service.objects.annotate(n_staff=Count("staff_members"))})


@role_required()
def service_edit(request, pk=None):
    obj = get_object_or_404(Service, pk=pk) if pk else None
    form = ServiceForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Đã lưu dịch vụ.")
        return redirect("service_list")
    return render(request, "booking/form.html", {
        "form": form, "title": "Sửa dịch vụ" if obj else "Thêm dịch vụ", "back": "service_list"})


@role_required()
def staff_list(request):
    staff = Staff.objects.select_related("user").prefetch_related("services", "availabilities")
    return render(request, "booking/staff_list.html", {"staff_list": staff})


@role_required()
def staff_edit(request, pk=None):
    obj = get_object_or_404(Staff, pk=pk) if pk else None
    form = StaffForm(request.POST or None, staff=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Đã lưu thông tin nhân viên.")
        return redirect("staff_list")
    return render(request, "booking/form.html", {
        "form": form, "title": "Sửa nhân viên" if obj else "Thêm nhân viên", "back": "staff_list"})


@role_required()
def staff_hours(request, pk):
    staff = get_object_or_404(Staff.objects.select_related("user"), pk=pk)
    a_form = AvailabilityForm(prefix="a")
    t_form = TimeOffForm(prefix="t")
    if request.method == "POST":
        if "add_availability" in request.POST:
            a_form = AvailabilityForm(request.POST, prefix="a", instance=Availability(staff=staff))
            if a_form.is_valid():
                a_form.save()
                messages.success(request, "Đã thêm ca làm việc.")
                return redirect("staff_hours", pk=pk)
        elif "add_timeoff" in request.POST:
            t_form = TimeOffForm(request.POST, prefix="t", instance=TimeOff(staff=staff))
            if t_form.is_valid():
                t_form.save()
                n = Appointment.objects.filter(staff=staff, status__in=Appointment.ACTIVE_STATUSES,
                                               start__lt=t_form.instance.end, end__gt=t_form.instance.start).count()
                messages.success(request, "Đã thêm thời gian nghỉ.")
                if n:
                    messages.warning(request, f"Có {n} lịch hẹn đang hiệu lực trùng thời gian nghỉ – cần liên hệ khách để hủy/đổi.")
                return redirect("staff_hours", pk=pk)
    return render(request, "booking/staff_hours.html", {
        "staff": staff, "a_form": a_form, "t_form": t_form,
        "availabilities": staff.availabilities.all(),
        "time_offs": staff.time_offs.filter(end__gte=timezone.now()),
    })


@role_required()
@require_POST
def availability_delete(request, pk):
    a = get_object_or_404(Availability, pk=pk)
    a.delete()
    messages.success(request, "Đã xóa ca làm việc.")
    return redirect("staff_hours", pk=a.staff_id)


@role_required()
@require_POST
def timeoff_delete(request, pk):
    t = get_object_or_404(TimeOff, pk=pk)
    t.delete()
    messages.success(request, "Đã xóa thời gian nghỉ.")
    return redirect("staff_hours", pk=t.staff_id)
