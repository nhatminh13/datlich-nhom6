from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Appointment, AppointmentLog, Availability, Service, Staff, TimeOff, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Vai trò", {"fields": ("role", "phone")}),)
    list_display = ("username", "first_name", "role", "phone", "is_active")
    list_filter = ("role",)


class AvailabilityInline(admin.TabularInline):
    model = Availability
    extra = 0


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ("__str__", "title", "is_active")
    inlines = [AvailabilityInline]


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "staff", "service", "start", "end", "status")
    list_filter = ("status", "staff")


admin.site.register([Service, TimeOff, AppointmentLog])
