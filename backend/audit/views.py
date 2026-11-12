from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import AuditLog
from .serializers import AuditLogSerializer

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def audit_logs_list(request):
    logs = AuditLog.objects.all()[:200]
    serializer = AuditLogSerializer(logs, many=True)
    return Response(serializer.data)