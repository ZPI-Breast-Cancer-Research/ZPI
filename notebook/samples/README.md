# Sample report for the notebooks

`synthetic17` is a made-up mammography + USG report. It describes no patient, so it can be
committed and the notebooks that use it can be committed with their outputs.

- `text/synthetic17.txt`: the report text, with a fictional header and footer; the OCR reference
- `synthetic17.json`: the gold extraction (`{"source", "data"}`, like `data/ground_truth`)
- `synthetic17.jpg`: the text as a phone photo, made with
  `RenderOptions(level=1, rotation=90, marks=True, crop=False, seed=17)` from
  `workers/extraction/datagen/render.py` (turned sideways, with pen notes over the text)

It is one of the synthetic reports in `data/synthetic/` (git-ignored). See "Synthetic reports"
in `workers/extraction/README.md`.
