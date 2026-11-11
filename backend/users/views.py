from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from .models import User
import random
from .permissions import require_permission

def generate_temporary_password(length=14):
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choices(alphabet, k=length))


@api_view(["POST"])
@permission_classes([AllowAny])
@ensure_csrf_cookie
def log_in(request):
    login_str = request.data.get("login")
    password = request.data.get("password")

    if not login_str or not password:
        return Response(
            {"detail": "Brak loginu lub hasła."}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    user = authenticate(request, username=login_str, password=password)

    if user is None:
        return Response(
            {"detail": "bad credentials"}, 
            status=status.HTTP_401_UNAUTHORIZED
        )

    if getattr(user, "is_first_login", False):
        return Response({
            "kind": "first-login", 
            "login": user.username
        })

    login(request, user)

    return Response({
        "kind": "signed-in",
        "user": {
            "login": user.username,
            "name": f"{user.first_name} {user.last_name}".strip() or user.username,
            "role": getattr(user, "role", "radiologist")
        }
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def set_first_password(request):
    login_str = request.data.get("login")
    _temporary = request.data.get("temporary")
    new_password = request.data.get("password")

    if not login_str or not new_password:
        return Response(
            {"detail": "Wymagany login i nowe hasło."}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user = User.objects.get(username=login_str)
        user.set_password(new_password)
        if hasattr(user, "is_first_login"):
            user.is_first_login = False
            
        user.save()

        return Response({
            "login": user.username,
            "name": f"{user.first_name} {user.last_name}".strip() or user.username,
            "role": getattr(user, "role", "radiologist")
        }, status=status.HTTP_200_OK)

    except User.DoesNotExist:
        return Response(
            {"detail": "Użytkownik nie istnieje."}, 
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(["POST"])
@permission_classes([AllowAny])
def sign_out(request):
    logout(request)
    return Response(status=status.HTTP_204_NO_CONTENT)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_profile(request):
    user = request.user
    return Response({
        "name": f"{user.first_name} {user.last_name}".strip() or user.username,
        "login": user.username,
        "email": user.email or f"{user.username}@szpital.pl",
        "role": getattr(user, "role", "radiologist"),
        "pwz": getattr(user, "pwz", None),
    })


@api_view(["GET", "POST"])
@require_permission(["administer"])
def manage_users(request):
    if request.method == "GET":
        users = User.objects.all()
        data = []
        for u in users:
            state = "active"
            if not u.is_active:
                state = "blocked"
            elif getattr(u, "is_first_login", False):
                state = "temporary"

            data.append({
                "id": str(u.id),
                "name": f"{u.first_name} {u.last_name}".strip() or u.username,
                "login": u.username,
                "email": u.email or f"{u.username}@szpital.pl",
                "role": getattr(u, "role", "radiologist"),
                "pwz": getattr(u, "pwz", None),
                "state": state,
                "lastLogin": u.last_login.strftime("%Y-%m-%d") if u.last_login else None
            })
        return Response(data)

    if request.method == "POST":
        draft = request.data
        login_str = draft.get("login")
        
        if User.objects.filter(username=login_str).exists():
            return Response({"detail": "login-taken"}, status=status.HTTP_400_BAD_REQUEST)

        temp_password = generate_temporary_password()
        
        full_name = draft.get("name", "")
        parts = full_name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

        user = User.objects.create_user(
            username=login_str,
            password=temp_password,
            email=draft.get("email", f"{login_str}@szpital.pl"),
            first_name=first_name,
            last_name=last_name,
            role=draft.get("role", "radiologist"),
            pwz=draft.get("pwz", None),
            is_first_login=True
        )

        return Response({"password": temp_password}, status=status.HTTP_201_CREATED)


@api_view(["PUT", "PATCH"])
@require_permission(["administer"])
def update_user(request, user_id):
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"detail": "Użytkownik nie znaleziony."}, status=status.HTTP_404_NOT_FOUND)

    data = request.data
    if "name" in data:
        parts = data["name"].split(" ", 1)
        user.first_name = parts[0]
        user.last_name = parts[1] if len(parts) > 1 else ""
    if "email" in data:
        user.email = data["email"]
    if "role" in data:
        user.role = data["role"]
    if "pwz" in data:
        user.pwz = data["pwz"]
        
    user.save()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@require_permission(["administer"])
def set_blocked(request, user_id):
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"detail": "Użytkownik nie znaleziony."}, status=status.HTTP_404_NOT_FOUND)
    blocked = request.data.get("blocked", False)
    user.is_active = not blocked
    user.save()

    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@require_permission(["administer"])
def reset_password(request, user_id):
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"detail": "Użytkownik nie znaleziony."}, status=status.HTTP_404_NOT_FOUND)

    temp_password = generate_temporary_password()
    user.set_password(temp_password)
    user.is_first_login = True
    user.is_active = True
    user.save()

    return Response({"password": temp_password})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def change_password(request):
    user = request.user
    current_password = request.data.get("current")
    new_password = request.data.get("next")

    if not user.check_password(current_password):
        return Response({"detail": "Stare hasło jest niepoprawne."}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(new_password)
    user.is_first_login = False
    user.save()
    
    return Response(status=status.HTTP_204_NO_CONTENT)