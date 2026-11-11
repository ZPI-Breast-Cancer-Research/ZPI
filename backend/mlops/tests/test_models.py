import pytest
from django.db import IntegrityError, transaction

from mlops.models import ModelVersion


@pytest.mark.django_db
def test_model_version_default_values():
    model = ModelVersion.objects.create(
        name="segmentation",
        version="1.0"
    )

    assert model.module == ModelVersion.ModuleChoices.SEG
    assert model.status == ModelVersion.StatusChoices.CANDIDATE
    assert model.decision == ModelVersion.DecisionChoices.PENDING
    assert model.activated_at is None
    assert model.deactivated_at is None
    assert model.decided_by is None
    assert model.mlflow_run_id == ""
    assert model.dice is None
    assert model.hd95 is None
    assert model.f1 is None


@pytest.mark.django_db
def test_model_version_string_representation():
    model = ModelVersion.objects.create(
        module=ModelVersion.ModuleChoices.SEG,
        name="segmentation",
        version="1.0"
    )

    assert str(model) == "seg v1.0"


@pytest.mark.django_db
def test_model_version_extraction_string_representation():
    model = ModelVersion.objects.create(
        module=ModelVersion.ModuleChoices.EXT,
        name="extraction",
        version="2.0"
    )

    assert str(model) == "ext v2.0"


@pytest.mark.django_db
def test_model_version_unique_constraint():
    ModelVersion.objects.create(
        module="seg",
        name="model1",
        version="1.0"
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ModelVersion.objects.create(
                module="seg",
                name="model2",
                version="1.0"
            )


@pytest.mark.django_db
def test_same_version_different_modules_allowed():
    ModelVersion.objects.create(
        module="seg",
        name="segmentation",
        version="1.0"
    )

    ModelVersion.objects.create(
        module="ext",
        name="extraction",
        version="1.0"
    )

    assert ModelVersion.objects.filter(version="1.0").count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status",
    ModelVersion.StatusChoices.values
)
def test_model_version_status_choices(status):
    model = ModelVersion.objects.create(
        name="test",
        version=f"status-{status}",
        status=status
    )

    assert model.status == status


@pytest.mark.django_db
@pytest.mark.parametrize(
    "decision",
    ModelVersion.DecisionChoices.values
)
def test_model_version_decision_choices(decision):
    model = ModelVersion.objects.create(
        name="test",
        version=f"decision-{decision}",
        decision=decision
    )

    assert model.decision == decision


@pytest.mark.django_db
@pytest.mark.parametrize(
    "module",
    ModelVersion.ModuleChoices.values
)
def test_model_version_module_choices(module):
    model = ModelVersion.objects.create(
        name="test",
        version=f"module-{module}",
        module=module
    )

    assert model.module == module
