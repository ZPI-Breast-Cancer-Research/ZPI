from rest_framework import serializers
from .models import AuditLog

class AuditLogSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    at = serializers.DateTimeField(source="timestamp", format="%Y-%m-%dT%H:%M:%S")
    login = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ("id", "at", "login", "name", "kind", "object", "detail")

    def get_id(self, obj):
        return f"e{obj.id}"

    def get_login(self, obj):
        if obj.user:
            return getattr(obj.user, "username", str(obj.user))
        return obj.fallback_login or "?"

    def get_name(self, obj):
        if obj.user:
            return obj.user.get_full_name() or getattr(obj.user, "username", "—")
        return obj.fallback_name or "—"