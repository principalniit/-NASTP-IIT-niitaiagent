"""A stand-in for the Ollama HTTP API, for tests and the E2E environment only.

It implements the two endpoints the platform uses (GET /api/tags, POST /api/chat). Replies
are either scripted by the test, or generated in "auto" mode: a deterministic reply that
only repeats text and issue ids found in the evidence of the prompt, so it passes the
grounding checks. It is not a language model and says nothing about real model quality.

Run standalone: python -m tests.fixtures.fake_ollama 11500 llama3.1
"""

import json
import re
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class Raw:
    """A scripted HTTP reply other than a normal chat message."""

    status: int
    body: bytes = b"{}"


Reply = str | dict[str, Any] | Raw | Callable[[dict[str, Any]], "str | dict[str, Any] | Raw"]


def _issues(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if "rule_id" in value and "id" in value and "title" in value:
            found.append(value)
        for item in value.values():
            found.extend(_issues(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_issues(item))
    return list({i["id"]: i for i in found}.values())


def _json_after(text: str, marker: str) -> Any:
    start = text.rfind(marker)
    if start < 0:
        return {}
    try:
        value, _ = json.JSONDecoder().raw_decode(text[start + len(marker) :].lstrip())
    except ValueError:
        return {}
    return value


def _clean(text: str | None, limit: int) -> str:
    """Text from the evidence without digits, so the reply never adds numbers."""
    return re.sub(r"\s+", " ", re.sub(r"\d", "", text or "")).strip()[:limit]


def auto_reply(request: dict[str, Any]) -> dict[str, Any]:
    schema = (request.get("format") or {}).get("title", "")
    messages = request.get("messages", [])
    prompt = next((m["content"] for m in messages if m["role"] == "user"), "")
    evidence = _json_after(prompt, "EVIDENCE (JSON):")
    issues = _issues(evidence)

    if schema == "ManagementSummaryOutput":
        return {
            "headline": "The site has technical and on-page issues to address",
            "overview": "The latest crawl found open issues. The most important are listed below.",
            "key_findings": [
                {"statement": f"Open issue: {_clean(i['title'], 200)}", "issue_ids": [i["id"]]}
                for i in issues[:3]
            ]
            or [{"statement": "No open issues were found in the latest crawl.", "issue_ids": []}],
            "priorities": [
                {
                    "action": f"Fix: {_clean(i['title'], 200)}",
                    "reason": "It is one of the highest priority open issues.",
                    "issue_ids": [i["id"]],
                }
                for i in issues[:2]
            ]
            or [{"action": "Keep monitoring the site", "reason": "No open issues were found."}],
            "data_limitations": ["The score is a site-health indicator, not a search ranking."],
        }
    if schema == "IssueExplanationOutput":
        issue = evidence.get("issue", {})
        return {
            "explanation": f"The crawler found this problem: {_clean(issue.get('title'), 300)}.",
            "why_it_matters": "Search engines and visitors rely on this to understand the page.",
            "steps": [_clean(issue.get("recommendation"), 300) or "Follow the recommendation."],
            "how_to_verify": "Run a new crawl and check that the issue is marked resolved.",
            "issue_ids": [issue["id"]] if issue.get("id") else [],
        }
    if schema == "PagePlanOutput":
        page = evidence.get("page", {})
        return {
            "summary": f"Improvements for {_clean(page.get('title'), 100) or 'this page'}.",
            "improvements": [
                {
                    "area": "title" if "title" in i["rule_id"] else "content",
                    "suggestion": f"Address: {_clean(i['title'], 300)}",
                    "issue_ids": [i["id"]],
                }
                for i in issues[:5]
            ],
        }
    if schema == "MetadataDraftOutput":
        page = evidence.get("page", {})
        heading = _clean((page.get("h1") or [""])[0], 60)
        name = heading or _clean(page.get("title"), 60) or "Page"
        return {
            "title": f"{name} | Overview and details",
            "meta_description": (
                f"Read about {name}: what it covers, who it is for and where to find "
                "further information on this website."
            ),
            "rationale": "Based on the page heading; the current title and description need work.",
            "facts_used": [name],
        }
    if schema == "ContentOutlineOutput":
        page = evidence.get("page", {})
        headings = [_clean(h.split(":", 1)[-1], 100) for h in page.get("headings") or []] or [
            "Overview"
        ]
        return {
            "purpose": f"Explain {headings[0]} clearly to prospective students.",
            "sections": [
                {
                    "heading": h or "Overview",
                    "points": ["Summarise what the page already says."],
                    "facts_needed": ["[verify: current details with the owning department]"],
                }
                for h in headings[:4]
            ],
            "questions_for_editor": ["Which department owns this page?"],
        }
    if schema == "AgentStep":
        results = [m for m in messages if m["content"].startswith("TOOL RESULT")]
        if not results:
            return {"action": "call_tool", "tool": "get_seo_issues", "arguments": {"limit": 5}}
        found = _issues(_json_after(results[-1]["content"], ":\n"))
        if not found:
            return {"action": "answer", "answer": "The project data shows no open issues."}
        return {
            "action": "answer",
            "answer": f"The most important open issue is: {_clean(found[0]['title'], 300)}.",
            "issue_ids": [found[0]["id"]],
        }
    return {"error": f"fake ollama has no auto reply for {schema}"}


class FakeOllama:
    def __init__(self, models: list[str] | None = None, port: int = 0) -> None:
        self.models = models if models is not None else ["llama3.1:latest"]
        self.replies: list[Reply] = []
        self.requests: list[dict[str, Any]] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", port), self._handler())
        self.port = self._server.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeOllama":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()

    def script(self, *replies: Reply) -> None:
        self.replies.extend(replies)

    def _knows(self, model: str) -> bool:
        return model in self.models or f"{model}:latest" in self.models

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def _send(self, status: int, body: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                if self.path != "/api/tags":
                    self._send(404, b'{"error":"not found"}')
                    return
                models = [{"name": m} for m in fake.models]
                self._send(200, json.dumps({"models": models}).encode())

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                request = json.loads(self.rfile.read(length) or b"{}")
                fake.requests.append(request)
                if self.path != "/api/chat":
                    self._send(404, b'{"error":"not found"}')
                    return
                if not fake._knows(request.get("model", "")):
                    self._send(404, b'{"error":"model not found, try pulling it first"}')
                    return
                reply: Any = fake.replies.pop(0) if fake.replies else auto_reply
                if callable(reply):
                    reply = reply(request)
                if isinstance(reply, Raw):
                    self._send(reply.status, reply.body)
                    return
                content = reply if isinstance(reply, str) else json.dumps(reply)
                prompt = sum(len(str(m.get("content", ""))) for m in request.get("messages", []))
                body = {
                    "model": request.get("model"),
                    "message": {"role": "assistant", "content": content},
                    "done": True,
                    # Ollama's counters, in nanoseconds; fixed so tests can check them.
                    "total_duration": 120_000_000,
                    "load_duration": 10_000_000,
                    "prompt_eval_count": prompt // 4,
                    "prompt_eval_duration": 60_000_000,
                    "eval_count": len(content) // 4,
                    "eval_duration": 50_000_000,
                }
                self._send(200, json.dumps(body).encode())

        return Handler


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 11500
    models = sys.argv[2:] or ["llama3.1:latest"]
    server = FakeOllama(models, port)
    print(f"Fake Ollama on {server.base} with models {models}", flush=True)
    server._server.serve_forever()
