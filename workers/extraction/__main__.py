import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import TextIO

from .config import Settings
from .documents import Document, find_documents
from .errors import ExtractionError
from .evaluation import (
    evaluate,
    format_report,
    load_gold,
    load_predictions,
    load_transcripts,
    tracking,
)
from .pipeline import Extractor
from .schema import EkstrakcjaBadania, ExtractionResult

GOLD_DIR = Path("data/ground_truth")
PREDICTIONS_DIR = Path("data/eval/runs")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    try:
        return args.handler(args, _settings(args))
    except (ExtractionError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def cmd_models(args: argparse.Namespace, settings: Settings) -> int:
    for model in _extractor(settings).llm.list_models():
        print(model)
    return 0


def cmd_ping(args: argparse.Namespace, settings: Settings) -> int:
    response = _extractor(settings).llm.complete(
        [{"role": "user", "content": "Odpowiedz jednym słowem: OK"}], temperature=0.0
    )
    print(f"{settings.llm_base_url} | model: {response.model} | {response.seconds:.1f}s")
    print(response.text.strip())
    return 0


def cmd_ocr(args: argparse.Namespace, settings: Settings) -> int:
    extractor = _extractor(settings)
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
    for document in find_documents(args.input):
        if document.is_text:
            continue
        result = extractor.run_ocr(document.files)
        confidence = result.mean_confidence
        rotations = ", ".join(f"{page.rotation}°" for page in result.pages if page.rotation)
        print(
            f"===== {document.source} | {result.engine} {result.engine_version} | "
            f"confidence: {confidence:.2f} | {result.seconds:.1f}s"
            if confidence is not None
            else f"===== {document.source} | {result.engine} {result.engine_version}"
        )
        if rotations:
            print(f"rotated: {rotations}")
        print(result.text)
        if args.out_dir:
            out = args.out_dir / f"{Path(document.source).stem}.txt"
            out.write_text(result.text, encoding="utf-8")
    return 0


def cmd_extract(args: argparse.Namespace, settings: Settings) -> int:
    text = args.input.read_text(encoding="utf-8")
    result = _extractor(settings).extract_text(text, source=args.input.name)
    print(result.model_dump_json(indent=2))
    return 0 if result.status == "ok" else 1


def cmd_run(args: argparse.Namespace, settings: Settings) -> int:
    documents = _require_documents(args.input)
    if not documents:
        return 1
    out = args.out.open("w", encoding="utf-8") if args.out else sys.stdout
    try:
        results = _run_documents(documents, _extractor(settings), out)
    finally:
        if args.out:
            out.close()
    return 0 if all(r.status == "ok" for r in results) else 1


def cmd_gold_init(args: argparse.Namespace, settings: Settings) -> int:
    args.out_dir.mkdir(parents=True, exist_ok=True)
    created = kept = failed = 0
    for key, result in load_predictions(args.predictions).items():
        out = args.out_dir / f"{key}.json"
        if result.status != "ok" or result.data is None:
            failed += 1
        elif out.exists():
            kept += 1
        else:
            gold = {"source": result.source, "data": result.data.model_dump(mode="json")}
            out.write_text(json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            created += 1
    print(
        f"{created} created, {kept} already existed (kept), {failed} failed predictions skipped "
        f"-> {args.out_dir}. Correct them by hand before running eval.",
        file=sys.stderr,
    )
    return 0


def cmd_eval(args: argparse.Namespace, settings: Settings) -> int:
    gold = _require_gold(args.gold)
    if not gold:
        return 1
    report = evaluate(
        gold,
        load_predictions(args.predictions),
        transcripts=load_transcripts(args.gold),
        include_leaked=args.include_leaked,
    )
    print(format_report(report))
    if args.report:
        args.report.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 0


def cmd_experiment(args: argparse.Namespace, settings: Settings) -> int:
    gold = _require_gold(args.gold)
    if not gold:
        return 1
    exp_id = tracking.next_id()

    if args.predictions:
        predictions_path = args.predictions
        results = list(load_predictions(predictions_path).values())
    else:
        documents = _require_documents(args.input)
        if not documents:
            return 1
        PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
        predictions_path = PREDICTIONS_DIR / f"{exp_id}_{tracking.slugify(args.name)}.jsonl"
        with predictions_path.open("w", encoding="utf-8") as out:
            results = _run_documents(documents, _extractor(settings), out)

    report = evaluate(
        gold,
        {Path(r.source).stem: r for r in results},
        transcripts=load_transcripts(args.gold),
    )
    previous = tracking.load_records()
    record = tracking.build_record(
        exp_id, args.name, args.note, settings, results, report, args.gold, predictions_path
    )
    path = tracking.save_record(record)

    print(format_report(report))
    print()
    if previous:
        print(tracking.format_diff(previous[-1], record))
    print(f"Saved experiment {exp_id} -> {path}", file=sys.stderr)
    return 0


def cmd_experiments(args: argparse.Namespace, settings: Settings) -> int:
    print(tracking.format_table(tracking.load_records()))
    return 0


def _run_documents(
    documents: list[Document], extractor: Extractor, out: TextIO
) -> list[ExtractionResult]:
    """Extract every document, writing one JSON line per result as soon as it is ready."""
    results = []
    started = time.perf_counter()
    for i, document in enumerate(documents, start=1):
        result = extractor.extract(document)
        results.append(result)
        out.write(result.model_dump_json() + "\n")
        out.flush()
        print(f"[{i}/{len(documents)}] {document.source}: {_summary(result)}", file=sys.stderr)

    failures = sum(r.status != "ok" for r in results)
    print(
        f"Done: {len(results) - failures} ok, {failures} failed, "
        f"{time.perf_counter() - started:.0f}s",
        file=sys.stderr,
    )
    return results


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


def _extractor(settings: Settings) -> Extractor:
    return Extractor.from_settings(settings, log=lambda message: print(message, file=sys.stderr))


def _require_documents(path: Path) -> list[Document]:
    documents = find_documents(path)
    if not documents:
        print(f"No .txt files or images in {path}", file=sys.stderr)
    return documents


def _require_gold(directory: Path) -> dict[str, EkstrakcjaBadania]:
    gold = load_gold(directory)
    if not gold:
        print(f"No gold files (*.json) in {directory}", file=sys.stderr)
    return gold


def _settings(args: argparse.Namespace) -> Settings:
    settings = Settings.from_env()
    # gold-init / eval have no LLM or OCR options.
    overrides = {
        "ocr_engine": getattr(args, "ocr", None),
        "ocr_orientation": getattr(args, "orientation", None),
        "llm_base_url": getattr(args, "base_url", None),
        "llm_model": getattr(args, "model", None),
        "few_shot_examples": getattr(args, "few_shot", None),
    }
    settings = replace(settings, **{k: v for k, v in overrides.items() if v is not None})
    if getattr(args, "no_structured", False):
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
    p.add_argument("--out-dir", type=Path, help="also save each text as <name>.txt here")
    p.set_defaults(handler=cmd_ocr)

    p = sub.add_parser("extract", parents=[common], help="LLM only: extract from a .txt file")
    p.add_argument("input", type=Path)
    p.set_defaults(handler=cmd_extract)

    p = sub.add_parser("run", parents=[common], help="full pipeline over a file or directory")
    p.add_argument("input", type=Path)
    p.add_argument("--out", type=Path, help="JSONL output file (default: stdout)")
    p.set_defaults(handler=cmd_run)

    p = sub.add_parser("gold-init", help="gold file skeletons from predictions, to correct by hand")
    p.add_argument("predictions", type=Path, help="JSONL from run --out")
    p.add_argument("--out-dir", type=Path, required=True)
    p.set_defaults(handler=cmd_gold_init)

    p = sub.add_parser("eval", help="score predictions against gold files")
    p.add_argument("predictions", type=Path, help="JSONL from run --out")
    p.add_argument(
        "--gold",
        type=Path,
        default=GOLD_DIR,
        help=f"gold <name>.json + text/<name>.txt transcripts (default: {GOLD_DIR})",
    )
    p.add_argument("--report", type=Path, help="also save the scores as JSON")
    p.add_argument(
        "--include-leaked",
        action="store_true",
        help="also score documents that are a few-shot example",
    )
    p.set_defaults(handler=cmd_eval)

    p = sub.add_parser(
        "experiment",
        parents=[common],
        help="run + eval + save a record in experiments/runs/ (the history of what was tried)",
    )
    p.add_argument("name", help="short name, e.g. baseline, few-shot-0, bielik-11b")
    p.add_argument("--note", help="hypothesis: what was changed and what should improve")
    p.add_argument(
        "--input",
        type=Path,
        default=GOLD_DIR / "text",
        help="documents to extract: transcripts (LLM alone, default) or data/reports (OCR + LLM)",
    )
    p.add_argument(
        "--predictions", type=Path, help="record an existing run (JSONL) instead of running"
    )
    p.add_argument("--gold", type=Path, default=GOLD_DIR)
    p.set_defaults(handler=cmd_experiment)

    p = sub.add_parser("experiments", help="table of all recorded experiments")
    p.set_defaults(handler=cmd_experiments)
    return parser


if __name__ == "__main__":
    sys.exit(main())
