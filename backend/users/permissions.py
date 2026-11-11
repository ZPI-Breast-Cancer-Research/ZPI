from typing import Dict, List, Union
from functools import wraps
from rest_framework.response import Response
from rest_framework import status

PERMISSIONS: Dict[str, List[str]] = {
    "review": ["radiologist", "admin"],
    "addStudies": ["radiologist", "admin"],
    "viewModels": ["researcher", "admin"],
    "manageModels": ["admin", "researcher"],
    "administer": ["admin"],
}


def user_has_permission(role: str, permission: str) -> bool:
    return role in PERMISSIONS.get(permission, [])


def require_permission(perm_name: Union[str, List[str]]):
    required = [perm_name] if isinstance(perm_name, str) else list(perm_name)

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user or not request.user.is_authenticated:
                return Response({"detail": "Wymagane logowanie"}, status=status.HTTP_401_UNAUTHORIZED)
            role = getattr(request.user, "role", None)
            # user needs at least one of the listed permissions
            if not any(user_has_permission(role, p) for p in required):
                return Response({"detail": "Brak uprawnień"}, status=status.HTTP_403_FORBIDDEN)
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator