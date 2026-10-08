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
    IssuesArgs,
    NoArgs,
    ToolContext,
    ToolError,
    get_project_summary,
    get_seo_issues,
    run_tool,
)
from app.modules.ai.topics import admit_missing, evidence_for, focus_issue_ids
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
        "top_open_issues": evidence.get("top_open_issues"),
        "for_this_question": evidence.get("for_this_question"),
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
    # The highest-priority open issues, so questions about what to do next can be answered
    # even by a model that does not call a tool first.
    try:
        evidence["top_open_issues"] = await get_seo_issues(tools, IssuesArgs(limit=10))
    except ToolError:
        evidence["top_open_issues"] = None
    # The issues and page the question is about, so the model answers from them instead
    # of from the generic priorities.
    found = await evidence_for(tools, question)
    if found:
        evidence["for_this_question"] = found
    focus = focus_issue_ids(found, evidence["top_open_issues"])
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
                "arguments, and leave 'answer' empty. When the evidence is enough, use action "
                "'answer' and write the complete answer for the person in 'answer', in full "
                "sentences. Put the references of issues you rely on (such as issue-a) in "
                "issue_ids.\n"
                "When the evidence has for_this_question, answer from it first: it holds the open "
                "issues (with their total) and the page the question is about. Cite those "
                "issues. When a topic there has open_issues_total 0, say that the latest crawl "
                "found no open issues of that kind.\n"
                "For questions about priorities, next steps, where to start or the way forward, "
                "answer from top_open_issues (already ordered by priority) and the scores: name the "
                "most important issues by title, say briefly why each matters and what to do, and "
                "cite them. Say that the data has no answer only when the question needs data this "
                "platform does not have, such as traffic, rankings, keywords or competitors."
            ),
        },
    ]
    attempts = 0
    tools_used: list[str] = []
    retried_grounding = False
    # A grounded answer that cites nothing: kept while the model is asked to cite, so the
    # follow-up can only improve the result.
    uncited: tuple[AgentAnswer, GroundingReport] | None = None
    for _ in range(MAX_TOOL_CALLS + 4):
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
                # AgentStep guarantees text here: an empty answer is sent back to the model
                # with the error instead of being replaced by a stock sentence.
                answer=admit_missing(step.answer, evidence.get("for_this_question")),
                issue_ids=step.issue_ids,
                tools_used=tools_used,
            )
        )
        facts = _grounding_facts(evidence)
        report = check_output(
            answer.model_copy(update={"tools_used": []}), facts, issue_ids_in(facts)
        )
        # An answer that cites none of the issues the question is about (no issues, or
        # only unrelated ones) is asked once to cite them.
        if report.passed and focus and not focus & set(answer.issue_ids) and uncited is None:
            uncited = (answer, report)
            candidates = ", ".join(sorted(r for r in map(refs.reference, focus) if r))
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your answer cites none of the issues this question is about, but it "
                        "relies on them. Reply again with action 'answer', the same answer text, "
                        "and the references of the issues it relies on in issue_ids, chosen "
                        f"from: {candidates}."
                    ),
                }
            )
            continue
        if report.passed:
            return answer, evidence, report, attempts
        if uncited is not None:
            return uncited[0], evidence, uncited[1], attempts
        if retried_grounding:
            return answer, evidence, report, attempts
        retried_grounding = True
        messages.append(
            {
                "role": "user",
                "content": report.retry_instruction() + " Answer the question again.",
            }
        )
    raise ToolError("The assistant did not reach an answer within the allowed number of steps.")
