"""Extraction versions: one configuration of the LLM, the prompt and the few-shot examples.

A researcher starts a new version from the one in use and changes it while it is a draft
(status ``new``); once proposed it does not change (docs/database.md, ``module_version``).
"""

import logging

import requests
from audit.utils import record_audit
from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from extraction.models import ExtractionResult, SourceChoices
from extraction.models import StatusChoices as ReportStatus
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from users.permissions import require_permission

from .errors import LlmServerUnavailable
from .models import ModelVersion

logger = logging.getLogger(__name__)

EXT = ModelVersion.ModuleChoices.EXT
NEW = ModelVersion.StatusChoices.NEW
VERIFIED = (ReportStatus.APPROVED, ReportStatus.CORRECTED)
# what a researcher may change in a draft
EDITABLE = ("llm_model", "structured_output", "few_shot_examples")
LLM_TIMEOUT = (2, 5)


def _version(version: str) -> ModelVersion:
    return get_object_or_404(ModelVersion, module=EXT, version=version)


def _in_use() -> ModelVersion | None:
    return (
        ModelVersion.objects.filter(module=EXT, status=ModelVersion.StatusChoices.PRODUCTION)
        .order_by("-id")
        .first()
    )


def _not_a_draft(model: ModelVersion) -> Response:
    return Response(
        {
            "code": "not_editable",
            "detail": f"Wersja {model.version} nie jest szkicem; zmiany wymagają nowej wersji.",
        },
        status=status.HTTP_409_CONFLICT,
    )


def _bad_request(detail: str) -> Response:
    return Response({"code": "invalid", "detail": detail}, status=status.HTTP_400_BAD_REQUEST)


def _examples_error(examples) -> str | None:
    """Why the list is not ``[{"report": text, "output": form}, ...]``, or None.

    The form itself is checked against the schema by the worker (examples_from_version).
    """
    if not isinstance(examples, list):
        return "few_shot_examples musi być listą."
    for item in examples:
        if not isinstance(item, dict) or not isinstance(item.get("report"), str):
            return "Każdy przykład ma tekst opisu w polu report."
        if not item["report"].strip() or not isinstance(item.get("output"), dict):
            return "Każdy przykład ma niepusty opis i formularz w polu output."
    return None


def _payload(model: ModelVersion) -> dict:
    return {
        "version": model.version,
        "name": model.name,
        "status": model.status,
        "llmModel": model.llm_model,
        "promptVersion": model.prompt_version,
        "structuredOutput": model.structured_output,
        "fewShotExamples": model.few_shot_examples,
        "editable": model.editable,
        "createdAt": model.created_at.isoformat() if model.created_at else None,
    }


def _next_version() -> str:
    """The next whole number after the numeric versions of the module (1, 2, 3, ...)."""
    numbers = [
        int(v)
        for v in ModelVersion.objects.filter(module=EXT).values_list("version", flat=True)
        if v.isdigit()
    ]
    return str(max(numbers, default=0) + 1)


@api_view(["GET"])
@require_permission(["viewModels"])
def llm_models(request):
    """The models the LLM server of the worker offers, for the version form."""
    if not settings.LLM_BASE_URL:
        raise LlmServerUnavailable("LLM_BASE_URL is not set")
    try:
        response = requests.get(f"{settings.LLM_BASE_URL}/models", timeout=LLM_TIMEOUT)
        response.raise_for_status()
        models = [item["id"] for item in response.json().get("data", [])]
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise LlmServerUnavailable(f"Listing models of {settings.LLM_BASE_URL}: {exc}") from exc
    return Response(models)


@api_view(["POST"])
@require_permission(["proposeModels"])
def create_version(request):
    """A new draft with the configuration of the version in use."""
    base = _in_use()
    version = str(request.data.get("version") or _next_version())
    try:
        # the unique (module, version) settles two drafts created at the same moment
        with transaction.atomic():
            model = ModelVersion.objects.create(
                module=EXT,
                name=request.data.get("name") or (base.name if base else "extraction"),
                version=version,
                status=NEW,
                llm_model=base.llm_model if base else "",
                prompt_version=base.prompt_version if base else "",
                structured_output=base.structured_output if base else True,
                few_shot_examples=list(base.few_shot_examples) if base else [],
            )
    except IntegrityError:
        return _bad_request(f"Wersja {version} już istnieje.")
    record_audit(
        request,
        kind="version_created",
        object=f"ext {model.version}",
        detail=f"z wersji {base.version}" if base else "bez wersji w użyciu",
    )
    return Response(_payload(model), status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH"])
@require_permission(["viewModels"])
def version_detail(request, version):
    """The configuration of a version; a draft can be changed (model, structured output,
    the whole set of examples)."""
    if request.method == "GET":
        return Response(_payload(_version(version)))

    if getattr(request.user, "role", None) not in ("researcher", "admin"):
        return Response({"detail": "Brak uprawnień"}, status=status.HTTP_403_FORBIDDEN)
    changes = {key: request.data[key] for key in EDITABLE if key in request.data}
    if "few_shot_examples" in changes and (error := _examples_error(changes["few_shot_examples"])):
        return _bad_request(error)
    if "structured_output" in changes and not isinstance(changes["structured_output"], bool):
        return _bad_request("structured_output musi być true albo false.")
    if "llm_model" in changes and not isinstance(changes["llm_model"], str):
        return _bad_request("llm_model musi być tekstem.")

    with transaction.atomic():
        model = get_object_or_404(
            ModelVersion.objects.select_for_update(), module=EXT, version=version
        )
        if not model.editable:
            return _not_a_draft(model)
        for key, value in changes.items():
            setattr(model, key, value)
        model.save(update_fields=[*changes])
    record_audit(
        request, kind="version_changed", object=f"ext {model.version}", detail=", ".join(changes)
    )
    return Response(_payload(model))


@api_view(["POST"])
@require_permission(["proposeModels"])
def add_example(request, version):
    """Add a verified report to the examples of a draft: its text and its accepted form.

    The report keeps its id in the example, so the evaluation of the version leaves it out.
    """
    report = ExtractionResult.objects.filter(pk=request.data.get("report_id")).first()
    if report is None:
        return Response({"detail": "Nie ma takiego opisu."}, status=status.HTTP_404_NOT_FOUND)
    if report.status not in VERIFIED or not report.accepted_report:
        return _bad_request("Przykładem może być tylko zweryfikowany opis.")
    if report.source == SourceChoices.MANUAL or not report.ocr_text:
        return _bad_request("Opis wypełniony ręcznie nie ma tekstu, który mógłby być przykładem.")

    with transaction.atomic():
        model = get_object_or_404(
            ModelVersion.objects.select_for_update(), module=EXT, version=version
        )
        if not model.editable:
            return _not_a_draft(model)
        if report.pk in few_shot_report_ids(model):
            return _bad_request("Ten opis już jest przykładem tej wersji.")
        model.few_shot_examples = [
            *model.few_shot_examples,
            {"report": report.ocr_text, "output": report.accepted_report, "report_id": report.pk},
        ]
        model.save(update_fields=["few_shot_examples"])
    record_audit(
        request,
        kind="version_changed",
        object=f"ext {model.version}",
        detail=f"przykład z opisu #{report.pk}",
    )
    return Response(_payload(model), status=status.HTTP_201_CREATED)


@api_view(["GET"])
@require_permission(["viewModels"])
def few_shot(request, version):
    """The examples of a version as the models screen shows them (frontend models/extraction.ts
    FewShotExample); ``isNew``: not in the set of the version in use."""
    model = _version(version)
    in_use = _in_use()
    used = {item["report"] for item in (in_use.few_shot_examples if in_use else [])}
    return Response(
        [
            {
                "id": str(item.get("report_id") or index + 1),
                "title": item["report"].strip().splitlines()[0][:80],
                "report": item["report"],
                "output": item["output"],
                "isNew": item["report"] not in used,
            }
            for index, item in enumerate(model.few_shot_examples)
        ]
    )


def few_shot_report_ids(model: ModelVersion | None) -> set[int]:
    """Reports that are examples of the version: left out when the version is evaluated."""
    if model is None:
        return set()
    return {item["report_id"] for item in model.few_shot_examples if item.get("report_id")}
