import pytest
from unittest import mock
from django.utils import timezone

from review import views


# =========================================================
# _option
# =========================================================

def test_option_returns_mapped_value():
    result = views._option(
        {"okrągły": "Okrągły"},
        "okrągły"
    )

    assert result == "Okrągły"


def test_option_uses_capitalize_when_value_is_not_mapped():
    result = views._option({}, "nieregularny")

    assert result == "Nieregularny"


def test_option_converts_value_to_string():
    result = views._option({}, 123)

    assert result == "123"


# =========================================================
# _size_value
# =========================================================

def test_size_value_returns_largest_dimension():
    result = views._size_value({
        "wartosci": [2, 5, 3],
        "jednostka": "mm"
    })

    assert result == "5"


def test_size_value_returns_none_when_dimensions_are_missing():
    assert views._size_value(None) is None


def test_size_value_returns_none_when_values_are_missing():
    assert views._size_value({}) is None


def test_size_value_returns_none_when_values_are_empty():
    assert views._size_value({"wartosci": []}) is None


def test_size_value_formats_float_without_unnecessary_zeros():
    result = views._size_value({
        "wartosci": [2.5, 4.0, 3.2]
    })

    assert result == "4"


# =========================================================
# _size_text
# =========================================================

def test_size_text_returns_largest_dimension_with_unit():
    result = views._size_text({
        "wartosci": [2, 5, 3],
        "jednostka": "mm"
    })

    assert result == "5 mm"


def test_size_text_uses_default_unit():
    result = views._size_text({
        "wartosci": [4]
    })

    assert result == "4 mm"


def test_size_text_includes_qualifier():
    result = views._size_text({
        "wartosci": [4, 6],
        "jednostka": "mm",
        "kwalifikator": "około"
    })

    assert result == "około 6 mm"


def test_size_text_does_not_include_exact_qualifier():
    result = views._size_text({
        "wartosci": [4],
        "jednostka": "mm",
        "kwalifikator": "dokładny"
    })

    assert result == "4 mm"


def test_size_text_returns_none_for_missing_dimensions():
    assert views._size_text(None) is None


def test_size_text_returns_none_for_empty_values():
    assert views._size_text({"wartosci": []}) is None


# =========================================================
# _dicom_date
# =========================================================

def test_dicom_date_converts_valid_date():
    assert views._dicom_date("20261026") == "2026-10-26"


def test_dicom_date_returns_empty_string_for_none():
    assert views._dicom_date(None) == ""


def test_dicom_date_returns_empty_string_for_empty_string():
    assert views._dicom_date("") == ""


def test_dicom_date_returns_empty_string_for_invalid_length():
    assert views._dicom_date("202610") == ""


# =========================================================
# _user_name
# =========================================================

def test_user_name_returns_first_and_last_name():
    user = mock.Mock(
        first_name="Jan",
        last_name="Kowalski",
        username="jkowalski"
    )

    assert views._user_name(user) == "Jan Kowalski"


def test_user_name_falls_back_to_username():
    user = mock.Mock(
        first_name="",
        last_name="",
        username="jkowalski"
    )

    assert views._user_name(user) == "jkowalski"


def test_user_name_strips_whitespace():
    user = mock.Mock(
        first_name=" Jan ",
        last_name=" Kowalski ",
        username="jkowalski"
    )

    assert views._user_name(user) == "Jan   Kowalski"


def test_user_name_returns_empty_string_for_none():
    assert views._user_name(None) == ""


# =========================================================
# _main_lesion
# =========================================================

def test_main_lesion_returns_highest_birads():
    report = {
        "zmiany": [
            {"birads": "2"},
            {"birads": "4"},
            {"birads": "5"},
            {"birads": "3"},
        ]
    }

    result = views._main_lesion(report)

    assert result == {"birads": "5"}


def test_main_lesion_returns_first_lesion_when_birads_are_equal():
    first = {"birads": "4", "id": 1}
    second = {"birads": "4", "id": 2}

    result = views._main_lesion({
        "zmiany": [first, second]
    })

    assert result == first


def test_main_lesion_returns_none_when_there_are_no_lesions():
    assert views._main_lesion({"zmiany": []}) is None


def test_main_lesion_returns_none_when_zmiany_are_missing():
    assert views._main_lesion({}) is None


def test_main_lesion_unknown_birads_has_lowest_priority():
    unknown = {"birads": "unknown"}
    known = {"birads": "2"}

    result = views._main_lesion({
        "zmiany": [unknown, known]
    })

    assert result == known


# =========================================================
# _as_fields
# =========================================================

def test_as_fields_converts_flat_report():
    report = {
        "birads": "4C",
        "location": "KGZ",
        "size": "12",
        "shape": "Owalny",
        "margin": "Gładki",
        "curve": "Typ 1",
    }

    result = views._as_fields(report)

    assert result == report


def test_as_fields_extracts_value_from_dictionary():
    report = {
        "birads": {"value": "4C"},
        "size": {"value": "12"},
    }

    result = views._as_fields(report)

    assert result == {
        "birads": "4C",
        "size": "12",
    }


def test_as_fields_ignores_fields_with_none_values():
    report = {
        "birads": "4C",
        "size": None,
    }

    result = views._as_fields(report)

    assert result == {"birads": "4C"}


def test_as_fields_converts_values_to_strings():
    report = {
        "birads": 4,
        "size": 12,
    }

    result = views._as_fields(report)

    assert result == {
        "birads": "4",
        "size": "12",
    }


def test_as_fields_returns_empty_dict_for_non_dictionary():
    assert views._as_fields(None) == {}
    assert views._as_fields([]) == {}
    assert views._as_fields("report") == {}


# =========================================================
# _fields_from_schema
# =========================================================

def test_fields_from_schema_extracts_main_lesion():
    report = {
        "zmiany": [
            {
                "birads": "3",
                "obserwacje": []
            },
            {
                "birads": "4c",
                "obserwacje": [
                    {
                        "lokalizacje": [
                            "kwadrant górny-zewnętrzny"
                        ],
                        "wymiary": {
                            "wartosci": [10, 15, 12],
                            "jednostka": "mm"
                        },
                        "ksztalt": "owalny",
                        "brzeg": "gładki"
                    }
                ]
            }
        ]
    }

    result = views._fields_from_schema(report)

    assert result == {
        "birads": "4C",
        "location": "KGZ",
        "size": "15",
        "shape": "Owalny",
        "margin": "Gładki",
    }


def test_fields_from_schema_uses_birads_from_conclusion():
    report = {
        "zmiany": [],
        "wniosek": {
            "birads": "3"
        }
    }

    result = views._fields_from_schema(report)

    assert result == {"birads": "3"}


def test_fields_from_schema_uses_observation_with_dimensions():
    report = {
        "zmiany": [
            {
                "birads": "4",
                "obserwacje": [
                    {
                        "ksztalt": "okrągły"
                    },
                    {
                        "wymiary": {
                            "wartosci": [5, 8]
                        }
                    }
                ]
            }
        ]
    }

    result = views._fields_from_schema(report)

    assert result["size"] == "8"


def test_fields_from_schema_uses_first_observation_when_no_dimensions():
    report = {
        "zmiany": [
            {
                "birads": "4",
                "obserwacje": [
                    {"ksztalt": "owalny"},
                    {"brzeg": "gładki"}
                ]
            }
        ]
    }

    result = views._fields_from_schema(report)

    assert result["shape"] == "Owalny"
    assert "margin" not in result


def test_fields_from_schema_returns_empty_dict_for_empty_report():
    assert views._fields_from_schema({}) == {}


# =========================================================
# _proposals
# =========================================================

def test_proposals_wraps_values_in_value_dictionary():
    report = {
        "birads": "4C",
        "size": "12",
    }

    result = views._proposals(report)

    assert result == {
        "birads": {"value": "4C"},
        "size": {"value": "12"},
    }


def test_proposals_returns_empty_dict_for_empty_report():
    assert views._proposals({}) == {}


# =========================================================
# _report_rows
# =========================================================

def test_report_rows_returns_none_when_extraction_is_none():
    assert views._report_rows(None) is None


def test_report_rows_returns_none_when_accepted_report_is_empty():
    extraction = mock.Mock(
        accepted_report=None,
        generated_report={"birads": "4C"}
    )

    assert views._report_rows(extraction) is None


def test_report_rows_marks_unchanged_fields_as_not_corrected():
    extraction = mock.Mock(
        accepted_report={
            "birads": "4C",
            "size": "12"
        },
        generated_report={
            "birads": "4C",
            "size": "12"
        }
    )

    result = views._report_rows(extraction)

    assert result == [
        {"field": "birads", "value": "4C", "corrected": False},
        {"field": "size", "value": "12", "corrected": False},
    ]


def test_report_rows_marks_changed_fields_as_corrected():
    extraction = mock.Mock(
        accepted_report={
            "birads": "5",
            "size": "15"
        },
        generated_report={
            "birads": "4C",
            "size": "12"
        }
    )

    result = views._report_rows(extraction)

    assert result == [
        {"field": "birads", "value": "5", "corrected": True},
        {"field": "size", "value": "15", "corrected": True},
    ]


def test_report_rows_ignores_fields_not_in_accepted_report():
    extraction = mock.Mock(
        accepted_report={"birads": "4C"},
        generated_report={
            "birads": "4C",
            "size": "12"
        }
    )

    result = views._report_rows(extraction)

    assert result == [
        {"field": "birads", "value": "4C", "corrected": False}
    ]


# =========================================================
# _apply_form
# =========================================================

def test_apply_form_sets_approved_status_for_normal_submission():
    extraction = mock.Mock()
    user = mock.Mock()

    views._apply_form(
        extraction,
        {"birads": "4C"},
        user
    )

    assert extraction.accepted_report == {"birads": "4C"}
    assert extraction.status == views.StatusChoices.APPROVED
    assert extraction.accepted_by == user
    assert extraction.accepted_at == timezone.now().date()
    extraction.save.assert_called_once_with()


def test_apply_form_sets_corrected_status_when_field_was_corrected():
    extraction = mock.Mock()
    user = mock.Mock()

    views._apply_form(
        extraction,
        {
            "birads": {
                "value": "5",
                "state": "corrected"
            }
        },
        user
    )

    assert extraction.accepted_report == {"birads": "5"}
    assert extraction.status == views.StatusChoices.CORRECTED
    assert extraction.accepted_by == user
    extraction.save.assert_called_once_with()


def test_apply_form_sets_approved_status_for_empty_submission():
    extraction = mock.Mock()
    extraction.accepted_report = {"birads": "4C"}
    user = mock.Mock()

    views._apply_form(extraction, {}, user)

    assert extraction.status == views.StatusChoices.APPROVED
    assert extraction.accepted_report == {"birads": "4C"}
    extraction.save.assert_called_once_with()


def test_apply_form_sets_approved_status_when_submission_is_not_dictionary():
    extraction = mock.Mock()
    extraction.accepted_report = {"birads": "4C"}
    user = mock.Mock()

    views._apply_form(extraction, None, user)

    assert extraction.status == views.StatusChoices.APPROVED
    assert extraction.accepted_report == {"birads": "4C"}
    extraction.save.assert_called_once_with()
