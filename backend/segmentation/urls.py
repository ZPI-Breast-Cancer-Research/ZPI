from django.urls import path

from .views import get_segmentation_result

urlpatterns = [
    path("studies/<int:study_id>/result/", get_segmentation_result, name="segmentation-result"),
]
