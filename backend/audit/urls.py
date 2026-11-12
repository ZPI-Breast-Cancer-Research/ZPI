from django.urls import path
from .views import audit_logs_list

urlpatterns = [
    path("logs/", audit_logs_list, name="audit-logs-list"),
]