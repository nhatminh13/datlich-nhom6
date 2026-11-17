"""Kiểm thử quy tắc nghiệp vụ chính: python manage.py test"""
from datetime import datetime, time, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from booking import services as svc
from booking.models import Appointment, Availability, Service, Staff, TimeOff, User


def next_monday_at(h, m=0):
    today = timezone.localdate()
    d = today + timedelta(days=(7 - today.weekday()) or 7)
    return timezone.make_aware(datetime.combine(d, time(h, m)))


class BookingRulesTest(TestCase):
    def setUp(self):
        self.cust = User.objects.create_user("c", password="x123456", role=User.Role.CUSTOMER)
        self.cust2 = User.objects.create_user("c2", password="x123456", role=User.Role.CUSTOMER)
        su = User.objects.create_user("s", password="x123456", role=User.Role.STAFF)
        su2 = User.objects.create_user("s2", password="x123456", role=User.Role.STAFF)
        self.cut = Service.objects.create(name="Cắt", duration_minutes=30)
        self.perm = Service.objects.create(name="Uốn", duration_minutes=90)
        self.staff = Staff.objects.create(user=su)
        self.staff.services.set([self.cut, self.perm])
        self.other = Staff.objects.create(user=su2)
        self.other.services.set([self.cut])
        for st in (self.staff, self.other):
            Availability.objects.create(staff=st, weekday=0, start_time=time(8), end_time=time(12))

    def book(self, h, m=0, service=None, staff=None, cust=None):
        return svc.create_appointment(cust or self.cust, (staff or self.staff).pk,
                                      (service or self.cut).pk, next_monday_at(h, m))

    def test_end_time_is_computed(self):
        a = self.book(9, service=self.perm)
        self.assertEqual(a.end - a.start, timedelta(minutes=90))

    def test_outside_working_hours_rejected(self):
        with self.assertRaises(svc.BookingError):
            self.book(11, 45)  # 11:45 + 30' vượt 12:00

    def test_overlap_rejected_even_with_different_start(self):
        self.book(9, service=self.perm)  # 9:00–10:30
        with self.assertRaises(svc.BookingError):
            self.book(10, 0, cust=self.cust2)

    def test_back_to_back_allowed_and_other_staff_free(self):
        self.book(9)            # 9:00–9:30
        self.book(9, 30)        # 9:30–10:00 nối tiếp: hợp lệ
        self.book(9, staff=self.other, cust=self.cust2)  # thợ khác cùng giờ: hợp lệ

    def test_cancelled_frees_slot(self):
        a = self.book(9)
        svc.cancel_appointment(a, self.cust)
        self.book(9, cust=self.cust2)

    def test_time_off_blocks(self):
        TimeOff.objects.create(staff=self.staff, start=next_monday_at(10), end=next_monday_at(11))
        with self.assertRaises(svc.BookingError):
            self.book(10, 30)
        self.assertNotIn(next_monday_at(10, 30), svc.available_slots(self.staff, self.cut, next_monday_at(8).date()))

    def test_available_slots_exclude_busy(self):
        self.book(9)
        slots = svc.available_slots(self.staff, self.cut, next_monday_at(8).date())
        self.assertNotIn(next_monday_at(9), slots)
        self.assertNotIn(next_monday_at(8, 45), slots)  # 8:45–9:15 chồng lấn
        self.assertIn(next_monday_at(8, 30), slots)
        self.assertEqual(slots[-1], next_monday_at(11, 30))

    def test_failed_reschedule_keeps_old(self):
        a = self.book(9)
        self.book(10, cust=self.cust2)
        with self.assertRaises(svc.BookingError):
            svc.reschedule_appointment(a, self.cust, next_monday_at(10))
        a.refresh_from_db()
        self.assertEqual(a.start, next_monday_at(9))

    def test_staff_service_must_match(self):
        with self.assertRaises(svc.BookingError):
            self.book(9, service=self.perm, staff=self.other)

    def test_status_flow(self):
        a = self.book(9)
        with self.assertRaises(svc.BookingError):
            svc.complete_appointment(a, self.staff.user)  # chưa xác nhận
        svc.confirm_appointment(a, self.staff.user)
        self.assertEqual(a.status, Appointment.Status.CONFIRMED)
        with self.assertRaises(svc.BookingError):
            svc.confirm_appointment(a, self.other.user)  # không phải thợ được giao


class PermissionTest(TestCase):
    def test_customer_cannot_open_admin_pages_or_others_appointment(self):
        c = User.objects.create_user("c", password="x123456", role=User.Role.CUSTOMER)
        other = User.objects.create_user("o", password="x123456", role=User.Role.CUSTOMER)
        su = User.objects.create_user("s", password="x123456", role=User.Role.STAFF)
        sv = Service.objects.create(name="Cắt", duration_minutes=30)
        st = Staff.objects.create(user=su)
        start = timezone.now() + timedelta(days=1)
        a = Appointment.objects.create(customer=other, staff=st, service=sv, start=start,
                                       end=start + timedelta(minutes=30))
        self.client.login(username="c", password="x123456")
        self.assertEqual(self.client.get(reverse("service_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("staff_schedule")).status_code, 403)
        self.assertEqual(self.client.get(reverse("appointment_detail", args=[a.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("book")).status_code, 200)
