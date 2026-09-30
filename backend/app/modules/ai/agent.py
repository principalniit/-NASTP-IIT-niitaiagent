"""Question answering with a bounded, allow-listed tool loop."""

import json
from typing import Any

from app.modules.ai.grounding import GroundingReport, check_output
from app.modules.ai.outputs import AgentAnswer, AgentStep
from app.modules.ai.provider import Message
from app.modules.ai.refs import IssueRefs
from app.modules.ai.tasks import issue_ids_in
from app.modules.ai.tools import (
    TOOLS,
    NoArgs,
    ToolContext,
    ToolError,
    get_project_summary,
    run_tool,
)
from app.providers.interfaces import AIProvider

MAX_TOOL_CALLS = 4


def tool_catalogue() -> list[dict[str, Any]]:
    return [
        {"name": t.name, "description": t.description, "arguments": t.args.model_json_schema()}
        for t in TOOLS.values()
    ]


def _grounding_facts(evidence: dict[str, Any]) -> dict[str, Any]:
    """What an answer may rely on: the data the tools returned, never the model's own tool
    arguments or error messages, which echo text the model chose."""
    return {
        "project_summary": evidence["project_summary"],
        "tool_results": [
            {"tool": call["tool"], "result": call["result"]}
            for call in evidence["tool_results"]
            if not (isinstance(call["result"], dict) and "error" in call["result"])
        ],
    }


async def answer_question(
    provider: AIProvider, tools: ToolContext, system: str, question: str
) -> tuple[AgentAnswer, dict[str, Any], GroundingReport, int]:
    evidence: dict[str, Any] = {
        "project_summary": await get_project_summary(tools, NoArgs()),
        "tool_results": [],
    }
    refs = IssueRefs()  # the model sees short issue references; evidence keeps real ids
    messages: list[Message] = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"QUESTION: {question}\n\n"
                f"TOOLS you may call, one at a time:\n{json.dumps(tool_catalogue())}\n\n"
                f"EVIDENCE so far:\n{json.dumps(refs.shorten(evidence), default=str)}\n\n"
                "Reply with JSON. To look something up, use action 'call_tool' with the tool name and "
                "arguments. When the evidence is enough, or the data does not exist, use action "
                "'answer'. Put the references of issues you rely on (such as issue-a) in issue_ids."
            ),
        },
    ]
    attempts = 0
    tools_used: list[str] = []
    retried_grounding = False
    for _ in range(MAX_TOOL_CALLS + 3):
        step, used, raw = await provider.chat_structured(messages, AgentStep)
        attempts += used
        messages.append({"role": "assistant", "content": raw[:6000]})
        must_answer = len(tools_used) >= MAX_TOOL_CALLS
        if step.action == "call_tool" and not must_answer:
            name = step.tool or ""
            try:
                result = await run_tool(tools, name, refs.expand_arguments(step.arguments))
            except ToolError as exc:
                result = {"error": str(exc)}
            tools_used.append(name)
            arguments = json.dumps(step.arguments, default=str)
            evidence["tool_results"].append(
                {
                    "tool": name[:100],
                    "arguments": step.arguments
                    if len(arguments) <= 2000
                    else {"omitted": "too long"},
                    "result": result,
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"TOOL RESULT ({name}):\n{json.dumps(refs.shorten(result), default=str)}"
                    ),
                }
            )
            continue
        if step.action == "call_tool":
            messages.append(
                {
                    "role": "user",
                    "content": "No more tool calls are allowed. Answer now with the evidence you have.",
                }
            )
            continue
        answer = refs.expand(
            AgentAnswer(
                answer=step.answer
                or "The project data does not contain an answer to this question.",
                issue_ids=step.issue_ids,
                tools_used=tools_used,
            )
        )
        facts = _grounding_facts(evidence)
        report = check_output(
            answer.model_copy(update={"tools_used": []}), facts, issue_ids_in(facts)
        )
        if report.passed or retried_grounding:
            return answer, evidence, report, attempts
        retried_grounding = True
        messages.append(
            {
                "role": "user",
                "content": (
                    "Your answer was not grounded in the evidence: "
                    + "; ".join(report.violations)
                    + ". Answer again using only facts and numbers present in the evidence."
                ),
            }
        )
    raise ToolError("The assistant did not reach an answer within the allowed number of steps.")
