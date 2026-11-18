"""An extraction version is one configuration (LLM, prompt, few-shot examples): a new one starts
from the version in use, changes only as a draft, and takes examples from verified reports."""

from unittest import mock

import pytest
import requests
from audit.models import AuditLog
from django.urls import reverse
from extraction.models import ExtractionResult, SourceChoices, StatusChoices
from mlops.models import ModelVersion

EXAMPLE = {"report": "Opis przykładowy.", "output": {"wniosek": {"birads": "2"}}}


@pytest.fixture
def in_use(db):
    """The version 1 the migration made (mlops 0006), with a known configuration."""
    version, _ = ModelVersion.objects.get_or_create(
        module="ext", version="1", defaults={"name": "extraction", "status": "production"}
    )
    version.llm_model = "bielik"
    version.prompt_version = "v6"
    version.structured_output = True
    version.few_shot_examples = [EXAMPLE]
    version.save()
    return version


def _detail(version):
    return reverse("extraction-version-detail", kwargs={"version": version})


@pytest.mark.django_db
def test_the_migration_puts_the_current_configuration_into_version_1():
    version = ModelVersion.objects.get(module="ext", version="1")

    assert version.status == ModelVersion.StatusChoices.PRODUCTION
    assert version.prompt_version == "v6"
    [example] = version.few_shot_examples
    assert example["report"].startswith("Opis badania")
    assert "wniosek" in example["output"]


@pytest.mark.django_db
def test_a_new_version_copies_the_one_in_use(client_as, in_use):
    # Act
    response = client_as("researcher").post(reverse("extraction-version-create"))

    # Assert
    assert response.status_code == 201
    assert (response.data["version"], response.data["status"]) == ("2", "new")
    assert response.data["llmModel"] == "bielik"
    assert response.data["fewShotExamples"] == [EXAMPLE]
    assert AuditLog.objects.get().kind == "version_created"


@pytest.mark.django_db
def test_a_taken_version_number_is_refused(client_as, in_use):
    response = client_as("researcher").post(reverse("extraction-version-create"), {"version": "1"})

    assert response.status_code == 400


@pytest.mark.django_db
def test_a_radiologist_cannot_create_a_version(client_as, in_use):
    response = client_as("radiologist").post(reverse("extraction-version-create"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_a_draft_takes_another_model_and_examples(client_as, in_use):
    # Arrange
    client = client_as("researcher")
    client.post(reverse("extraction-version-create"))
    examples = [EXAMPLE, {"report": "Drugi opis.", "output": {"zmiany": []}}]

    # Act
    response = client.patch(
        _detail("2"),
        {"llm_model": "qwen", "structured_output": False, "few_shot_examples": examples},
        format="json",
    )

    # Assert
    assert response.status_code == 200
    draft = ModelVersion.objects.get(module="ext", version="2")
    assert (draft.llm_model, draft.structured_output) == ("qwen", False)
    assert draft.few_shot_examples == examples
    # the version in use is untouched: changing the examples always means a new version
    in_use.refresh_from_db()
    assert in_use.few_shot_examples == [EXAMPLE]


@pytest.mark.django_db
def test_a_version_that_is_not_a_draft_does_not_change(client_as, in_use):
    response = client_as("admin").patch(_detail("1"), {"llm_model": "qwen"}, format="json")

    assert response.status_code == 409
    assert response.data["code"] == "not_editable"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "examples",
    ["tekst", [{"report": "", "output": {}}], [{"report": "Opis"}], [{"output": {}}]],
)
def test_malformed_examples_are_refused(client_as, in_use, examples):
    client = client_as("researcher")
    client.post(reverse("extraction-version-create"))

    response = client.patch(_detail("2"), {"few_shot_examples": examples}, format="json")

    assert response.status_code == 400


@pytest.mark.django_db
def test_a_verified_report_becomes_an_example_with_its_accepted_form(client_as, in_use):
    # Arrange
    client = client_as("researcher")
    client.post(reverse("extraction-version-create"))
    report = ExtractionResult.objects.create(
        status=StatusChoices.CORRECTED,
        report_path="reports/a/opis.txt",
        ocr_text="Tekst zweryfikowanego opisu.",
        accepted_report={"wniosek": {"birads": "4a"}},
    )

    # Act
    response = client.post(
        reverse("extraction-version-examples", kwargs={"version": "2"}),
        {"report_id": report.id},
        format="json",
    )
    again = client.post(
        reverse("extraction-version-examples", kwargs={"version": "2"}),
        {"report_id": report.id},
        format="json",
    )

    # Assert
    assert response.status_code == 201
    assert response.data["fewShotExamples"][-1] == {
        "report": "Tekst zweryfikowanego opisu.",
        "output": {"wniosek": {"birads": "4a"}},
        "report_id": report.id,
    }
    assert again.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize(
    "fields",
    [
        {"status": StatusChoices.COMPLETED, "ocr_text": "x", "accepted_report": {"a": 1}},
        {"status": StatusChoices.APPROVED, "ocr_text": "", "source": SourceChoices.MANUAL},
    ],
)
def test_only_a_verified_report_with_text_becomes_an_example(client_as, in_use, fields):
    client = client_as("researcher")
    client.post(reverse("extraction-version-create"))
    report = ExtractionResult.objects.create(**{"accepted_report": {"a": 1}, **fields})

    response = client.post(
        reverse("extraction-version-examples", kwargs={"version": "2"}),
        {"report_id": report.id},
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_the_examples_of_a_version_for_the_models_screen(client_as, in_use):
    client = client_as("researcher")
    client.post(reverse("extraction-version-create"))
    client.patch(
        _detail("2"),
        {"few_shot_examples": [EXAMPLE, {"report": "Nowy opis.\nDruga linia", "output": {}}]},
        format="json",
    )

    response = client.get(reverse("extraction-few-shot", kwargs={"version": "2"}))

    assert [(e["title"], e["isNew"]) for e in response.data] == [
        ("Opis przykładowy.", False),
        ("Nowy opis.", True),
    ]


@pytest.mark.django_db
def test_an_example_report_is_left_out_of_the_statistics_of_its_version(client_as, in_use):
    # Arrange: two verified reports of the version in use, one of them is its example
    rows = [
        ExtractionResult.objects.create(
            model=in_use,
            status=StatusChoices.APPROVED,
            generated_report={"birads": "3"},
            accepted_report={"birads": "3"},
        )
        for _ in range(2)
    ]
    in_use.few_shot_examples = [{**EXAMPLE, "report_id": rows[0].id}]
    in_use.save()

    # Act
    response = client_as("researcher").get(reverse("extraction-overview"))

    # Assert
    assert response.json()["verifiedDescriptions"] == 1


@pytest.mark.django_db
def test_the_models_of_the_llm_server_are_listed(client_as, settings):
    settings.LLM_BASE_URL = "http://llm.invalid/v1"
    answer = mock.Mock(status_code=200)
    answer.json.return_value = {"data": [{"id": "bielik"}, {"id": "qwen"}]}

    with mock.patch("mlops.extraction_versions.requests.get", return_value=answer) as get:
        response = client_as("researcher").get(reverse("extraction-llm-models"))

    assert response.status_code == 200
    assert response.data == ["bielik", "qwen"]
    get.assert_called_once_with("http://llm.invalid/v1/models", timeout=(2, 5))


@pytest.mark.django_db
def test_an_unreachable_llm_server_is_503(client_as, settings):
    settings.LLM_BASE_URL = "http://llm.invalid/v1"

    with mock.patch(
        "mlops.extraction_versions.requests.get", side_effect=requests.ConnectionError("down")
    ):
        response = client_as("researcher").get(reverse("extraction-llm-models"))

    assert response.status_code == 503
    assert response.data["code"] == "llm_unavailable"
