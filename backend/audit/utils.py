from .models import AuditLog

def record_audit(request, kind: str, object: str, detail: str = None, fallback_login=None, fallback_name=None):
    user = request.user if request and request.user.is_authenticated else None
    ip = request.META.get("REMOTE_ADDR") if request else None
    
    AuditLog.objects.create(
        user=user if (user and user.is_authenticated) else None,
        fallback_login=fallback_login if not (user and user.is_authenticated) else None,
        fallback_name=fallback_name if not (user and user.is_authenticated) else None,
        kind=kind,
        object=object,
        detail=detail,
        ip_address=ip
    )