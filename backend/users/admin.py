from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Rola systemowa", {"fields": ("role", "is_first_login")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Rola systemowa", {"fields": ("role", "is_first_login")}),
    )
    list_display = ("username", "email", "first_name", "last_name", "role", "is_staff")
    list_filter = ("role", "is_staff", "is_superuser")