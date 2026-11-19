"""The CLI (``python -m workers.extraction``) through ``main(argv)``, with a scripted LLM."""

import json

import pytest

from workers.extraction import __main__ as cli
from workers.extraction.evaluation import tracking
from workers.extraction.pipeline import Extractor
from workers.extraction.tests.factories import (
    REPORT,
    FakeLLM,
    answer_json,
    error_result,
    provenance,
    result,
)

from .conftest import write_predictions


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Experiment records go to tmp_path; git is not asked; LLM/OCR env vars don't leak in."""
    monkeypatch.setattr(tracking, "EXPERIMENTS_DIR", tmp_path / "experiments")
    monkeypatch.setattr(tracking, "git_state", lambda: {"git_commit": "abc123", "git_dirty": False})
    for name in ("OCR_ENGINE", "OCR_ORIENTATION", "LLM_PROVIDER", "LLM_TIMEOUT", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)


def use_llm(monkeypatch, *answers):
    llm = FakeLLM(answers)
    monkeypatch.setattr(cli, "_extractor", lambda settings: Extractor(llm))
    return llm


def reports_dir(tmp_path, *names):
    directory = tmp_path / "reports"
    directory.mkdir()
    for name in names:
        (directory / name).write_text(REPORT, encoding="utf-8")
    return directory


def test_run_writes_one_json_line_per_document(monkeypatch, tmp_path):
    # Arrange
    use_llm(monkeypatch, answer_json(), answer_json())
    out = tmp_path / "run.jsonl"

    # Act
    code = cli.main(["run", str(reports_dir(tmp_path, "a.txt", "b.txt")), "--out", str(out)])

    # Assert
    lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert code == 0
    assert [(r["source"], r["status"]) for r in lines] == [("a.txt", "ok"), ("b.txt", "ok")]


def test_run_records_a_failed_document_and_continues(monkeypatch, tmp_path, capsys):
    # Arrange: a.txt fails parsing twice, b.txt succeeds.
    use_llm(monkeypatch, "nie wiem", "nadal nie wiem", answer_json())
    out = tmp_path / "run.jsonl"

    # Act
    code = cli.main(["run", str(reports_dir(tmp_path, "a.txt", "b.txt")), "--out", str(out)])

    # Assert
    lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert code == 1
    assert [r["status"] for r in lines] == ["error", "ok"]
    assert "Done: 1 ok, 1 failed" in capsys.readouterr().err


def test_run_rejects_an_unsupported_file(tmp_path, capsys):
    # Arrange
    path = tmp_path / "opis.pdf"
    path.write_bytes(b"x")

    # Act
    code = cli.main(["run", str(path)])

    # Assert
    assert code == 1
    assert "unsupported file type" in capsys.readouterr().err


def test_eval_prints_the_table_and_saves_the_report(gold_dir, tmp_path, capsys):
    # Arrange
    predictions = write_predictions(
        tmp_path / "run.jsonl", [result("doc1.jpg"), result("doc2.jpg")]
    )
    report_path = tmp_path / "report.json"

    # Act
    code = cli.main(
        ["eval", str(predictions), "--gold", str(gold_dir), "--report", str(report_path)]
    )

    # Assert
    assert code == 0
    assert "documents: 2 evaluated" in capsys.readouterr().out
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["summary"]["field_accuracy"] == 1.0


def test_eval_without_gold_files_fails(tmp_path, capsys):
    # Arrange
    predictions = write_predictions(tmp_path / "run.jsonl", [result("doc1.jpg")])
    (tmp_path / "empty").mkdir()

    # Act
    code = cli.main(["eval", str(predictions), "--gold", str(tmp_path / "empty")])

    # Assert
    assert code == 1
    assert "No gold files" in capsys.readouterr().err


def test_gold_init_creates_skeletons_and_keeps_existing_files(tmp_path):
    # Arrange
    out_dir = tmp_path / "gold"
    out_dir.mkdir()
    (out_dir / "doc3.json").write_text("poprawione ręcznie", encoding="utf-8")
    predictions = write_predictions(
        tmp_path / "run.jsonl",
        [result("doc1.jpg"), error_result("doc2.jpg"), result("doc3.jpg")],
    )

    # Act
    code = cli.main(["gold-init", str(predictions), "--out-dir", str(out_dir)])

    # Assert
    assert code == 0
    created = json.loads((out_dir / "doc1.json").read_text(encoding="utf-8"))
    assert created["source"] == "doc1.jpg"
    assert created["data"]["wniosek"]["birads"] == "3"
    assert not (out_dir / "doc2.json").exists()
    assert (out_dir / "doc3.json").read_text(encoding="utf-8") == "poprawione ręcznie"


def test_experiment_records_an_existing_run_and_diffs_the_next_one(gold_dir, tmp_path, capsys):
    # Arrange
    first = write_predictions(tmp_path / "first.jsonl", [result("doc1.jpg"), result("doc2.jpg")])
    second = write_predictions(
        tmp_path / "second.jsonl",
        [
            result("doc1.jpg", provenance=provenance(few_shot=0)),
            error_result("doc2.jpg", provenance=provenance(few_shot=0)),
        ],
    )
    gold = ["--gold", str(gold_dir)]

    # Act
    code_1 = cli.main(["experiment", "baseline", "--predictions", str(first), "--note", "h", *gold])
    capsys.readouterr()
    code_2 = cli.main(["experiment", "few-shot-0", "--predictions", str(second), *gold])
    output = capsys.readouterr().out

    # Assert
    records = tracking.load_records()
    assert (code_1, code_2) == (0, 0)
    assert [(r["id"], r["name"]) for r in records] == [("001", "baseline"), ("002", "few-shot-0")]
    assert records[0]["hypothesis"] == "h"
    assert records[1]["config"]["few_shot"] == 0
    assert "vs 001 baseline:" in output
    assert "few_shot: 1 -> 0" in output
    assert "Opis badania" not in json.dumps(records, ensure_ascii=False)


def test_experiments_lists_the_history(gold_dir, tmp_path, capsys):
    # Arrange
    predictions = write_predictions(tmp_path / "run.jsonl", [result("doc1.jpg")])
    cli.main(["experiment", "baseline", "--predictions", str(predictions), "--gold", str(gold_dir)])
    capsys.readouterr()

    # Act
    code = cli.main(["experiments"])

    # Assert
    output = capsys.readouterr().out
    assert code == 0
    assert "001  baseline" in output
    assert "fake-model" in output


def test_experiments_without_history(capsys):
    # Act
    code = cli.main(["experiments"])

    # Assert
    assert code == 0
    assert "No experiments yet." in capsys.readouterr().out


@pytest.mark.parametrize(
    ("variable", "value", "message"),
    [
        ("LLM_TIMEOUT", "abc", "LLM_TIMEOUT='abc' is not valid"),
        ("LLM_PROVIDER", "foo", "Unknown LLM provider 'foo'"),
    ],
)
def test_bad_configuration_is_a_one_line_error(
    monkeypatch, tmp_path, capsys, variable, value, message
):
    # Arrange
    monkeypatch.setenv(variable, value)

    # Act
    code = cli.main(["run", str(reports_dir(tmp_path, "a.txt"))])

    # Assert
    err = capsys.readouterr().err
    assert code == 1
    assert err.startswith("Error: ")
    assert message in err
    assert "Traceback" not in err


def test_unknown_ocr_engine_is_a_one_line_error(monkeypatch, tmp_path, capsys):
    # Arrange
    directory = tmp_path / "scans"
    directory.mkdir()
    (directory / "skan.jpg").write_bytes(b"x")
    monkeypatch.setattr(
        cli, "_extractor", lambda settings: Extractor(FakeLLM(), ocr_engine=settings.ocr_engine)
    )

    # Act
    code = cli.main(["run", str(directory), "--ocr", "foo"])

    # Assert
    err = capsys.readouterr().err
    assert code == 1
    assert "Error: Unknown OCR engine 'foo'" in err
