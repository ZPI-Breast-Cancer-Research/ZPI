from django.contrib import admin
from django.urls import include, path

from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health", views.health, name="health"),
    path("api/auth/orthanc", views.orthanc_auth, name="orthanc-auth"),
    path("api/", include("patients.urls")),
    path("api/", include("users.urls")),
    path("api/segmentation/", include("segmentation.urls")),
    path("api/review/", include("review.urls")),
    path("api/models/", include("mlops.urls")),
]
