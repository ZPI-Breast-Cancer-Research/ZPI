# Report extraction (OCR + local LLM)

Extracts structured data from scanned mammography / USG reports:

```
JPG → OCR → normalize → prompt → local LLM → parse + validate → checks → ExtractionResult (JSON)
```

Pure Python with no Django imports, so the module can be developed and run on its own (CLI,
notebooks); `tasks.py` is the only file that needs Django/Celery. It depends only on its own `requirements*.txt`
and does not change the backend's dependencies.

**Data never leaves the machine.** The LLM client sends requests only to hosts on
`LLM_ALLOWED_HOSTS` (default: `localhost`, `127.0.0.1`, `host.docker.internal`), ignores proxy
environment variables, and does not use any cloud SDK. Logs contain file names only, never
report text.

## Setup

Python 3.12 (PaddlePaddle has no wheels for the newest Python versions yet).

```bash
python -m venv .venv && .venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r workers/extraction/requirements-paddle.txt
# without OCR (text input only): pip install -r workers/extraction/requirements.txt
```

LM Studio:
1. Download a Bielik GGUF model, quantised to fit the GPU (Q4_K_M of a 7B model is ~4.5 GB).
2. Load it with the longest context the model supports. The prompt (instructions, field list,
   one few-shot example) is ~6k characters before the report and the answer; a model with a
   4k-token window (e.g. Bielik-7B-Instruct v0.1) is tight – use `--few-shot 0` with it or
   prefer a newer Bielik version with a longer window.
3. *Developer* → *Start Server* (default `http://localhost:1234`).

## Usage

Run from the repo root:

```bash
python -m workers.extraction models                     # models available on the server
python -m workers.extraction ping                       # the server answers
python -m workers.extraction ocr data/reports/skan.jpg  # OCR only: print the text
python -m workers.extraction extract opis.txt           # LLM only: from a text file
python -m workers.extraction run data/reports --out data/exports/ext.jsonl
```

`run` input: a single file, or a directory where every `.jpg`/`.png`/`.txt` file is one document
and every subdirectory is one multi-page document (pages = images sorted by name).
One JSON line per document is written; a failed document is recorded with `"status": "error"` and
the batch continues.

Keep real reports under `data/` (git-ignored). Never commit them.

## Configuration

Environment variables; the CLI flags `--ocr`, `--base-url`, `--model`, `--few-shot` and
`--no-structured` override them.

| Variable | Default | |
|---|---|---|
| `OCR_ENGINE` | `paddle` | key in `ocr/registry.py` |
| `OCR_LANG` | `pl` | |
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

Every result stores what produced it (`provenance`: OCR engine + version, OCR confidence, LLM
model, prompt version, schema version), so runs with different components can be compared.

## Layout

| File | Role |
|---|---|
| `schema.py` | data contract: `EkstrakcjaBadania` (what the LLM returns), `ExtractionResult` (envelope) |
| `pipeline.py` | entry points `extract_from_images`, `extract_from_text`, `run_ocr` |
| `ocr/` | OCR interface, PaddleOCR engine, registry |
| `llm/` | LLM interface + local-host guard, HTTP client for `/v1/chat/completions`, registry |
| `normalize.py` | layout-only clean-up of OCR text (never changes words or numbers) |
| `prompting.py`, `prompts/` | prompt, field list generated from the schema, few-shot examples |
| `parsing.py` | JSON extraction from the answer + schema validation (one retry with feedback) |
| `checks.py` | warnings: quote not found in the report, broken links between lesions |
| `__main__.py` | CLI |
| `tasks.py` | Celery task `extraction.run` (worker entry point, needs `backend/` on the path) |

Changing `prompts/` or `prompting.py`: bump `PROMPT_VERSION`. Changing `schema.py`: bump
`SCHEMA_VERSION` and update `prompts/few_shot/` (examples are validated against the schema at
load time). Few-shot reports must be synthetic.
