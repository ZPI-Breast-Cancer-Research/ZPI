from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user model – defined up front so it can be extended later (roles etc.)."""
