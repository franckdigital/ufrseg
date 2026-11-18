from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseAdmin):
    list_display = ("phone", "full_name", "role", "is_author", "is_active")
    list_filter = ("role", "is_author", "is_active")
    search_fields = ("phone", "email", "first_name", "last_name", "matricule")
    ordering = ("last_name",)
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Identité", {"fields": ("first_name", "last_name", "email", "matricule", "avatar")}),
        ("Rôle", {"fields": ("role", "is_author", "is_class_rep", "classe")}),
        ("Droits", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("phone", "first_name", "last_name", "role", "password1", "password2")}),)
