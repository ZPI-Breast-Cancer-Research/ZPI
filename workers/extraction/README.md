# Report extraction (OCR + local LLM)

Extracts structured data from mammography / USG breast reports (text or scanned):

```
JPG → orientation → OCR → normalize → prompt → local LLM → parse + validate → checks → ExtractionResult (JSON)
```

Pure Python with no Django imports, so the module can be developed and run on its own (CLI,
notebooks); `tasks.py` is the only file that needs Django/Celery. It depends only on its own `requirements*.txt`
and does not change the backend's dependencies.

**Data never leaves the machine.** The LLM client sends requests only to hosts on
`LLM_ALLOWED_HOSTS` (default: `localhost`, `127.0.0.1`, `host.docker.internal`), ignores proxy
environment variables, and does not use any cloud SDK. Logs contain file names only, never
report text.

## Running the extraction worker (Windows / PowerShell)

The whole pipeline runs locally from the CLI, without Docker and without the rest of the app:
photo of a report → orientation → OCR → local LLM → JSON with warnings.

### 1. LLM server (LM Studio)

1. *Discover* → `Bielik-4.5B-v3.0-Instruct-GGUF` (speakleash) → download **q8_0** (~4.8 GB, fits a
   6 GB GPU).
2. *Developer* → select the model → *Load* settings:
   - **Context Length** `8192` (the model's maximum; the prompt + report + answer need ~6k tokens),
   - **GPU Offload** max (all layers on the GPU),
   - **Flash Attention** on.
3. *Load Model* → *Status: Running* (`http://localhost:1234`).

The model must have at least an 8k-token window: Bielik-7B-Instruct v0.1 (4k) does not fit the
prompt.

### 2. Python environment (once)

Python 3.12 – PaddlePaddle has no wheels for newer versions yet. From the repo root:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r workers/extraction/requirements-paddle.txt
# text reports only, without OCR: pip install -r workers/extraction/requirements.txt
```

On the first OCR run PaddleOCR downloads its models (~200 MB) to `%USERPROFILE%\.paddlex`; after
that it works offline.

### 3. Run

```powershell
.venv\Scripts\activate
$env:LLM_MODEL = "bielik-4.5b-v3.0-instruct"   # LM Studio lists every downloaded model

python -m workers.extraction models            # model ids on the server
python -m workers.extraction ping              # the LLM answers
python -m workers.extraction ocr data/reports/skan.jpg     # OCR only: rotation + text
python -m workers.extraction run data/reports/skan.jpg     # full extraction → JSON on stdout
python -m workers.extraction run data/reports --out data/exports/ext.jsonl   # whole folder
python -m workers.extraction extract opis.txt              # LLM only, from a text file
```

`run` prints one JSON per document to stdout (or `--out`, one line each) and a summary to stderr,
e.g. `ok – 1 lesions, 2 lymph nodes, LLM 34s, OCR 66s, 2 warnings`. Check `warnings` first: they point
at fields that do not follow from the report. `provenance` says which model, prompt and rotation
produced the result.

Input: a single file, or a directory where every `.jpg`/`.png`/`.txt` file is one document and
every subdirectory is one multi-page document (pages = images sorted by name). A failed document
is recorded with `"status": "error"` and the batch continues.

Useful flags: `--few-shot 0` (no example, shorter prompt), `--orientation none` (upright scans,
faster), `--model <id>` (instead of `LLM_MODEL`), `--no-structured` (do not enforce the JSON
Schema on the server).

Keep real reports under `data/` (git-ignored) and write results to `data/exports/`. Never commit
them – the output contains the report text.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `Several models available … Choose one with LLM_MODEL or --model` | set `$env:LLM_MODEL` (see `models`) |
| `Cannot connect to http://localhost:1234` | LM Studio: *Developer* → *Status: Running* |
| `HTTP 400 … context` or `Parsing: …` after 2 attempts | context too small: reload with 8192, or `--few-shot 0` |
| `ConvertPirAttribute2RuntimeAttribute not support` | PaddlePaddle 3.3 oneDNN bug on Windows CPU; the engine disables oneDNN – update this module |
| `paddlepaddle` install fails with a long path error | enable Windows long paths or use a short venv path |
| LM Studio: *0 GPUs detected* / `nvidia-smi`: *GPU access blocked by the operating system* | the dGPU is switched off: plug in the charger, set a non-battery power mode in the laptop vendor tool (e.g. MSI Center *User Scenario*), restart LM Studio |
| LLM takes 30–40 s per report | the model runs on the CPU – check *GPU Offload* and *GPU Settings* in LM Studio |

## Evaluation

`warnings` only say that a field does not follow from the text; accuracy needs hand-checked
ground truth. It lives in `data/ground_truth/` (git-ignored as a whole – it contains report text):

```
data/ground_truth/<scan>.json       # {"source": "<scan>.jpg", "data": EkstrakcjaBadania}, read by hand from the scan
data/ground_truth/text/<scan>.txt   # hand-typed report text from „Opis badania:” – reference for OCR
```

```powershell
# full pipeline (OCR + LLM) – scores extraction and OCR (character error rate vs text/)
python -m workers.extraction run data/reports --out data/eval/runs/full.jsonl
python -m workers.extraction eval data/eval/runs/full.jsonl --report data/eval/runs/full.report.json
# LLM alone on the perfect text – the gap to the run above is what OCR costs
python -m workers.extraction run data/ground_truth/text --out data/eval/runs/llm.jsonl
python -m workers.extraction eval data/eval/runs/llm.jsonl
```

`eval` uses `data/ground_truth` unless `--gold` says otherwise. New scans: `gold-init <run.jsonl>
--out-dir data/ground_truth` writes skeletons from a run (never overwrites), which must then be
corrected by hand against the scan.

Annotation conventions (where the schema leaves a choice):
- Every finding with its own size, location or BI-RADS is a lesion, including microcalcification
  clusters/areas and benign findings (cysts, lipomas; `strona` = `obustronnie` when both breasts).
  A biopsy marker or a pacemaker shadow is not.
- `zmiana.birads` comes from the conclusion line that names the lesion (the body rarely gives it).
- One `wniosek` per report: with several conclusion lines it holds the line with the highest
  BI-RADS (`tekst` without the category and the recommendation, `zalecenie` verbatim).
- Nodes are recorded per modality and side; `okolica` is the region in the nominative
  („dół pachowy”, „okolica podobojczykowa”), negated regions get `patologiczne = false`.
- `godzina` is the clock position only (`godz 9-2cm` → `"9"`, distance 2 cm).
- `piersi.zmiany_ogniskowe` is true when any lesion of that breast is described in either modality.

Documents are matched by file stem (`skan.jpg` ↔ `skan.txt` ↔ `skan.json`). Lesions, their
observations and nodes are paired by quote overlap (same modality), and `eval` reports
precision / recall / F1 for them. For each field of the paired items it reports accuracy plus
`missed` (gold has a value, prediction is null) and `spurious` (the reverse). Fields of unpaired
items are not scored, because recall already counts them. A failed document is scored as an
empty extraction. Verbatim text fields count as correct at ≥ 90 % similarity after folding case
and diacritics, and `wymiary.max_mm` compares sizes after unit conversion. A document whose text
is a few-shot example is skipped, since it would inflate the scores (`--include-leaked` to keep it).
For runs with OCR, the character error rate is the edit distance to `text/<scan>.txt` after
normalisation, with whitespace collapsed. The output contains file names and numbers only.

The top of the output is a `summary`: pooled accuracy over all scored fields, accuracy per field
group (`piersi`, MMG / USG observations, `zmiana`, `wezel`, `wniosek`), entity F1 and conclusion
BI-RADS accuracy. Use it to compare runs.

### Experiments

To keep a history of what improves the results, run changes as experiments instead of plain
`run` + `eval`:

```powershell
python -m workers.extraction experiment baseline --note "hypothesis"   # transcripts (LLM alone)
python -m workers.extraction experiment baseline-ocr --input data/reports
python -m workers.extraction experiment old-run --predictions data/eval/runs/x.jsonl  # record an existing run
python -m workers.extraction experiments                               # table of all experiments
```

Each one saves `experiments/runs/<id>_<name>.json`: the configuration (model, few-shot,
structured output, OCR, prompt / schema version **and hash**, git commit, ground-truth hash), runtime
and all scores – no report text, so records are committed with the code. Predictions go to
`data/eval/runs/<id>_<name>.jsonl` (git-ignored). The command prints the difference to the previous
experiment. The reasoning (hypothesis → result → decision) goes into
[`experiments/EXPERIMENTS.md`](experiments/EXPERIMENTS.md), and
`notebook/02_extraction_experiments.ipynb` plots the history (needs `matplotlib` and `jupyter` –
the `dev` dependency group).

## Configuration

Environment variables; the CLI flags `--ocr`, `--orientation`, `--base-url`, `--model`, `--few-shot` and
`--no-structured` override them.

| Variable | Default | |
|---|---|---|
| `OCR_ENGINE` | `paddle` | key in `ocr/registry.py` |
| `OCR_LANG` | `pl` | |
| `OCR_ORIENTATION` | `paddle` | page rotation detector: `paddle` (document orientation classifier), `none` |
| `LLM_PROVIDER` | `local_http` | key in `llm/registry.py` |
| `LLM_BASE_URL` | `http://localhost:1234/v1` | LM Studio; vLLM `:8000/v1`, Ollama `:11434/v1`; from Docker `http://host.docker.internal:1234/v1` |
| `LLM_MODEL` | empty | empty = the only model loaded on the server |
| `LLM_ALLOWED_HOSTS` | `localhost,127.0.0.1,host.docker.internal` | add only trusted on-premise servers |
| `LLM_TIMEOUT` | `300` | seconds |
| `LLM_STRUCTURED_OUTPUT` | `true` | the server constrains output to the JSON Schema |
| `EXTRACTION_FEW_SHOT` | `1` | few-shot examples per request |

## Swapping components

- **Another model:** load it on the server and pass `--model`.
- **Another server with the same API** (vLLM, Ollama, llama.cpp server): change `LLM_BASE_URL`.
- **Another LLM backend** (e.g. `transformers` in-process): a new module in `llm/` implementing
  `LLMClient` (`llm/base.py`) and one entry in `llm/registry.py`.
- **Another OCR engine:** a new module in `ocr/` implementing `OcrEngine` (`ocr/base.py`, method
  `read_page(image) -> OcrPage`), one entry in `ocr/registry.py`, and its own
  `requirements-<engine>.txt`. Import the engine library inside the class, not at module level,
  so other engines work without it installed.
- **Page orientation** is a separate step before OCR (`orientation/`), so it works with any OCR
  engine: a detector returns the correction angle (0/90/180/270), our code rotates the page
  (Pillow), and the OCR engine reads an upright image. The `paddle` detector is a separate
  classifier (PP-LCNet document orientation), not part of the OCR engine, so it keeps working when
  another OCR engine reads the text. Another detector is a new module in `orientation/`
  implementing `OrientationDetector` and one entry in `orientation/registry.py`. OCR confidence is
  not a usable orientation signal: PaddleOCR reads rotated text with full confidence.

Every result stores what produced it (`provenance`: OCR engine + version, OCR confidence,
orientation detector and per-page rotation, LLM model, prompt version, schema version), so runs with different components can be compared.

## Layout

| File | Role |
|---|---|
| `schema.py` | data contract: `EkstrakcjaBadania` (what the LLM returns – per-breast findings, lesions with MMG/USG observations, nodes, conclusion), `ExtractionResult` (envelope) |
| `pipeline.py` | entry points `extract_from_images`, `extract_from_text`, `run_ocr` |
| `ocr/` | OCR interface, PaddleOCR engine, registry |
| `orientation/` | page orientation detector (PaddleOCR document classifier), rotation, registry |
| `llm/` | LLM interface + local-host guard, HTTP client for `/v1/chat/completions`, registry |
| `normalize.py` | layout-only clean-up of OCR text (never changes words or numbers); drops the form header before „Opis badania” |
| `prompting.py`, `prompts/` | prompt, field list generated from the schema, few-shot examples |
| `parsing.py` | JSON extraction from the answer + schema validation (one retry with feedback) |
| `checks.py` | warnings: quote not found in the report, verbatim fields not in the report, numbers not in the observation's quote, shape / margin / echogenicity not supported by the quote, USG-only fields in a mammography observation, inconsistent observation links, lesion in a breast marked without focal lesions |
| `evaluation.py` | scoring predictions against gold files: entity matching, per-field accuracy, summary, OCR CER, report table (`eval`) |
| `tracking.py`, `experiments/` | experiment history: records with configuration fingerprints and scores, journal (`experiment`, `experiments`) |
| `__main__.py` | CLI |
| `tasks.py` | Celery task `extraction.run` (worker entry point, needs `backend/` on the path) |

Changing `prompts/` or `prompting.py`: bump `PROMPT_VERSION`. Changing `schema.py`: bump
`SCHEMA_VERSION` and update `prompts/few_shot/` (examples are validated against the schema at
load time). Few-shot reports must be synthetic.
