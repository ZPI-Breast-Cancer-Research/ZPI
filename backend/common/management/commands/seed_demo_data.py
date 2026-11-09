"""Populate database with synthetic data for local UI development."""
import requests

from patients.orthanc_client import OrthancClient

from ._demo_dicom import delete_demo_studies, upload_study
from copy import deepcopy
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from extraction.models import ExtractionResult, StatusChoices as ExtractionStatus
from mlops.models import ModelVersion
from patients.models import Study
from segmentation.models import SegmentationResult, StatusChoices as SegmentationStatus
from users.models import Role, User


STUDY_PREFIX = "DEMO-ORTHANC-"
MODEL_VERSION_PREFIX = "demo-"
UNASSIGNED_REPORT_PREFIX = "demo/unassigned/"
DEFAULT_PASSWORD = "DemoPass123!"

DEMO_BIRADS = ["2", "3", "4", "4a", "4b", "4c", "5"]
BIRADS_ORDER = ["0", "1", "2", "3", "4", "4a", "4b", "4c", "5", "6"]
DEMO_SIZES = [
    [6, 5, 4],
    [8, 7, 6],
    [12, 9, 8],
    [15, 11, 9],
    [19, 14, 12],
    [22, 16, 13],
]

DEMO_SHAPES = ["okrągły", "owalny", "nieregularny"]

DEMO_MARGINS = [
    "obwiedziony",
    "nieostry",
    "zatarty",
    "mikropłatowaty",
    "kątowy",
    "spikularny",
]

DEMO_LOCATIONS = [
    "kwadrant górny-zewnętrzny",
    "kwadrant górny-wewnętrzny",
    "kwadrant dolny-zewnętrzny",
    "kwadrant dolny-wewnętrzny",
    "okolica zabrodawkowa",
    "część centralna",
]

DEMO_BREAST_BUILD = [
    "tłuszczowa",
    "gruczołowo-tłuszczowa",
    "gruczołowa",
]

DEMO_ECHOGENICITY = [
    "bezechowa",
    "hipoechogeniczna",
    "izoechogeniczna",
    "hiperechogeniczna",
    "złożona",
]

DEMO_HOMOGENEITY = ["jednorodna", "niejednorodna"]

DEMO_BIRADS_CORRECTIONS = {
    "2": "3",
    "3": "4",
    "4": "4a",
    "4a": "4b",
    "4b": "4c",
    "4c": "5",
    "5": "6",
}
def _apply_variant(report: dict, index: int) -> dict:
    """Edge cases for the review views: no lesion, two lesions, incomplete observation."""
    if index % 11 == 5:  # badanie bez zmian ogniskowych
        report["zmiany"] = []
        for side in ("lewa", "prawa"):
            report["piersi"][side]["zmiany_ogniskowe"] = False
            report["piersi"][side]["mikrozwapnienia"] = False
            report["piersi"][side]["obrzek"] = False
        report["wniosek"] = {
            "birads": "1",
            "tekst": "Obraz bez zmian ogniskowych, BI-RADS 1.",
            "zalecenie": "Kontrola za 12 miesięcy.",
        }
        return report

    if index % 9 == 4:  # druga zmiana: sprawdza wybór „głównej” (najwyższy BI-RADS)
        second = deepcopy(report["zmiany"][0])
        second["id"] = 2
        second["birads"] = DEMO_BIRADS[(index + 3) % len(DEMO_BIRADS)]
        for obs in second["obserwacje"]:
            obs["lokalizacje"] = [DEMO_LOCATIONS[(index + 2) % len(DEMO_LOCATIONS)]]
            _refresh_observation_citation(obs)
        report["zmiany"].append(second)
        top = max(
            (report["zmiany"][0]["birads"], second["birads"]), key=BIRADS_ORDER.index
        )
        report["wniosek"]["birads"] = top
        report["wniosek"]["tekst"] = f"Obraz zmiany BI-RADS {top}."

    if index % 13 == 7:  # niekompletna obserwacja USG
        usg = report["zmiany"][0]["obserwacje"][1]
        usg["wymiary"] = None
        usg["brzeg"] = None

    return report

def _build_demo_observation(index: int, modality: str) -> dict:
    """Generates a complete observation matching the Pydantic schema."""

    is_ultrasound = modality == "usg"

    location = DEMO_LOCATIONS[index % len(DEMO_LOCATIONS)]
    size = list(DEMO_SIZES[
        (index + (1 if is_ultrasound else 0)) % len(DEMO_SIZES)
    ])

    shape = DEMO_SHAPES[index % len(DEMO_SHAPES)]
    margin = DEMO_MARGINS[(index + 1) % len(DEMO_MARGINS)]

    clock_position = str((index * 2) % 12 + 1)
    distance_cm = float(2 + index % 6)

    skin_invasion = index % 17 == 0

    if is_ultrasound:
        observation_type = "ognisko hipoechogeniczne"
        depth = {
            "wartosc": float(5 + index % 8),
            "jednostka": "mm",
        }
        echogenicity = DEMO_ECHOGENICITY[
            index % len(DEMO_ECHOGENICITY)
        ]
        homogeneity = DEMO_HOMOGENEITY[
            index % len(DEMO_HOMOGENEITY)
        ]
    else:
        observation_type = "zmiana guzowata"
        depth = None
        echogenicity = None
        homogeneity = None

    size_text = " × ".join(str(value) for value in size) + " mm"

    citation = (
        f"W lokalizacji {location}, na godzinie {clock_position}, "
        f"widoczna {observation_type} o wymiarach {size_text}, "
        f"kształcie {shape} i brzegu {margin}."
    )

    return {
        "modalnosc": modality,
        "lokalizacje": [location],
        "godzina": clock_position,
        "odleglosc_od_brodawki": {
            "wartosc": distance_cm,
            "jednostka": "cm",
        },
        "typ": observation_type,
        "wymiary": {
            "wartosci": size,
            "jednostka": "mm",
            "kwalifikator": (
                "dokładny",
                "około",
                "do",
            )[index % 3],
        },
        "glebokosc": depth,
        "ksztalt": shape,
        "brzeg": margin,
        "echogenicznosc": echogenicity,
        "jednorodnosc": homogeneity,
        "naciek_skory": skin_invasion,
        "cytat": citation,
    }


def _build_demo_breast(
    index: int,
    has_focal_lesion: bool,
    side: str,
) -> dict:

    has_calcifications = not has_focal_lesion and index % 7 == 0
    has_microcalcifications = has_focal_lesion and index % 5 == 0
    has_edema = has_focal_lesion and index % 19 == 0
    skin_invasion = has_focal_lesion and index % 17 == 0

    return {
        "budowa": DEMO_BREAST_BUILD[
            (index + (0 if side == "lewa" else 1))
            % len(DEMO_BREAST_BUILD)
        ],
        "obrzek": has_edema,
        "zwapnienia": has_calcifications,
        "mikrozwapnienia": has_microcalcifications,
        "zmiany_ogniskowe": has_focal_lesion,
        "skora": {
            "stan": (
                "niewielkie pogrubienie"
                if skin_invasion
                else "prawidłowa"
            ),
            "naciek": skin_invasion,
        },
    }


def _build_demo_nodes(index: int, side: str) -> list[dict]:

    pathological = index % 5 == 0
    multiple = index % 2 == 1

    count_label = "mnogie" if multiple else "pojedynczy"

    if pathological:
        note = "pogrubiała kora, zatarta wnęka tłuszczowa"
        dimensions = [14, 7]

        quote = (
            "W dole pachowym widoczne mnogie węzły chłonne "
            "o pogrubiałej korze."
            if multiple
            else "W dole pachowym widoczny pojedynczy węzeł "
                 "chłonny o pogrubiałej korze."
        )
    else:
        note = "zachowana wnęka tłuszczowa, niepogrubiała kora"
        dimensions = [8, 4]

        quote = (
            "W dole pachowym widoczne mnogie węzły chłonne "
            "o zachowanej wnęce tłuszczowej."
            if multiple
            else "W dole pachowym widoczny pojedynczy węzeł "
                 "chłonny o zachowanej wnęce tłuszczowej."
        )

    return [
        {
            "modalnosc": "usg",
            "strona": side,
            "okolica": "dół pachowy",
            "liczba": count_label,
            "wymiary": {
                "wartosci": dimensions,
                "jednostka": "mm",
                "kwalifikator": "dokładny",
            },
            "patologiczne": pathological,
            "uwagi": note,
            "cytat": quote,
        }
    ]


def _build_demo_report(index: int) -> dict:
    """Generates a complete EkstrakcjaBadania JSON object."""

    side = "lewa" if index % 2 == 0 else "prawa"
    birads = DEMO_BIRADS[index % len(DEMO_BIRADS)]

    observations = [
        _build_demo_observation(index, "mammografia"),
        _build_demo_observation(index, "usg"),
    ]

    reason = (
        "Obserwacje dotyczą tej samej strony, lokalizacji "
        "i położenia zegarowego; zmiana w USG koreluje "
        "ze zmianą opisaną w mammografii."
    )

    return {
        "modalnosci": [
            "mammografia",
            "usg",
        ],
        "piersi": {
            "lewa": _build_demo_breast(
                index,
                side == "lewa",
                "lewa",
            ),
            "prawa": _build_demo_breast(
                index,
                side == "prawa",
                "prawa",
            ),
        },
        "zmiany": [
            {
                "id": 1,
                "strona": side,
                "birads": birads,
                "obserwacje": observations,
                "polaczenie_obserwacji": {
                    "pewne": True,
                    "powod": reason,
                },
            }
        ],
        "wezly": _build_demo_nodes(index, side),
        "wniosek": {
            "birads": birads,
            "tekst": f"Obraz zmiany BI-RADS {birads}.",
            "zalecenie": (
                "Kontrola obrazowa za 6 miesięcy."
                if birads in ("2", "3")
                else "Wskazana dalsza diagnostyka zmiany."
            ),
        },
    }


def _refresh_observation_citation(observation: dict) -> None:

    dimensions = observation["wymiary"]["wartosci"]
    unit = observation["wymiary"]["jednostka"]

    size_text = " × ".join(str(value) for value in dimensions)
    size_text += f" {unit}"

    location = (
        observation["lokalizacje"][0]
        if observation["lokalizacje"]
        else "opisywanej okolicy"
    )

    observation["cytat"] = (
        f"W lokalizacji {location} widoczna "
        f"{observation['typ']} o wymiarach {size_text}, "
        f"kształcie {observation['ksztalt']} "
        f"i brzegu {observation['brzeg']}."
    )


def _build_accepted_demo_report(
    generated_report: dict,
    index: int,
    ext_status: str,
) -> dict:
    accepted_report = deepcopy(generated_report)
    if not accepted_report["zmiany"]:
            return accepted_report
    
    should_correct_birads = (
        index % 2 == 0
        or ext_status == ExtractionStatus.CORRECTED
    )

    if should_correct_birads:
        current_birads = accepted_report["zmiany"][0]["birads"]

        corrected_birads = DEMO_BIRADS_CORRECTIONS[
            current_birads
        ]

        accepted_report["zmiany"][0]["birads"] = corrected_birads
        accepted_report["wniosek"]["birads"] = corrected_birads

        accepted_report["wniosek"]["tekst"] = (
            f"Obraz zmiany BI-RADS {corrected_birads}."
        )

    corrected_observation = (
        accepted_report["zmiany"][0]["obserwacje"][0]
    )

    if index % 3 == 0:
        corrected_observation["wymiary"]["wartosci"] = list(
            DEMO_SIZES[(index + 2) % len(DEMO_SIZES)]
        )

    if index % 4 == 0:
        corrected_observation["brzeg"] = DEMO_MARGINS[
            (index + 3) % len(DEMO_MARGINS)
        ]

    if index % 3 == 0 or index % 4 == 0:
        _refresh_observation_citation(corrected_observation)

    return accepted_report
class Command(BaseCommand):
    help = (
        "Creates synthetic demo users, studies, segmentations, "
        "reports and ML model versions."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=80,
            help="How many synthetic studies to create (default: 80).",
        )

        parser.add_argument(
            "--password",
            type=str,
            default=DEFAULT_PASSWORD,
            help="Password assigned to generated demo accounts.",
        )

        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete only records created by this command before seeding again.",
        )
        parser.add_argument(
            "--no-orthanc",
            action="store_true",
            help="Do not upload DICOMs; Study rows get fake Orthanc ids (the study list stays empty).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count = options["count"]
        password = options["password"]

        if count < 1 or count > 2000:
            raise CommandError("--count must be between 1 and 2000.")
        if not password:
            raise CommandError("--password cannot be empty.")

        orthanc = None
        if not options["no_orthanc"]:
            client = OrthancClient()
            if client.status() != "ok":
                raise CommandError(
                    "Orthanc jest niedostępny albo odrzuca dane logowania "
                    "(sprawdź ORTHANC_*). Użyj --no-orthanc, żeby pominąć DICOM-y."
                )
            orthanc = (requests.Session(), client.base_url, client.auth)

        if options["reset"]:
            self._reset_demo_data(orthanc)

        users = self._seed_users(password)
        versions = self._seed_model_versions(users)

        self._seed_studies(count, users, versions, orthanc)
        self._seed_unassigned_reports()

        demo_ids = self._demo_study_ids()
        segmentation_count = SegmentationResult.objects.filter(study_id__in=demo_ids).count()
        extraction_count = ExtractionResult.objects.filter(study_id__in=demo_ids).count()
        unassigned_count = ExtractionResult.objects.filter(
            report_path__startswith=UNASSIGNED_REPORT_PREFIX
        ).count()
        model_count = ModelVersion.objects.filter(
            version__startswith=MODEL_VERSION_PREFIX
        ).count()

        self.stdout.write(self.style.SUCCESS("Demo data is ready."))
        self.stdout.write(
            f"Studies: {len(demo_ids)} | "
            f"Segmentations: {segmentation_count} | "
            f"Extractions: {extraction_count} | "
            f"Unassigned reports: {unassigned_count} | "
            f"Model versions: {model_count} | "
            f"DICOM in Orthanc: {'yes' if orthanc else 'no'}"
        )

        self.stdout.write("Demo accounts:")
        for username, label in (
            ("demo.admin", "admin"),
            ("demo.radiologist", "radiologist"),
            ("demo.radiologist2", "radiologist"),
            ("demo.researcher", "researcher"),
            ("demo.temporary", "first login required"),
            ("demo.blocked", "inactive account"),
        ):
            self.stdout.write(f"  {username:<20} / {password} ({label})")

        self.stdout.write(
            self.style.WARNING(
                "These are synthetic records. "
                "Do not run this command against production data."
            )
        )

    def _demo_study_ids(self):
        """Demo studies = anything pointing at demo/ paths (or the old fake ids)."""
        ids = set(
            SegmentationResult.objects.filter(
                generated_path__startswith="demo/"
            ).values_list("study_id", flat=True)
        )
        ids |= set(
            ExtractionResult.objects.filter(
                report_path__startswith="demo/"
            ).values_list("study_id", flat=True)
        )
        ids |= set(
            Study.objects.filter(
                orthanc_path__startswith=STUDY_PREFIX
            ).values_list("id", flat=True)
        )
        ids.discard(None)
        return ids

    def _reset_demo_data(self, orthanc):
        demo_ids = self._demo_study_ids()

        SegmentationResult.objects.filter(study_id__in=demo_ids).delete()
        ExtractionResult.objects.filter(study_id__in=demo_ids).delete()
        ExtractionResult.objects.filter(
            report_path__startswith=UNASSIGNED_REPORT_PREFIX
        ).delete()
        Study.objects.filter(id__in=demo_ids).delete()

        ModelVersion.objects.filter(version__startswith=MODEL_VERSION_PREFIX).delete()
        User.objects.filter(username__startswith="demo.").delete()

        if orthanc:
            removed = delete_demo_studies(*orthanc)
            self.stdout.write(f"Removed {removed} demo studies from Orthanc.")
        self.stdout.write("Removed previous demo records.")
    def _seed_users(self, password):
        now = timezone.now()

        specs = [
            {
                "username": "demo.admin",
                "first_name": "Demo",
                "last_name": "Administrator",
                "email": "demo.admin@example.test",
                "role": Role.ADMIN,
                "pwz": None,
                "is_superuser": True,
                "is_staff": True,
                "is_active": True,
                "is_first_login": False,
                "last_login": now - timedelta(hours=3),
            },
            {
                "username": "demo.radiologist",
                "first_name": "Anna",
                "last_name": "Nowak",
                "email": "anna.nowak@example.test",
                "role": Role.RADIOLOGIST,
                "pwz": "DEMO-PWZ-001",
                "is_superuser": False,
                "is_staff": False,
                "is_active": True,
                "is_first_login": False,
                "last_login": now - timedelta(hours=8),
            },
            {
                "username": "demo.radiologist2",
                "first_name": "Piotr",
                "last_name": "Kowalski",
                "email": "piotr.kowalski@example.test",
                "role": Role.RADIOLOGIST,
                "pwz": "DEMO-PWZ-002",
                "is_superuser": False,
                "is_staff": False,
                "is_active": True,
                "is_first_login": False,
                "last_login": now - timedelta(days=1),
            },
            {
                "username": "demo.researcher",
                "first_name": "Marta",
                "last_name": "Wiśniewska",
                "email": "marta.wisniewska@example.test",
                "role": Role.RESEARCHER,
                "pwz": None,
                "is_superuser": False,
                "is_staff": False,
                "is_active": True,
                "is_first_login": False,
                "last_login": now - timedelta(days=4),
            },
            {
                "username": "demo.temporary",
                "first_name": "Tomasz",
                "last_name": "Zieliński",
                "email": "tomasz.zielinski@example.test",
                "role": Role.RADIOLOGIST,
                "pwz": "DEMO-PWZ-003",
                "is_superuser": False,
                "is_staff": False,
                "is_active": True,
                "is_first_login": True,
                "last_login": None,
            },
            {
                "username": "demo.blocked",
                "first_name": "Ewa",
                "last_name": "Kamińska",
                "email": "ewa.kaminska@example.test",
                "role": Role.RADIOLOGIST,
                "pwz": "DEMO-PWZ-004",
                "is_superuser": False,
                "is_staff": False,
                "is_active": False,
                "is_first_login": False,
                "last_login": now - timedelta(days=20),
            },
        ]

        result = {}

        for spec in specs:
            username = spec["username"]

            user, _ = User.objects.get_or_create(
                username=username
            )

            for field, value in spec.items():
                if field != "username":
                    setattr(user, field, value)

            user.set_password(password)
            user.save()

            result[username] = user

        return result

    def _seed_model_versions(self, users):
        now = timezone.now()
        admin = users["demo.admin"]

        specs = [
            {
                "module": ModelVersion.ModuleChoices.SEG,
                "version": "demo-seg-0.9.0",
                "name": "Breast MRI Segmentation",
                "status": ModelVersion.StatusChoices.ARCHIVED,
                "decision": ModelVersion.DecisionChoices.REPLACED,
                "created_days_ago": 85,
                "activated_days_ago": 85,
                "deactivated_days_ago": 48,
                "decided_by": admin,
                "dice": 0.842,
                "hd95": 7.8,
                "f1": 0.861,
            },
            {
                "module": ModelVersion.ModuleChoices.SEG,
                "version": "demo-seg-1.0.0",
                "name": "Breast MRI Segmentation",
                "status": ModelVersion.StatusChoices.ARCHIVED,
                "decision": ModelVersion.DecisionChoices.REPLACED,
                "created_days_ago": 52,
                "activated_days_ago": 48,
                "deactivated_days_ago": 18,
                "decided_by": admin,
                "dice": 0.876,
                "hd95": 5.9,
                "f1": 0.889,
            },
            {
                "module": ModelVersion.ModuleChoices.SEG,
                "version": "demo-seg-1.1.0",
                "name": "Breast MRI Segmentation",
                "status": ModelVersion.StatusChoices.PRODUCTION,
                "decision": ModelVersion.DecisionChoices.PROMOTED,
                "created_days_ago": 23,
                "activated_days_ago": 18,
                "deactivated_days_ago": None,
                "decided_by": admin,
                "dice": 0.901,
                "hd95": 4.6,
                "f1": 0.914,
            },
            {
                "module": ModelVersion.ModuleChoices.SEG,
                "version": "demo-seg-1.2.0",
                "name": "Breast MRI Segmentation",
                "status": ModelVersion.StatusChoices.CANDIDATE,
                "decision": ModelVersion.DecisionChoices.PENDING,
                "created_days_ago": 3,
                "activated_days_ago": None,
                "deactivated_days_ago": None,
                "decided_by": None,
                "dice": 0.918,
                "hd95": 4.1,
                "f1": 0.927,
            },
            {
                "module": ModelVersion.ModuleChoices.SEG,
                "version": "demo-seg-1.3.0",
                "name": "Breast MRI Segmentation",
                "status": ModelVersion.StatusChoices.TRAINING,
                "decision": ModelVersion.DecisionChoices.PENDING,
                "created_days_ago": 1,
                "activated_days_ago": None,
                "deactivated_days_ago": None,
                "decided_by": None,
                "dice": None,
                "hd95": None,
                "f1": None,
            },
            {
                "module": ModelVersion.ModuleChoices.SEG,
                "version": "demo-seg-0.8.0",
                "name": "Breast MRI Segmentation",
                "status": ModelVersion.StatusChoices.REJECTED,
                "decision": ModelVersion.DecisionChoices.REJECTED_GATE,
                "created_days_ago": 12,
                "activated_days_ago": None,
                "deactivated_days_ago": None,
                "decided_by": None,
                "dice": 0.851,
                "hd95": 9.3,
                "f1": 0.867,
            },
            {
                "module": ModelVersion.ModuleChoices.EXT,
                "version": "demo-ext-0.9.0",
                "name": "Breast MRI Report Extraction",
                "status": ModelVersion.StatusChoices.ARCHIVED,
                "decision": ModelVersion.DecisionChoices.REPLACED,
                "created_days_ago": 70,
                "activated_days_ago": 70,
                "deactivated_days_ago": 30,
                "decided_by": admin,
                "dice": None,
                "hd95": None,
                "f1": 0.842,
            },
            {
                "module": ModelVersion.ModuleChoices.EXT,
                "version": "demo-ext-1.0.0",
                "name": "Breast MRI Report Extraction",
                "status": ModelVersion.StatusChoices.PRODUCTION,
                "decision": ModelVersion.DecisionChoices.PROMOTED,
                "created_days_ago": 35,
                "activated_days_ago": 30,
                "deactivated_days_ago": None,
                "decided_by": admin,
                "dice": None,
                "hd95": None,
                "f1": 0.913,
            },
            {
                "module": ModelVersion.ModuleChoices.EXT,
                "version": "demo-ext-1.1.0",
                "name": "Breast MRI Report Extraction",
                "status": ModelVersion.StatusChoices.CANDIDATE,
                "decision": ModelVersion.DecisionChoices.PENDING,
                "created_days_ago": 2,
                "activated_days_ago": None,
                "deactivated_days_ago": None,
                "decided_by": None,
                "dice": None,
                "hd95": None,
                "f1": 0.929,
            },
        ]

        result = {}

        for spec in specs:
            module = spec["module"]
            version = spec["version"]

            model, _ = ModelVersion.objects.get_or_create(
                module=module,
                version=version,
                defaults={"name": spec["name"]},
            )

            model.name = spec["name"]
            model.status = spec["status"]
            model.decision = spec["decision"]

            model.activated_at = (
                now - timedelta(days=spec["activated_days_ago"])
                if spec["activated_days_ago"] is not None
                else None
            )

            model.deactivated_at = (
                now - timedelta(days=spec["deactivated_days_ago"])
                if spec["deactivated_days_ago"] is not None
                else None
            )

            model.decided_by = spec["decided_by"]
            model.mlflow_run_id = (
                f"demo-{module}-{version.replace('.', '-')}"
            )

            model.dice = spec["dice"]
            model.hd95 = spec["hd95"]
            model.f1 = spec["f1"]

            model.save()

            ModelVersion.objects.filter(pk=model.pk).update(
                created_at=now - timedelta(
                    days=spec["created_days_ago"]
                )
            )

            result[(module, version)] = model

        return {
            "seg_production": result[
                (ModelVersion.ModuleChoices.SEG, "demo-seg-1.1.0")
            ],
            "seg_previous": result[
                (ModelVersion.ModuleChoices.SEG, "demo-seg-1.0.0")
            ],
            "seg_candidate": result[
                (ModelVersion.ModuleChoices.SEG, "demo-seg-1.2.0")
            ],
            "ext_production": result[
                (ModelVersion.ModuleChoices.EXT, "demo-ext-1.0.0")
            ],
            "ext_previous": result[
                (ModelVersion.ModuleChoices.EXT, "demo-ext-0.9.0")
            ],
        }
    def _seed_studies(self, count, users, versions, orthanc):
        today = timezone.localdate()

        reviewers = [users["demo.radiologist"], users["demo.radiologist2"]]

        segmentation_statuses = [
            SegmentationStatus.PENDING,
            SegmentationStatus.PROCESSING,
            SegmentationStatus.COMPLETED,
            SegmentationStatus.COMPLETED,
            SegmentationStatus.COMPLETED,
            SegmentationStatus.APPROVED,
            SegmentationStatus.CORRECTED,
            SegmentationStatus.APPROVED,
            SegmentationStatus.REJECTED,
            SegmentationStatus.COMPLETED,
        ]
        extraction_statuses = [
            ExtractionStatus.PENDING,
            ExtractionStatus.PROCESSING,
            ExtractionStatus.COMPLETED,
            ExtractionStatus.APPROVED,
            ExtractionStatus.APPROVED,
            ExtractionStatus.CORRECTED,
            ExtractionStatus.REJECTED,
            ExtractionStatus.APPROVED,
            ExtractionStatus.COMPLETED,
            ExtractionStatus.APPROVED,
        ]

        for index in range(count):
            number = index + 1
            study_date = today - timedelta(days=(index * 7) % 60)

            if orthanc:
                orthanc_id, series_uids = upload_study(
                    *orthanc, number=number, study_date=study_date
                )
                self.stdout.write(f"  [{number}/{count}] {orthanc_id}")
            else:
                orthanc_id = f"{STUDY_PREFIX}{number:05d}"
                series_uids = [
                    f"DEMO-SERIES-{number:05d}-01",
                    f"DEMO-SERIES-{number:05d}-02",
                ]

            study, _ = Study.objects.get_or_create(orthanc_path=orthanc_id)

            # ---------------- SEGMENTATION ----------------
            seg_status = segmentation_statuses[index % len(segmentation_statuses)]
            seg_verified = seg_status in (
                SegmentationStatus.APPROVED,
                SegmentationStatus.CORRECTED,
            )
            seg_reviewer = reviewers[index % len(reviewers)] if seg_verified else None
            seg_accepted_at = (
                today - timedelta(days=(index * 5) % 56) if seg_verified else None
            )
            seg_model = (
                versions["seg_previous"] if index % 7 == 0 else versions["seg_production"]
            )
            uncertainty = round(0.04 + ((index * 19) % 90) / 100, 3)

            segmentation, _ = SegmentationResult.objects.get_or_create(study=study)
            segmentation.model = seg_model
            segmentation.status = seg_status
            segmentation.uncertainty = uncertainty
            segmentation.generated_path = (
                f"demo/segmentations/{number:05d}/generated.nii.gz"
            )
            segmentation.accepted_path = (
                f"demo/segmentations/{number:05d}/accepted.nii.gz"
                if seg_verified
                else None
            )
            segmentation.input_series_ids = series_uids
            segmentation.accepted_by = seg_reviewer
            segmentation.accepted_at = seg_accepted_at
            segmentation.save()

            # ---------------- EXTRACTION ----------------
            ext_status = extraction_statuses[index % len(extraction_statuses)]
            ext_verified = ext_status in (
                ExtractionStatus.APPROVED,
                ExtractionStatus.CORRECTED,
            )
            ext_reviewer = (
                reviewers[(index + 1) % len(reviewers)] if ext_verified else None
            )
            ext_accepted_at = (
                today - timedelta(days=(index * 3) % 56) if ext_verified else None
            )

            generated_report = _apply_variant(_build_demo_report(index), index)
            accepted_report = (
                _build_accepted_demo_report(generated_report, index, ext_status)
                if ext_verified
                else None
            )

            report_path = f"demo/reports/{number:05d}/report.json"
            extraction, _ = ExtractionResult.objects.get_or_create(
                study=study, defaults={"report_path": report_path}
            )
            extraction.model = versions["ext_production"]
            extraction.status = ext_status
            extraction.uncertainty = round(max(0.02, min(0.98, uncertainty + 0.07)), 3)
            extraction.report_path = report_path
            extraction.generated_report = generated_report
            extraction.accepted_report = accepted_report
            extraction.accepted_by = ext_reviewer
            extraction.accepted_at = ext_accepted_at
            extraction.save()
    def _seed_unassigned_reports(self):
        samples = [
            ("opis_piersi_001.txt", ExtractionStatus.PENDING),
            ("skan_opisu_002.jpg", ExtractionStatus.PENDING),
            ("opis_konsultacyjny_003.txt", ExtractionStatus.PROCESSING),
            ("zalacznik_004.png", ExtractionStatus.PENDING),
            ("opis_piersi_005.txt", ExtractionStatus.COMPLETED),
            ("skan_opisu_006.jpeg", ExtractionStatus.PENDING),
        ]

        for filename, state in samples:
            path = f"{UNASSIGNED_REPORT_PREFIX}{filename}"

            report, _ = ExtractionResult.objects.get_or_create(
                study=None,
                report_path=path,
            )

            report.status = state
            report.uncertainty = None

            report.generated_report = None
            report.accepted_report = None

            report.accepted_by = None
            report.accepted_at = None
            report.model = None

            report.save()