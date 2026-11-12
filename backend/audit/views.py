from rest_framework.decorators import api_view
from rest_framework.response import Response

from users.permissions import require_permission

from .models import AuditLog
from .serializers import AuditLogSerializer


@api_view(["GET"])
@require_permission("administer")
def audit_logs_list(request):
    """The latest entries of the audit log; only the admin sees it (Settings page)."""
    logs = AuditLog.objects.select_related("user")[:200]
    return Response(AuditLogSerializer(logs, many=True).data)
