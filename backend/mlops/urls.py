from django.urls import path

from .extraction_versions import (
    add_example,
    create_version,
    few_shot,
    llm_models,
    promote_version,
    propose_version,
    reject_version,
    version_detail,
    withdraw_version,
)
from .views import (
    extraction_overview,
    promote_model,
    reject_model,
    rollback_model,
    segmentation_overview,
    start_training,
)

urlpatterns = [
    path("segmentation/", segmentation_overview, name="segmentation-overview"),
    path("extraction/", extraction_overview, name="extraction-overview"),
    # extraction versions: above "<str:version>/" so "extraction" is never read as a version
    path("extraction/llm-models/", llm_models, name="extraction-llm-models"),
    path("extraction/versions/", create_version, name="extraction-version-create"),
    path("extraction/versions/<str:version>/", version_detail, name="extraction-version-detail"),
    path(
        "extraction/versions/<str:version>/examples/",
        add_example,
        name="extraction-version-examples",
    ),
    path(
        "extraction/versions/<str:version>/propose/",
        propose_version,
        name="extraction-version-propose",
    ),
    path(
        "extraction/versions/<str:version>/withdraw/",
        withdraw_version,
        name="extraction-version-withdraw",
    ),
    path(
        "extraction/versions/<str:version>/promote/",
        promote_version,
        name="extraction-version-promote",
    ),
    path(
        "extraction/versions/<str:version>/reject/",
        reject_version,
        name="extraction-version-reject",
    ),
    path("extraction/few-shot/<str:version>/", few_shot, name="extraction-few-shot"),
    path("training/start/", start_training, name="start-training"),
    path("<str:version>/promote/", promote_model, name="promote-model"),
    path("<str:version>/reject/", reject_model, name="reject-model"),
    path("<str:version>/rollback/", rollback_model, name="rollback-model"),
]
