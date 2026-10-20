from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Medical Information", {"fields": ("pwz_number",)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Medical Information", {"fields": ("pwz_number",)}),
    )
    list_display = ("username", "email", "first_name", "last_name", "pwz_number", "is_staff")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("username", "email", "pwz_number")
