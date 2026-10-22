from django.contrib import admin
from django.urls import include, path

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health", views.health, name="health"),
    path("api/auth/orthanc", views.orthanc_auth, name="orthanc-auth"),
    path("api/", include("patients.urls")),
]
