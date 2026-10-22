import json
import re

from pydantic import ValidationError

from .schema import EkstrakcjaBadania

_CODE_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class ParseError(Exception):
    pass


def parse_response(text: str) -> EkstrakcjaBadania:
    candidate = _json_candidate(text)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Odpowiedź nie jest poprawnym JSON: {exc}") from exc
    try:
        return EkstrakcjaBadania.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()[:10]
        )
        raise ParseError(f"JSON niezgodny ze schematem: {problems}") from exc


def _json_candidate(text: str) -> str:
    fenced = _CODE_FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ParseError("W odpowiedzi nie ma obiektu JSON.")
    return text[start : end + 1]
