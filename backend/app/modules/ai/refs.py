"""Short issue references for prompts.

Small local models often mistype 36-character issue ids, which the grounding check then
rightly rejects as references to issues that were never provided. So the model is shown
short, letter-only references ("issue-a", "issue-b", ...) instead, and they are mapped back
to the real ids before grounding and before anything is stored. Letters only, so the
references never add numbers that the grounding check would treat as facts.
"""

import re
from typing import Any

from pydantic import BaseModel, ValidationError

_REF = re.compile(r"\bissue-([a-z]{1,3})\b", re.I)


def _letters(index: int) -> str:
    text = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        text = chr(97 + rest) + text
    return text


class IssueRefs:
    def __init__(self) -> None:
        self._ref_of: dict[str, str] = {}
        self._id_of: dict[str, str] = {}
        self._title_of: dict[str, str] = {}

    def _ref(self, issue_id: str, title: str | None = None) -> str:
        ref = self._ref_of.get(issue_id)
        if ref is None:
            ref = f"issue-{_letters(len(self._ref_of))}"
            self._ref_of[issue_id], self._id_of[ref] = ref, issue_id
        if title:
            self._title_of.setdefault(ref, title)
        return ref

    def shorten(self, value: Any) -> Any:
        """A copy of the evidence with every issue id replaced by its short reference."""
        if isinstance(value, dict):
            copy = {k: self.shorten(v) for k, v in value.items()}
            if "rule_id" in value and "id" in value:
                copy["id"] = self._ref(str(value["id"]), value.get("title"))
            if isinstance(value.get("issue_ids"), list):
                copy["issue_ids"] = [self._ref(str(i)) for i in value["issue_ids"]]
            return copy
        if isinstance(value, list):
            return [self.shorten(v) for v in value]
        return value

    def resolve(self, value: str) -> str:
        """The real id for a reference; anything else is returned unchanged."""
        return self._id_of.get(value.strip().lower(), value)

    def expand_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {k: self.resolve(v) if isinstance(v, str) else v for k, v in arguments.items()}

    def _with_titles(self, text: str) -> str:
        """References the model wrote in prose, replaced by the issue's title."""

        def title(match: re.Match[str]) -> str:
            name = self._title_of.get(match.group(0).lower())
            return f"“{name}”" if name else match.group(0)

        return _REF.sub(title, text)

    @staticmethod
    def _same_length(text: str) -> str:
        """References in prose as "issue A": readable, and never longer than the original."""
        return _REF.sub(lambda m: f"issue {m.group(1).upper()}", text)

    def _expand(self, value: Any, key: str | None = None) -> Any:
        """Real ids in issue_ids fields; prose references in the short "issue A" form."""
        if isinstance(value, dict):
            return {k: self._expand(v, k) for k, v in value.items()}
        if isinstance(value, list):
            if key == "issue_ids":
                return [self.resolve(v) if isinstance(v, str) else v for v in value]
            return [self._expand(v) for v in value]
        if isinstance(value, str):
            return self._same_length(value)
        return value

    def _prose_slots(self, value: Any, path: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        """Paths of the text fields that mention a known reference."""
        if isinstance(value, dict):
            return [
                p
                for k, v in value.items()
                if k != "issue_ids"
                for p in self._prose_slots(v, (*path, k))
            ]
        if isinstance(value, list):
            return [p for i, v in enumerate(value) for p in self._prose_slots(v, (*path, i))]
        if isinstance(value, str) and any(
            m.group(0).lower() in self._title_of for m in _REF.finditer(value)
        ):
            return [path]
        return []

    def expand[M: BaseModel](self, output: M) -> M:
        """The model's output with references turned back into real ids.

        Each sentence that mentions an issue gets the issue's title when the text still fits
        its length limit, and keeps the short "issue A" form otherwise, so expanding never
        fails however close to a limit the model wrote.
        """
        original = output.model_dump(mode="json")
        data = self._expand(original)
        result = type(output).model_validate(data)
        for path in self._prose_slots(original):
            holder, source = data, original
            for step in path[:-1]:
                holder, source = holder[step], source[step]
            short = holder[path[-1]]
            holder[path[-1]] = self._with_titles(source[path[-1]])
            try:
                result = type(output).model_validate(data)
            except ValidationError:
                holder[path[-1]] = short
        return result
