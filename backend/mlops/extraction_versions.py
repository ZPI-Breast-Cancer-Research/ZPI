"""Extraction versions: one configuration of the LLM, the prompt and the few-shot examples.

A researcher starts a new version from the one in use and changes it while it is a draft
(status ``new``); once proposed it does not change (docs/database.md, ``module_version``). An
admin puts a proposal in use or rejects it, as for segmentation.
"""

import logging

import requests
from audit.utils import record_audit
from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from extraction.models import ExtractionResult, SourceChoices
from extraction.models import StatusChoices as ReportStatus
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from users.permissions import require_permission

from .decisions import wrong_status
from .errors import LlmServerUnavailable
from .models import ModelVersion

logger = logging.getLogger(__name__)

EXT = ModelVersion.ModuleChoices.EXT
NEW = ModelVersion.StatusChoices.NEW
CANDIDATE = ModelVersion.StatusChoices.CANDIDATE
ARCHIVED = ModelVersion.StatusChoices.ARCHIVED
VERIFIED = (ReportStatus.APPROVED, ReportStatus.CORRECTED)
# what a researcher may change in a draft
EDITABLE = ("llm_model", "structured_output", "few_shot_examples")
LLM_TIMEOUT = (2, 5)
VERSION_MAX = ModelVersion._meta.get_field("version").max_length
NAME_MAX = ModelVersion._meta.get_field("name").max_length


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


def _version_error(version: str, name: str) -> str | None:
    """Why the number or the name of a new version cannot be stored or used in a URL."""
    if not version.strip() or len(version) > VERSION_MAX or "/" in version:
        return f"Numer wersji: od 1 do {VERSION_MAX} znaków, bez „/”."
    if len(name) > NAME_MAX:
        return f"Nazwa wersji: najwyżej {NAME_MAX} znaków."
    return None


def _title(report: str) -> str:
    """The first line of an example report, for the list of examples."""
    return next(iter(report.strip().splitlines()), "")[:80]


def _person(user) -> dict | None:
    if not user:
        return None
    return {
        "login": user.get_username(),
        "name": f"{user.first_name} {user.last_name}".strip() or user.get_username(),
    }


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
        "proposedBy": _person(model.proposed_by),
        "proposedAt": model.proposed_at.isoformat() if model.proposed_at else None,
        "reason": model.reason or None,
        "restore": model.restore,
        "decidedBy": _person(model.decided_by),
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
    name = str(request.data.get("name") or (base.name if base else "extraction"))
    if error := _version_error(version, name):
        return _bad_request(error)
    try:
        # the unique (module, version) settles two drafts created at the same moment
        with transaction.atomic():
            model = ModelVersion.objects.create(
                module=EXT,
                name=name,
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
    # the version says which model fills the forms; empty would leave it to the LLM server
    if "llm_model" in changes and (
        not isinstance(changes["llm_model"], str) or not changes["llm_model"].strip()
    ):
        return _bad_request("llm_model musi być niepustym tekstem.")

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
                "title": _title(item["report"]),
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


# ---------------------------------------------------------------- decisions


def _locked(version: str) -> ModelVersion:
    return get_object_or_404(ModelVersion.objects.select_for_update(), module=EXT, version=version)


def _other_proposal(model: ModelVersion) -> Response | None:
    """One proposal at a time: the decision compares it with the version in use."""
    other = ModelVersion.objects.filter(module=EXT, status=CANDIDATE).exclude(pk=model.pk).first()
    if other is None:
        return None
    return Response(
        {"code": "proposal_pending", "detail": f"Wersja {other.version} już czeka na decyzję."},
        status=status.HTTP_409_CONFLICT,
    )


@api_view(["POST"])
@require_permission(["proposeModels"])
def propose_version(request, version):
    """A draft (or an archived version, to bring it back) waits for the admin's decision."""
    reason = str(request.data.get("reason") or "").strip()
    if not reason:
        return _bad_request("Podaj powód propozycji.")
    with transaction.atomic():
        model = _locked(version)
        if refused := wrong_status(model, (NEW, ARCHIVED)):
            return refused
        if not model.llm_model.strip():
            return _bad_request("Wersja bez modelu językowego nie może być zaproponowana.")
        if refused := _other_proposal(model):
            return refused
        model.restore = model.status == ARCHIVED
        model.status = CANDIDATE
        model.proposed_by = request.user
        model.proposed_at = timezone.now()
        model.reason = reason
        model.save(update_fields=["status", "restore", "proposed_by", "proposed_at", "reason"])
    record_audit(request, kind="model_proposed", object=f"ext {model.version}", detail=reason)
    return Response(_payload(model))


@api_view(["POST"])
@require_permission(["proposeModels"])
def withdraw_version(request, version):
    """The proposal goes back: a draft can be changed again, a restored version stays archived."""
    with transaction.atomic():
        model = _locked(version)
        if refused := wrong_status(model, (CANDIDATE,)):
            return refused
        model.status = ARCHIVED if model.restore else NEW
        model.restore = False
        model.proposed_by = None
        model.proposed_at = None
        model.reason = ""
        model.save(update_fields=["status", "restore", "proposed_by", "proposed_at", "reason"])
    record_audit(request, kind="proposal_withdrawn", object=f"ext {model.version}")
    return Response(_payload(model))


@api_view(["POST"])
@require_permission(["manageModels"])
def promote_version(request, version):
    """The proposal becomes the version in use; the next reports are processed with it."""
    with transaction.atomic():
        model = _locked(version)
        if refused := wrong_status(model, (CANDIDATE,)):
            return refused
        model.restore = False
        # the admin's note, or the reason of the proposal when there is none
        model.put_in_use(request.user, reason=str(request.data.get("reason") or model.reason))
    record_audit(request, kind="model_promoted", object=f"ext {model.version}")
    return Response(_payload(model))


@api_view(["POST"])
@require_permission(["manageModels"])
def reject_version(request, version):
    """The proposal is turned down; a restored version stays archived."""
    reason = str(request.data.get("reason") or "").strip()
    if not reason:
        return _bad_request("Podaj powód odrzucenia.")
    with transaction.atomic():
        model = _locked(version)
        if refused := wrong_status(model, (CANDIDATE,)):
            return refused
        model.status = ARCHIVED if model.restore else ModelVersion.StatusChoices.REJECTED
        model.restore = False
        model.decided_by = request.user
        model.reason = reason
        model.save(update_fields=["status", "restore", "decided_by", "reason"])
    record_audit(request, kind="model_rejected", object=f"ext {model.version}", detail=reason)
    return Response(_payload(model))
