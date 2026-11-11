from django.contrib.auth.models import AbstractUser
from django.db import models

class Role(models.TextChoices):
    RADIOLOGIST = "radiologist", "Radiologist"
    RESEARCHER = "researcher", "Researcher"
    ADMIN = "admin", "Admin"

class User(AbstractUser):
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.RADIOLOGIST
    )
    is_first_login = models.BooleanField(default=False)
    pwz = models.CharField(
        max_length=20, 
        blank=True,
        null=True,
        unique=True,
        verbose_name="Numer PWZ"
    )

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = Role.ADMIN
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.role})"