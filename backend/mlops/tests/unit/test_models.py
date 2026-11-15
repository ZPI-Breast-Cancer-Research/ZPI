import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from mlops.models import ModelVersion


@pytest.mark.django_db
def test_model_version_default_values():
    model = ModelVersion.objects.create(name="segmentation", version="1.0")

    assert model.module == ModelVersion.ModuleChoices.SEG
    assert model.status == ModelVersion.StatusChoices.NEW
    assert model.editable
    assert model.decided_by is None
    assert model.proposed_by is None
    assert model.proposed_at is None
    assert model.reason == ""
    assert model.restore is False
    assert model.mlflow_run_id == ""
    assert model.dataset == ""
    assert model.metrics == {}
    assert model.metrics_cases is None
    assert model.periods.count() == 0


@pytest.mark.django_db
def test_model_version_string_representation():
    model = ModelVersion.objects.create(
        module=ModelVersion.ModuleChoices.SEG, name="segmentation", version="1.0"
    )

    assert str(model) == "seg v1.0"


@pytest.mark.django_db
def test_model_version_extraction_string_representation():
    model = ModelVersion.objects.create(
        module=ModelVersion.ModuleChoices.EXT, name="extraction", version="2.0"
    )

    assert str(model) == "ext v2.0"


@pytest.mark.django_db
def test_model_version_unique_constraint():
    ModelVersion.objects.create(module="seg", name="model1", version="1.0")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ModelVersion.objects.create(module="seg", name="model2", version="1.0")


@pytest.mark.django_db
def test_same_version_different_modules_allowed():
    ModelVersion.objects.create(module="seg", name="segmentation", version="1.0")

    ModelVersion.objects.create(module="ext", name="extraction", version="1.0")

    assert ModelVersion.objects.filter(version="1.0").count() == 2


@pytest.mark.django_db
@pytest.mark.parametrize("status", ModelVersion.StatusChoices.values)
def test_model_version_status_choices(status):
    model = ModelVersion.objects.create(name="test", version=f"status-{status}", status=status)

    assert model.status == status


@pytest.mark.django_db
@pytest.mark.parametrize("module", ModelVersion.ModuleChoices.values)
def test_model_version_module_choices(module):
    model = ModelVersion.objects.create(name="test", version=f"module-{module}", module=module)

    assert model.module == module


def test_model_version_table_does_not_collide_with_mlflow():
    assert ModelVersion._meta.db_table == "module_version"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status",
    [s for s in ModelVersion.StatusChoices.values if s != ModelVersion.StatusChoices.NEW],
)
def test_only_a_new_version_is_editable(status):
    model = ModelVersion.objects.create(name="test", version=f"locked-{status}", status=status)

    assert not model.editable


@pytest.fixture
def admin(db):
    return get_user_model().objects.create_user(username="admin", password="x", role="admin")


@pytest.mark.django_db
def test_put_in_use_opens_a_period_and_closes_the_replaced_one(admin):
    old = ModelVersion.objects.create(name="seg", version="1")
    new = ModelVersion.objects.create(name="seg", version="2")
    old.put_in_use(admin)

    new.put_in_use(admin, reason="better dice")

    old.refresh_from_db()
    new.refresh_from_db()
    assert old.status == ModelVersion.StatusChoices.ARCHIVED
    assert old.periods.get().ended_at is not None
    assert new.status == ModelVersion.StatusChoices.PRODUCTION
    assert new.reason == "better dice"
    assert new.decided_by == admin
    period = new.periods.get()
    assert period.ended_at is None
    assert period.decided_by == admin


@pytest.mark.django_db
def test_restored_version_has_a_period_for_every_time_it_was_in_use(admin):
    first = ModelVersion.objects.create(name="seg", version="1")
    second = ModelVersion.objects.create(name="seg", version="2")
    first.put_in_use(admin)
    second.put_in_use(admin)

    first.put_in_use(admin)

    assert first.periods.count() == 2
    assert first.periods.filter(ended_at__isnull=True).count() == 1
    assert second.periods.get().ended_at is not None


@pytest.mark.django_db
def test_put_in_use_leaves_other_modules_alone(admin):
    extraction = ModelVersion.objects.create(module="ext", name="ext", version="1")
    extraction.put_in_use(admin)

    ModelVersion.objects.create(module="seg", name="seg", version="1").put_in_use(admin)

    extraction.refresh_from_db()
    assert extraction.status == ModelVersion.StatusChoices.PRODUCTION
    assert extraction.periods.get().ended_at is None


@pytest.mark.django_db
def test_put_in_use_twice_keeps_one_open_period(admin):
    model = ModelVersion.objects.create(name="seg", version="1")
    model.put_in_use(admin)

    model.put_in_use(admin)

    assert model.periods.count() == 1
