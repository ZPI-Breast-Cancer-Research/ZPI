from django.urls import path

from . import views

urlpatterns = [
    path("studies", views.study_list, name="study-list"),
]
