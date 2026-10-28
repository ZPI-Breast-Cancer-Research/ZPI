import argparse
import sys
import time
from dataclasses import replace
from pathlib import Path

from .config import Settings
from .llm import LLMError, get_llm_client
from .ocr import IMAGE_SUFFIXES, OcrEngine, OcrError, get_ocr_engine
from .orientation import OrientationDetector, OrientationError, get_orientation_detector
from .pipeline import extract_from_images, extract_from_text, run_ocr
from .schema import ExtractionResult

TEXT_SUFFIXES = {".txt"}


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    try:
        return args.handler(args, _settings(args))
    except (LLMError, OcrError, OrientationError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_models(args: argparse.Namespace, settings: Settings) -> int:
    client = get_llm_client(settings)
    for model in client.list_models():
        print(model)
    return 0


def cmd_ping(args: argparse.Namespace, settings: Settings) -> int:
    client = get_llm_client(settings)
    response = client.complete(
        [{"role": "user", "content": "Odpowiedz jednym słowem: OK"}], temperature=0.0
    )
    print(f"{settings.llm_base_url} | model: {response.model} | {response.seconds:.1f}s")
    print(response.text.strip())
    return 0


def cmd_ocr(args: argparse.Namespace, settings: Settings) -> int:
    ocr = _ocr_engine(settings)
    orientation = _orientation(settings)
    for source, files in _documents(args.input):
        if files[0].suffix.lower() in TEXT_SUFFIXES:
            continue
        result = run_ocr(files, ocr, orientation)
        confidence = result.mean_confidence
        rotations = ", ".join(f"{page.rotation}°" for page in result.pages if page.rotation)
        print(
            f"===== {source} | {result.engine} {result.engine_version} | "
            f"confidence: {confidence:.2f} | {result.seconds:.1f}s"
            if confidence is not None
            else f"===== {source} | {result.engine} {result.engine_version}"
        )
        if rotations:
            print(f"rotated: {rotations}")
        print(result.text)
    return 0


def cmd_extract(args: argparse.Namespace, settings: Settings) -> int:
    client = get_llm_client(settings)
    text = args.input.read_text(encoding="utf-8")
    result = extract_from_text(
        text,
        client,
        source=args.input.name,
        few_shot=settings.few_shot_examples,
        structured_output=settings.llm_structured_output,
    )
    print(result.model_dump_json(indent=2))
    return 0 if result.status == "ok" else 1


def cmd_run(args: argparse.Namespace, settings: Settings) -> int:
    documents = _documents(args.input)
    if not documents:
        print(f"No .txt files or images in {args.input}", file=sys.stderr)
        return 1

    client = get_llm_client(settings)
    needs_ocr = any(files[0].suffix.lower() not in TEXT_SUFFIXES for _, files in documents)
    ocr: OcrEngine | None = _ocr_engine(settings) if needs_ocr else None
    orientation = _orientation(settings) if ocr else None
    out = args.out.open("w", encoding="utf-8") if args.out else sys.stdout
    failures = 0
    started = time.perf_counter()
    try:
        for i, (source, files) in enumerate(documents, start=1):
            if files[0].suffix.lower() in TEXT_SUFFIXES:
                result = extract_from_text(
                    files[0].read_text(encoding="utf-8"),
                    client,
                    source=source,
                    few_shot=settings.few_shot_examples,
                    structured_output=settings.llm_structured_output,
                )
            else:
                assert ocr is not None
                result = extract_from_images(
                    files,
                    ocr,
                    client,
                    orientation=orientation,
                    source=source,
                    few_shot=settings.few_shot_examples,
                    structured_output=settings.llm_structured_output,
                )
            failures += result.status != "ok"
            out.write(result.model_dump_json() + "\n")
            out.flush()
            print(f"[{i}/{len(documents)}] {source}: {_summary(result)}", file=sys.stderr)
    finally:
        if args.out:
            out.close()

    print(
        f"Done: {len(documents) - failures} ok, {failures} failed, "
        f"{time.perf_counter() - started:.0f}s",
        file=sys.stderr,
    )
    return 0 if failures == 0 else 1


def _documents(path: Path) -> list[tuple[str, list[Path]]]:
    if path.is_file():
        return [(path.name, [path])]
    if not path.is_dir():
        raise ValueError(f"{path} does not exist")

    documents = []
    for entry in sorted(path.iterdir()):
        suffix = entry.suffix.lower()
        if entry.is_file() and (suffix in IMAGE_SUFFIXES or suffix in TEXT_SUFFIXES):
            documents.append((entry.name, [entry]))
        elif entry.is_dir():
            pages = sorted(p for p in entry.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
            if pages:
                documents.append((entry.name, pages))
    return documents


def _summary(result: ExtractionResult) -> str:
    if result.status != "ok":
        return f"ERROR – {result.error}"
    assert result.data is not None
    parts = [
        f"{len(result.data.zmiany)} lesions",
        f"{len(result.data.wezly)} lymph nodes",
        f"LLM {result.llm_seconds}s",
    ]
    if result.ocr_seconds is not None:
        parts.append(f"OCR {result.ocr_seconds}s")
    if result.warnings:
        parts.append(f"{len(result.warnings)} warnings")
    return "ok – " + ", ".join(parts)


def _ocr_engine(settings: Settings) -> OcrEngine:
    print(f"Loading OCR: {settings.ocr_engine} ...", file=sys.stderr)
    return get_ocr_engine(settings.ocr_engine, lang=settings.ocr_lang)


def _orientation(settings: Settings) -> OrientationDetector | None:
    if settings.ocr_orientation != "none":
        print(f"Loading orientation detector: {settings.ocr_orientation} ...", file=sys.stderr)
    return get_orientation_detector(settings.ocr_orientation)


def _settings(args: argparse.Namespace) -> Settings:
    settings = Settings.from_env()
    overrides = {
        "ocr_engine": args.ocr,
        "ocr_orientation": args.orientation,
        "llm_base_url": args.base_url,
        "llm_model": args.model,
        "few_shot_examples": args.few_shot,
    }
    settings = replace(settings, **{k: v for k, v in overrides.items() if v is not None})
    if args.no_structured:
        settings = replace(settings, llm_structured_output=False)
    return settings


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ocr", help="OCR engine (env OCR_ENGINE, default: paddle)")
    common.add_argument(
        "--orientation",
        help="page orientation detector: paddle, none (env OCR_ORIENTATION, default: paddle)",
    )
    common.add_argument("--base-url", help="local LLM server URL (env LLM_BASE_URL)")
    common.add_argument("--model", help="model id on the server (env LLM_MODEL)")
    common.add_argument("--few-shot", type=int, help="few-shot examples (env EXTRACTION_FEW_SHOT)")
    common.add_argument(
        "--no-structured",
        action="store_true",
        help="do not ask the server to enforce the JSON Schema",
    )

    parser = argparse.ArgumentParser(
        prog="python -m workers.extraction",
        description="Extract structured data from mammography / USG reports.",
    )
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("models", parents=[common], help="list models on the LLM server")
    p.set_defaults(handler=cmd_models)

    p = sub.add_parser("ping", parents=[common], help="check the LLM server answers")
    p.set_defaults(handler=cmd_ping)

    p = sub.add_parser("ocr", parents=[common], help="OCR only: print recognised text")
    p.add_argument("input", type=Path, help="image, or directory of images / page folders")
    p.set_defaults(handler=cmd_ocr)

    p = sub.add_parser("extract", parents=[common], help="LLM only: extract from a .txt file")
    p.add_argument("input", type=Path)
    p.set_defaults(handler=cmd_extract)

    p = sub.add_parser("run", parents=[common], help="full pipeline over a file or directory")
    p.add_argument("input", type=Path)
    p.add_argument("--out", type=Path, help="JSONL output file (default: stdout)")
    p.set_defaults(handler=cmd_run)
    return parser


if __name__ == "__main__":
    sys.exit(main())
