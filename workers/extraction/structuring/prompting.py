import json
import types
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

from ..llm.base import Message
from ..schema import EkstrakcjaBadania

PROMPT_VERSION = "v6"
PROMPTS_DIR = Path(__file__).parent / "prompts"


@cache
def describe_schema(model: type[BaseModel] = EkstrakcjaBadania) -> str:
    lines: list[str] = []
    _describe(model, lines, indent="")
    return "\n".join(lines)


def _describe(model: type[BaseModel], lines: list[str], indent: str) -> None:
    for name, info in model.model_fields.items():
        annotation = info.annotation
        nested = _nested_model(annotation)
        line = f"{indent}- {name}: {_type_name(annotation)}"
        if info.description:
            line += f" — {info.description}"
        lines.append(line)
        if nested is not None:
            _describe(nested, lines, indent + "    ")


def _nested_model(annotation: Any) -> type[BaseModel] | None:
    for arg in (annotation, *get_args(annotation)):
        if isinstance(arg, type) and issubclass(arg, BaseModel):
            return arg
    return None


def _type_name(annotation: Any) -> str:
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        args = [a for a in get_args(annotation) if a is not type(None)]
        inner = " | ".join(_type_name(a) for a in args)
        return f"{inner} | null"
    if origin is list:
        (item,) = get_args(annotation)
        return f"lista[{_type_name(item)}]"
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return "jedno z: " + ", ".join(f'"{m.value}"' for m in annotation)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return "obiekt"
    return {str: "tekst", int: "liczba całkowita", float: "liczba", bool: "true/false"}.get(
        annotation, str(annotation)
    )


# (report text, the expected answer as JSON) of one few-shot example
Example = tuple[str, str]


@cache
def load_few_shot() -> list[Example]:
    """The examples in prompts/few_shot/: the CLI and experiments use them; the Celery worker
    takes the examples of the extraction version in use (``examples_from_version``)."""
    return examples_from_version(
        [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((PROMPTS_DIR / "few_shot").glob("*.json"))
        ]
    )


def examples_from_version(items: list[dict[str, Any]]) -> list[Example]:
    """``module_version.few_shot_examples`` ([{"report", "output"}, ...]) for the prompt; each
    output is checked against the schema, so a broken example fails here, not in the LLM."""
    examples = []
    for item in items:
        output = EkstrakcjaBadania.model_validate(item["output"])
        examples.append((item["report"], output.model_dump_json(exclude_none=False)))
    return examples


@cache
def system_prompt() -> str:
    system = (PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
    return system.replace("{fields}", describe_schema())


def build_messages(
    report_text: str, *, few_shot: int = 1, examples: list[Example] | None = None
) -> list[Message]:
    """``examples`` (all of them) when given, otherwise the first ``few_shot`` example files."""
    messages: list[Message] = [{"role": "system", "content": system_prompt()}]
    chosen = examples if examples is not None else load_few_shot()[:few_shot]
    for example_report, example_output in chosen:
        messages.append({"role": "user", "content": _user_content(example_report)})
        messages.append({"role": "assistant", "content": example_output})
    messages.append({"role": "user", "content": _user_content(report_text)})
    return messages


def _user_content(report_text: str) -> str:
    return f"Opis badania:\n<<<\n{report_text}\n>>>"
