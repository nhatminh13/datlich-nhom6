from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dang-ky/", views.register, name="register"),
    path("dang-nhap/", auth_views.LoginView.as_view(template_name="booking/login.html"), name="login"),
    path("dang-xuat/", auth_views.LogoutView.as_view(), name="logout"),

    # Khách hàng
    path("dat-lich/", views.book, name="book"),
    path("lich-cua-toi/", views.my_appointments, name="my_appointments"),
    path("lich-hen/<int:pk>/", views.appointment_detail, name="appointment_detail"),
    path("lich-hen/<int:pk>/huy/", views.appointment_cancel, name="appointment_cancel"),
    path("lich-hen/<int:pk>/doi/", views.appointment_reschedule, name="appointment_reschedule"),

    # Nhân viên / Quản trị
    path("lich-lam-viec/", views.staff_schedule, name="staff_schedule"),
    path("lich-hen/<int:pk>/xac-nhan/", views.appointment_confirm, name="appointment_confirm"),
    path("lich-hen/<int:pk>/hoan-tat/", views.appointment_complete, name="appointment_complete"),
    path("thong-ke/", views.statistics, name="statistics"),

    # Quản trị
    path("quan-tri/dich-vu/", views.service_list, name="service_list"),
    path("quan-tri/dich-vu/them/", views.service_edit, name="service_add"),
    path("quan-tri/dich-vu/<int:pk>/sua/", views.service_edit, name="service_edit"),
    path("quan-tri/nhan-vien/", views.staff_list, name="staff_list"),
    path("quan-tri/nhan-vien/them/", views.staff_edit, name="staff_add"),
    path("quan-tri/nhan-vien/<int:pk>/sua/", views.staff_edit, name="staff_edit"),
    path("quan-tri/nhan-vien/<int:pk>/gio-lam/", views.staff_hours, name="staff_hours"),
    path("quan-tri/gio-lam/<int:pk>/xoa/", views.availability_delete, name="availability_delete"),
    path("quan-tri/nghi/<int:pk>/xoa/", views.timeoff_delete, name="timeoff_delete"),
]
