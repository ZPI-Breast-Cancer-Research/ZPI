from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    """Custom user model – defined up front so it can be extended later (roles etc.)."""
    pwz_number = models.CharField(max_length=7, unique=True, null=True, blank=True)