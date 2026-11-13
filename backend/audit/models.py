from django.db import models
from users.models import User

class AuditKind(models.TextChoices):
    MASK_APPROVED = "mask_approved", "Zatwierdzenie maski"
    MASK_UNAPPROVED = "mask_unapproved", "Cofnięcie zatwierdzenia maski"
    FORM_APPROVED = "form_approved", "Potwierdzenie formularza"
    FORM_UNAPPROVED = "form_unapproved", "Cofnięcie potwierdzenia formularza"
    MODEL_PROPOSED = "model_proposed", "Propozycja modelu"
    PROPOSAL_WITHDRAWN = "proposal_withdrawn", "Wycofanie propozycji"
    MODEL_PROMOTED = "model_promoted", "Promocja modelu"
    MODEL_REJECTED = "model_rejected", "Odrzucenie modelu"
    MODEL_ROLLED_BACK = "model_rolled_back", "Cofnięcie wersji modelu"
    TRAINING_STARTED = "training_started", "Uruchomienie treningu"
    TRAINING_STOPPED = "training_stopped", "Zatrzymanie treningu"
    ACCOUNT_CREATED = "account_created", "Utworzenie konta"
    ACCOUNT_CHANGED = "account_changed", "Zmiana danych konta"
    ACCOUNT_BLOCKED = "account_blocked", "Zablokowanie konta"
    ACCOUNT_UNBLOCKED = "account_unblocked", "Odblokowanie konta"
    PASSWORD_RESET = "password_reset", "Reset hasła"
    LOGIN_FAILED = "login_failed", "Nieudane logowanie"
    STUDY_IMPORTED = "study_imported", "Badanie zaimportowane"
    STUDY_DELETED = "study_deleted", "Badanie usunięte"
    ATTACH_REPORT = "attach_report"

class AuditLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    
    fallback_login = models.CharField(max_length=150, blank=True, null=True)
    fallback_name = models.CharField(max_length=150, blank=True, null=True)
    
    kind = models.CharField(max_length=50, choices=AuditKind.choices)
    object = models.CharField(max_length=255)
    detail = models.TextField(blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Wpis dziennika zdarzeń"
        verbose_name_plural = "Dziennik zdarzeń"

    def __str__(self):
        return f"[{self.timestamp}] {self.kind} - {self.object}"