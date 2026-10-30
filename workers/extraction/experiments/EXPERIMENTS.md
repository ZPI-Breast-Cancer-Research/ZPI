# Extraction experiments

The journal of what was tried in `workers/extraction`, why, and what it did to the scores. The
numbers live in `runs/<id>_<name>.json` (written by `python -m workers.extraction experiment`);
this file holds the reasoning. Plots: `notebook/02_extraction_experiments.ipynb`.

## How to run an experiment

1. Make **one** change (model, prompt, few-shot, schema, OCR setting …). Bump `PROMPT_VERSION` /
   `SCHEMA_VERSION` if you touched the prompt / schema (the record also stores their hashes, so a
   forgotten bump is still visible).
2. Run it against the ground truth (`data/ground_truth/`, git-ignored):
   ```powershell
   # LLM alone, on hand-typed text (fast, isolates the LLM)
   python -m workers.extraction experiment <name> --note "<hypothesis>"
   # OCR + LLM, on the scans
   python -m workers.extraction experiment <name>-ocr --input data/reports --note "<hypothesis>"
   # list all experiments
   python -m workers.extraction experiments
   ```
   The command prints the scores and the difference to the previous experiment.
3. Add an entry below: **hypothesis → change → result → decision** (kept / reverted).
4. Commit the record together with the code change, so the record's `git_commit` points at it.

Reading the scores: the gold set has 12 reports, so one document moves a field's accuracy by ~8 pp.
Differences of a few points are noise until confidence intervals are added (queued below).
Records with a different `gold_sha` were scored against another version of the ground truth and
are not directly comparable.

## Before measurements (not measured)

State reached before the ground truth existed; changes were judged by reading outputs and the
`warnings`, not by scores.

| When | Change |
|---|---|
| 2026-10-23 (`1badc49`) | Schema v3 for MMG/USG reports (per-breast findings, lesions with MMG and USG observations, nodes, conclusion); text-based checks (`checks.py`); page orientation detector |
| 2026-10-28 (`a10c7d5`) | Prompt v6 (dimension qualifier moved from the rules into the schema description); `plugins.load_class`; error result no longer fails when the LLM server is down; readable errors for bad env vars |
| 2026-10-28 (uncommitted) | Strict JSON schema for structured output (all keys required, no extras – llama.cpp / vLLM); EXIF applied before orientation detection; checks accept „obniżonej echogeniczności” / „normoechogeniczne” |
| 2026-10-28 | Ground truth: 12 reports read by hand from `data/reports` (24 lesions, 33 observations, 33 nodes) + transcripts for OCR scoring; `eval` with per-field accuracy, entity P/R/F1, OCR CER |

Known gap before the first measurement: the few-shot example leaves `zmiana.birads` null when the
BI-RADS is only in the conclusion, while the ground truth takes it from the conclusion line that
names the lesion – expect a low `zmiana.birads` score in the baseline.

## Queue

| # | Experiment | Hypothesis |
|---|---|---|
| 001 | `baseline` – Bielik 4.5B q8_0, prompt v6, schema 3, 1 few-shot, structured, transcripts | Reference point for the LLM alone |
| 002 | `baseline-ocr` – same, `--input data/reports` | Gap to 001 = cost of OCR; CER shows how bad OCR is |
| – | Confidence intervals in `eval` (bootstrap over documents) | Infrastructure, not a model change: tells which later differences are real |
| 003 | `few-shot-0` | Does the example help or only cost context? |
| 004 | `no-structured` | Does enforcing the JSON schema change accuracy (not only parse failures)? |
| 005 | `few-shot-birads` – few-shot example takes lesion BI-RADS from the conclusion | `zmiana.birads` up, nothing else down |
| 006 | `schema-4-wnioski` – `wnioski: list[Wniosek]` | 6/12 reports have several conclusion lines; the single `wniosek` loses recommendations |
| 007 | Bigger / other model (e.g. Bielik 11B) | Upper bound for prompt-only work |

Commands for 001 and 002 (LM Studio running, model loaded):

```powershell
$env:LLM_MODEL = "bielik-4.5b-v3.0-instruct"
python -m workers.extraction experiment baseline --note "reference: Bielik 4.5B q8_0, prompt v6, schema 3, 1 few-shot, structured, transcripts"
python -m workers.extraction experiment baseline-ocr --input data/reports --note "reference with OCR: same config on the scans"
```

## Log

<!-- Newest first. Template:

### 00N `name` – YYYY-MM-DD
- **Hypothesis:** …
- **Change:** … (commit / files)
- **Result:** field_accuracy a% → b%, … (from `experiment` output); notable fields: …
- **Decision:** kept / reverted – why
-->

No measured experiments yet.
