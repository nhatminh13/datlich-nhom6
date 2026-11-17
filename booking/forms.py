from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Availability, Service, Staff, TimeOff, User


class BootstrapMixin:
    def _style(self):
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, (forms.CheckboxInput,)):
                w.attrs.setdefault("class", "form-check-input")
            elif isinstance(w, forms.CheckboxSelectMultiple):
                pass
            elif isinstance(w, forms.Select):
                w.attrs.setdefault("class", "form-select")
            else:
                w.attrs.setdefault("class", "form-control")


class RegisterForm(BootstrapMixin, UserCreationForm):
    full_name = forms.CharField(label="Họ và tên", max_length=150)
    phone = forms.RegexField(label="Số điện thoại", regex=r"^0\d{9,10}$",
                             error_messages={"invalid": "Số điện thoại gồm 10–11 chữ số, bắt đầu bằng 0."})
    email = forms.EmailField(label="Email", required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "full_name", "phone", "email")

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = self.cleaned_data["full_name"]
        user.phone = self.cleaned_data["phone"]
        user.email = self.cleaned_data.get("email", "")
        user.role = User.Role.CUSTOMER
        if commit:
            user.save()
        return user


class ServiceForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Service
        fields = ["name", "description", "duration_minutes", "price", "is_active"]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()

    def clean_duration_minutes(self):
        d = self.cleaned_data["duration_minutes"]
        if d < 15 or d > 240 or d % 15:
            raise forms.ValidationError("Thời lượng từ 15 đến 240 phút và là bội số của 15.")
        return d


class StaffForm(BootstrapMixin, forms.Form):
    username = forms.CharField(label="Tên đăng nhập", max_length=150)
    password = forms.CharField(label="Mật khẩu", widget=forms.PasswordInput, required=False,
                               help_text="Để trống khi sửa nếu không đổi mật khẩu.")
    full_name = forms.CharField(label="Họ và tên", max_length=150)
    phone = forms.CharField(label="Số điện thoại", max_length=15, required=False)
    title = forms.CharField(label="Chức danh", max_length=50, initial="Thợ tóc")
    services = forms.ModelMultipleChoiceField(label="Dịch vụ đảm nhận", queryset=Service.objects.all(),
                                              widget=forms.CheckboxSelectMultiple, required=False)
    is_active = forms.BooleanField(label="Đang làm việc", required=False, initial=True)

    def __init__(self, *a, staff=None, **kw):
        self.staff = staff
        if staff and "initial" not in kw:
            kw["initial"] = {
                "username": staff.user.username, "full_name": staff.user.first_name,
                "phone": staff.user.phone, "title": staff.title,
                "services": staff.services.all(), "is_active": staff.is_active,
            }
        super().__init__(*a, **kw)
        self._style()
        if staff:
            self.fields["username"].disabled = True

    def clean_username(self):
        u = self.cleaned_data["username"]
        if not self.staff and User.objects.filter(username=u).exists():
            raise forms.ValidationError("Tên đăng nhập đã tồn tại.")
        return u

    def clean(self):
        data = super().clean()
        if not self.staff and not data.get("password"):
            self.add_error("password", "Vui lòng đặt mật khẩu cho nhân viên mới.")
        return data

    def save(self):
        d = self.cleaned_data
        if self.staff:
            user = self.staff.user
        else:
            user = User(username=d["username"], role=User.Role.STAFF)
        user.first_name, user.phone = d["full_name"], d["phone"]
        if d.get("password"):
            user.set_password(d["password"])  # mật khẩu được băm
        user.save()
        staff = self.staff or Staff(user=user)
        staff.title, staff.is_active = d["title"], d["is_active"]
        staff.save()
        staff.services.set(d["services"])
        return staff


class AvailabilityForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Availability
        fields = ["weekday", "start_time", "end_time"]
        widgets = {"start_time": forms.TimeInput(attrs={"type": "time"}),
                   "end_time": forms.TimeInput(attrs={"type": "time"})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()


class TimeOffForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = TimeOff
        fields = ["start", "end", "reason"]
        widgets = {"start": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                   "end": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._style()
