from django.urls import path
from .views import (
    segmentation_overview,
    extraction_overview,
    promote_model,
    reject_model,
    rollback_model,
    start_training,
)

urlpatterns = [
    path('segmentation/', segmentation_overview, name='segmentation-overview'),
    path('extraction/', extraction_overview, name='extraction-overview'),
    path('training/start/', start_training, name='start-training'),
    path('<str:version>/promote/', promote_model, name='promote-model'),
    path('<str:version>/reject/', reject_model, name='reject-model'),
    path('<str:version>/rollback/', rollback_model, name='rollback-model'),
]
