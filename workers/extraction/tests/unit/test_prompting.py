import json

from workers.extraction.schema import EkstrakcjaBadania
from workers.extraction.structuring.prompting import (
    build_messages,
    describe_schema,
    load_few_shot,
    system_prompt,
)


def test_few_shot_examples_load_and_match_the_schema():
    # Act
    examples = load_few_shot()

    # Assert
    assert examples, "at least one few-shot example is expected"
    for report, output in examples:
        assert report.strip()
        EkstrakcjaBadania.model_validate(json.loads(output))


def test_without_few_shot_only_system_and_report():
    # Act
    messages = build_messages("Opis badania: zmiana 5 mm", few_shot=0)

    # Assert
    assert [m["role"] for m in messages] == ["system", "user"]


def test_one_few_shot_example_adds_a_user_assistant_pair():
    # Act
    messages = build_messages("Opis badania: zmiana 5 mm", few_shot=1)

    # Assert
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[2]["content"] == load_few_shot()[0][1]


def test_report_text_goes_into_the_last_user_message():
    # Act
    messages = build_messages("Opis badania: zmiana 5 mm", few_shot=1)

    # Assert
    assert "Opis badania: zmiana 5 mm" in messages[-1]["content"]


def test_system_prompt_lists_the_schema_fields():
    # Act
    prompt = system_prompt()
    fields = describe_schema()

    # Assert
    assert "{fields}" not in prompt
    for name in ("modalnosci", "piersi", "zmiany", "wezly", "wniosek"):
        assert name in fields
