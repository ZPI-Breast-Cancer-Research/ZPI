import pytest

from extraction.models import ExtractionResult, SourceChoices, StatusChoices


def test_reports_live_in_the_reports_table():
    assert ExtractionResult._meta.db_table == "reports"


@pytest.mark.parametrize(
    "name, source",
    [
        ("opis.txt", SourceChoices.TEXT),
        ("OPIS.TXT", SourceChoices.TEXT),
        ("skan.jpg", SourceChoices.SCAN),
        ("skan.JPEG", SourceChoices.SCAN),
        ("reports/abc/skan.png", SourceChoices.SCAN),
    ],
)
def test_source_of_an_uploaded_file(name, source):
    assert SourceChoices.of_file(name) == source


@pytest.mark.django_db
def test_report_can_wait_as_uploaded_without_processing():
    report = ExtractionResult.objects.create(
        report_path="reports/abc/opis.txt",
        source=SourceChoices.TEXT,
        status=StatusChoices.UPLOADED,
    )

    report.refresh_from_db()

    assert report.status == StatusChoices.UPLOADED
    assert report.requested_by is None
    assert not hasattr(report, "lesion_answers")
