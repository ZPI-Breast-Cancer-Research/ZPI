from django.urls import path
from .views import approve_segmentation, get_segmentation_result

urlpatterns = [
    path("studies/<int:study_id>/result/", get_segmentation_result, name="segmentation-result"),
    path("studies/<int:study_id>/approve/", approve_segmentation, name="segmentation-approve"),
]
