# AI prompts and grounding

How the AI layer builds its prompts, what evidence each task sees, how output is checked,
and how to change a prompt without making the assistant worse. Code:
`backend/app/modules/ai/`. Architecture overview: `docs/ARCHITECTURE.md` section 9.
Security controls: `docs/SECURITY.md` section 5a.

## 1. Principles

| Principle | How the code enforces it |
|-----------|--------------------------|
| The deterministic engine works without AI | Crawling, rules, scoring, issue tracking and reports never call the AI layer. `AI_PROVIDER=none` is the default, and each organisation must also turn AI on. |
| AI only explains and drafts | Tasks produce stored text, recommendations (`seo_recommendations`, status `open`, `accepted` or `dismissed`) or content drafts. Nothing an AI writes changes a website. |
| Never fabricate metrics | The system prompt forbids it, and the grounding check rejects numbers that are not in the evidence and claims about rankings, traffic, search volumes and backlinks. |
| Every claim grounded in evidence | Each task gathers evidence with read-only tools before the model runs. The evidence is stored with the analysis, and output is checked against it. |
| Drafts need human approval | AI drafts are created with `source=ai` and no author, and go through the normal review flow. Protected facts need a verified source to be approved. |
| Institutional facts only from approved content | The model is never given institutional facts to repeat. Rule 5 makes it write `[verify: ...]` where a fact is needed. See below. |

**Organisation and project data in prompts.** NIIT is data, not code. The prompts read:
- from organisation settings: the name, the language code, `brand_tone` and the first 30
  `approved_terminology` entries (the `note` field is not sent);
- from project settings: the title and description length thresholds (metadata drafts),
  the content types whose URL patterns match the page (content outlines), and the
  institutional profile's `approved_sources` as label and URL (content outlines only).

The institutional profile's description and contact details are not sent to the model.
Approved sources are used again at approval time: a protected draft cited by web address
must cite a page under one of them (`drafts/service.py`).

## 2. Prompt structure

### System prompt

`prompts.system_prompt(org_name, settings, language)` builds one system prompt used by
every task and by the question agent. Lines, in order:
1. `You are an SEO assistant helping the web team of {org_name}.`
2. `Write in the language with code '{language}'.`
3. `Brand tone: ...`, when set.
4. `Approved terminology: use 'X' instead of 'Y', 'Z'; ...`, when set.
5. `RULES`, seven numbered rules.

Key rules, verbatim:
- Rule 1: "Use only facts contained in EVIDENCE. If the answer is not in the evidence, say
  that the information is not available in the project data."
- Rule 2: "Never invent, estimate or guess numbers. This platform has no data on visitor
  numbers, keyword search volumes, backlinks or competitors: do not mention them. Google
  Search clicks, impressions and positions are known only when EVIDENCE contains
  search_performance from Google Search Console. Then quote its figures exactly, as Google
  Search figures for its period, never as all visitors and never as a forecast. Without
  it, do not mention rankings or traffic."
- Rule 3: "Never promise search results or ranking outcomes."
- Rule 4: keep observations separate from recommendations.
- Rule 5: "Do not state or change official facts such as dates, fees, eligibility,
  admission requirements or institutional claims. Where content needs such a fact, write
  [verify: <what is needed>] instead."
- Rule 6: cite issues by their short references (`issue-a`) in `issue_ids` fields, name
  them by title in sentences, and "Never cite an issue that is not in the evidence."
- Rule 7: "Reply with JSON only, matching the requested schema."

### User prompt for tasks

`prompts.user_prompt(task, evidence, schema)` produces:

```
TASK:
<task text from tasks.py>

EVIDENCE (JSON):
<json.dumps(evidence, ensure_ascii=False, default=str)>

Reply with JSON matching this schema:
<schema.model_json_schema()>
```

The question agent writes its own user message (section 4).

### Schema enforcement

`OllamaProvider.chat_structured` posts to `/api/chat` with:
- `format`: the output model's JSON schema, so Ollama constrains the reply to it;
- `options`: `temperature` 0 and `num_ctx` (`AI_CONTEXT_TOKENS`);
- `keep_alive` (`AI_KEEP_ALIVE`) and `stream: false`.

The reply is validated with Pydantic. On a validation error the model is shown the errors
("Your reply did not match the required JSON schema: ...") and asked again. Each call
allows two attempts (`max_attempts=2`); after that the task fails with a safe message.

Output models (`outputs.py`) cap every string and list length so output stays
reviewable, and ignore extra fields. `AgentStep` lists `answer` as required in its
schema, because small models otherwise reply `{"action": "answer"}` with no text. An
answer step with less than three characters of text fails validation and is sent back.

### Short issue references

`refs.IssueRefs` replaces every issue id in the evidence with a letter-only reference
(`issue-a`, `issue-b`, ...). Small models mistype 36-character ids, and letters add no
numbers for the grounding check to query. After the reply:
- references in `issue_ids` fields are mapped back to real ids;
- references written in prose become the issue title when the field still fits its
  length limit, and `issue A` otherwise;
- brackets that only list references are removed;
- issues named in prose are added to the top-level `issue_ids`, up to its limit.

Grounding and storage always use real ids.

### Prompt-injection defences

Crawled text reaches the model only as values inside the JSON evidence or inside a
`TOOL RESULT` JSON block. The prompts do not tell the model to ignore instructions in
that text; the defences are structural:
- The model has nothing dangerous to call: nine read-only tools, each bound to one
  authorised project and filtered by project and organisation, with validated arguments.
  There is no SQL, shell, file or network tool.
- Page facts are capped: text excerpt 1,500 characters, 25 headings, 10 H1s, 30 links
  each way, 30 structured-data findings, 20 affected URLs per issue. A hostile page cannot
  push the instructions out of the context window.
- Model replies echoed back into the conversation are cut to 6,000 characters.
- Output is schema-validated and grounding-checked. Answers are checked against what the
  tools returned, never against tool arguments or error messages, which echo text the
  model chose.
- Results are stored as recommendations or drafts that a person reviews.

Two inputs from people are placed in prompt text: the question (3 to 500 characters)
and the editor's goal for a content outline (up to 300 characters, appended to the task
as `Editor's goal: ...`).

### PROMPT_VERSION

`prompts.PROMPT_VERSION` (currently `2026-10.7`) is stored on every analysis
(`ai_analyses.prompt_version`) and in `ai-eval --out` results, so any output can be traced
to the prompt that produced it. The format is year, month and a sequence number.

Bump it whenever anything the model reads or must return changes: `RULES`, the system or
user prompt, task text, the agent's messages, retry instructions, topic notes, the shape
of the evidence, or an output schema.

| Version | Change (`docs/IMPLEMENTATION_PLAN.md`) |
|---------|------------------------------------------|
| 2026-10.1 | `answer` required; empty answers sent back, no stock sentence (16.2) |
| 2026-10.2 | Specific retry instructions; prose references cited; list numbering ignored (16.2) |
| 2026-10.3 | Topic evidence first and citation follow-up (16.3) |
| 2026-10.4 | "None found" limited to crawled pages; unavailable data said first (16.3) |
| 2026-10.5 | Search Console queries in metadata drafts, digits excluded (16.5a) |
| 2026-10.6 | Rule 2 allows Search Console figures when the evidence has them; conversions stay unavailable |
| 2026-10.7 | Comparisons with other institutions count as competitor data; answers that skip a detected gap are opened with it by the platform |

## 3. Task kinds

`AIKind` has six values. Requests go to `POST /projects/{id}/ai/analyses` (202) and the
worker runs them; never the web request.

| Kind | Permission | Roles | Needs | Produces |
|------|------------|-------|-------|----------|
| `management_summary` | `reports:generate` | owner, admin, SEO manager | - | Stored output; used by reports with "Include AI summary" |
| `issue_explanation` | `issues:triage` | owner, admin, SEO manager, editor | `issue_id` | One recommendation |
| `page_plan` | `issues:triage` | as above | `page_url` | One recommendation per improvement |
| `metadata_draft` | `drafts:create` | owner, admin, SEO manager, editor | `page_url` | Title and meta description drafts |
| `content_outline` | `drafts:create` | as above | `page_url`, optional `goal` | One content outline draft |
| `question` | `issues:triage` | as above | `question` | Stored answer |

Before a task is queued, `ai/service.py` checks, in order: the role's permission (403),
that AI is enabled for the platform and organisation (409 `ai_disabled`), the plan's
`ai_tasks_per_day` limit, at most `AI_MAX_ACTIVE_JOBS_PER_ORG` queued or running tasks,
and an analysed crawl (409 `not_analysed`). The issue must belong to the project, and the
page must be an HTML page in the latest analysed crawl (404 otherwise). Every request is
audit-logged as `ai.requested`.

### Management summary

- **Evidence:** `project_summary` (scores with the note that they are not a search ranking,
  open issue counts, latest crawl facts), `top_open_issues` (15, by priority) and
  `comparison` with the previous crawl, or the text "No comparison available: ...".
- **Task:** a short summary for leadership who are not SEO specialists; most important
  findings and priorities in plain language, citing references; changes only if a
  comparison is provided; data limitations, "including that the score is a site-health
  indicator and not a search ranking".
- **Output:** `headline`, `overview`, `key_findings` (1 to 8, each `statement` and
  `issue_ids`), `priorities` (1 to 6, each `action`, `reason`, `issue_ids`),
  `changes_since_previous`, `data_limitations` (up to 6).
- Fails with "This project has no analysed crawl yet" when there is none.

### Issue explanation

- **Evidence:** the issue with its description, evidence, up to 20 affected URLs, first
  detection and recurrence count; the rule's catalogue entry; the affected page's facts
  without its issue list, when the page is in the latest crawl.
- **Task:** explain to a website editor what was found, why it matters, concrete steps
  to fix it, and how to verify the fix with a new crawl.
- **Output:** `explanation`, `why_it_matters`, `steps` (1 to 8), `how_to_verify`, `caveats`,
  `issue_ids`.
- **Result:** a recommendation titled `How to fix: <issue title>`, body `explanation`,
  with the steps.

### Page plan

- **Evidence:** page facts with open issues, internal links (inbound, outbound, link
  suggestions) and structured-data findings for the page.
- **Task:** specific improvements "based only on its open issues and the page facts",
  each naming the area and citing the related references.
- **Output:** `summary`; `improvements` (up to 10), each `area` (`title`,
  `meta_description`, `headings`, `content`, `links`, `images`, `structured_data`,
  `technical`), `suggestion` and `issue_ids`.
- **Result:** one recommendation per improvement, titled `<Area>: <url>`.
- **Warnings:** any avoided term from approved terminology in the suggestions, stored in
  the grounding report.

### Metadata draft

- **Evidence:** the page, with its open issues filtered to title and meta description
  rules; `limits` (the project's `title_min_chars`, `title_max_chars`,
  `description_min_chars`, `description_max_chars`); `search_queries` when Search Console
  data is ready.
- **Search queries:** the page's top Google queries over 90 days. Queries containing any
  digit are dropped, because years, fees and figures must come from the page, never from
  what people searched for.
- **Task:** a title and description within the limits that "Describe only what the page
  text and headings say", with no added facts, figures, dates or claims, quoting the
  phrases relied on in `facts_used`. With queries: prefer their wording where the page
  covers them, and "Never add a topic the page does not cover."
- **Output:** `title` (3 to 120 characters), `meta_description` (10 to 320),
  `rationale`, `facts_used` (up to 10).
- **Warnings** (shown to reviewers, not rejections): a title or description outside
  the project's limits, and any avoided term from approved terminology. They are stored
  in the analysis's grounding report and in each draft's evidence.
- **Result:** a draft for each field whose proposal differs from the current value, with
  the rationale as reason and the related issue ids, `facts_used` and warnings as
  evidence.

### Content outline

- **Evidence:** as for a page plan, plus `content_type` (label and expected sections of
  the content types whose URL patterns match the page path, or "No content type is
  configured for this page.") and `approved_sources`.
- **Task:** a purpose and sections with headings and points, "using only information
  already on the page". Facts not in the evidence (dates, fees, eligibility, requirements,
  figures) go in `facts_needed` as `[verify: ...]` items. Questions for the editor where
  information is missing. The editor's goal is appended when given.
- **Output:** `purpose`; `sections` (1 to 8, each `heading`, `points` up to 6,
  `facts_needed` up to 5); `questions_for_editor` (up to 6).
- **Result:** one `content_outline` draft. The original is the page's current headings;
  the proposal is rendered as `Purpose:`, `## heading`, `- point`, `- [verify: ...]` lines
  and "Questions for the editor:".
- **Warnings:** any avoided term from approved terminology in the purpose, headings or
  points, stored in the grounding report and the draft's evidence.

## 4. The question agent

`agent.answer_question` answers free-text questions with a bounded tool loop.

**Refusal without a crawl.** The API refuses a question when the project has no analysed
crawl (409 `not_analysed`), and the runner refuses a queued one ("Crawl and analyse this
project before asking questions about it."). Otherwise the model would see no issues and
report a healthy site.

**Evidence before the first step:**
- `project_summary`;
- `top_open_issues`: the 10 highest-priority open issues;
- `for_this_question`: what `topics.evidence_for` selects from the question's wording;
- `tool_results`: filled as the model calls tools.

**Topic selection** (`topics.py`) is keyword matching in English. It chooses which facts
the model sees and never decides the answer.

| Detected | Evidence added |
|----------|----------------|
| Topic words (broken pages, titles, meta descriptions, headings, images, redirects, canonicals, indexing, speed, structured data, internal links, content, language, URL structure) | Up to 3 topics, each with the real `open_issues_total` and up to 8 open issues whose rule id starts with the topic's prefixes, for example `onpage.title` or `schema.` |
| A topic with no open issues | A note: the latest analysed crawl found none "on the pages it crawled. Say exactly that; do not claim more." |
| A URL or path | That page's facts and open issues, or a note that it is not in the latest crawl |
| Visitors or traffic, rankings, competitors (including comparisons with other universities, institutions, colleges, schools or sites), keywords or search volumes, backlinks, clicks or impressions, conversions or bounce rate | `not_available`, with "Start the answer by saying so in one sentence." |
| Search Console words, when data has been imported | `search_performance` (below); rankings and Google Search clicks or impressions are then no longer listed as unavailable. Conversions and bounce rate always are: Search Console has neither |
| A priority question with no topic and no missing data | A pointer to `top_open_issues`, which is ordered by priority |

**Search Console evidence** (`search_data.ai_evidence`, last 28 days): source, period, a
note that figures are Google Search clicks only and how position is defined, totals, top
10 pages and top 10 queries with `ctr_percent`, and `low_click_through_pages`: up to five
first-page pages whose click-through rate is below the site's own rate at similar
positions, with `site_ctr_percent_at_similar_positions`. Visitor totals, competitors,
backlinks and search volumes stay unavailable.

**The loop:**
1. The user message holds the question, the tool catalogue (name, description, argument
   schema), the evidence with short references, and guidance: answer from
   `for_this_question` first and cite it; answer priority questions from
   `top_open_issues`; say the data has no answer only for data the platform lacks.
2. Each step returns an `AgentStep`: `call_tool` with `tool` and `arguments`, or
   `answer` with `answer` and `issue_ids`.
3. Tool calls run one at a time. Unknown tools and invalid arguments return
   `{"error": ...}` to the model. After `MAX_TOOL_CALLS` (4) calls, a further request is
   answered with "No more tool calls are allowed. Answer now with the evidence you have."
4. An answer is expanded from references and grounding-checked against the tool data
   only (no tool arguments, no error results). When the question asked for data the
   platform does not have (`not_available`) and the answer does not say so in its first
   250 characters, `topics.admit_missing` opens it with "This platform has no data on …",
   generated from the detected gaps. A 7B model skipped the evidence note once Search
   Console figures made the evidence longer.
5. **Citation follow-up:** when the answer passes but cites none of the issues the
   question is about (no issues, or only unrelated ones), and the question matched topic,
   page or priority issues, the model is asked once to reply with the same
   text and references chosen from those issues. If the follow-up fails grounding, the
   first answer is kept.
6. A failed grounding check gets one retry with `retry_instruction()` and "Answer the
   question again." A second failure fails the task.
7. After `MAX_TOOL_CALLS + 4` (8) steps without an answer the task fails.

The nine tools:

| Tool | Returns |
|------|---------|
| `get_project_summary` | Scores, open issue counts, latest crawl facts |
| `get_crawl_status` | Status and counts of the most recent crawl |
| `get_seo_issues` | Open issues by priority, optional severity or category, limit up to 20 |
| `get_issue_evidence` | Full evidence and recommendation for one issue |
| `get_page_details` | Metadata, headings, text excerpt and open issues for one page |
| `get_internal_links` | Inbound and outbound links and link suggestions for one page |
| `get_schema_findings` | Structured data found, optionally for one page |
| `compare_crawls` | Changes between the two most recent analysed crawls |
| `get_rule` | What a rule checks and its standard recommendation |

## 5. Grounding and retries

`grounding.check_output(output, evidence, known_issue_ids)` checks every text field
except `issue_ids`. Any violation rejects the output.

| Check | Rejects |
|-------|---------|
| Numbers | Any number in the text that does not appear in the evidence. Commas and trailing zeros are normalised; UUIDs and list numbering at the start of a line ("1. ", "2) ") are ignored. |
| Issue references | Any id in an `issue_ids` field that was not in the evidence |
| "guarantee" | Promises a guaranteed outcome |
| "rank", "ranking" or "position" followed by a number | States a ranking position |
| "first" or "top" page, result, spot or position of, on or in Google, Bing or search | Promises a search position |
| "search volume" or "keyword volume" followed by of, is, are or was | States a search volume |
| A number followed by visits, visitors, searches, clicks, impressions or backlinks | States traffic or backlink figures |
| "traffic will", "would" or "should" increase, grow, double or rise | Predicts traffic |

Ranking-position and traffic-figure matches are allowed only when the evidence holds
`search_performance`, every number in the match comes from the evidence, and the
sentence contains no predictive word (will, would, could, can, might, expect, reach,
gain, more, increase, boost, grow, achieve, improve, "get you"). "80 clicks" from imported
data passes; "you will reach position 1" does not.

**Retry instruction.** `GroundingReport.retry_instruction()` names what to change: the
unsupported numbers ("Do not count, add, subtract or calculate anything yourself"), the
unknown references, and each claim to remove ("You may say that this data is not
available").

**Retry layers:**

| Layer | Where | Limit |
|-------|-------|-------|
| Schema validation | `OllamaProvider.chat_structured` | 2 attempts per call |
| Grounding, tasks | `runner._run_task` | 1 retry, then the task fails |
| Grounding, questions | `agent.answer_question` | 1 retry, then the task fails |
| Citation follow-up | `agent.answer_question` | Once; never makes the result worse |

**What is stored** on each `ai_analyses` row:
- `evidence`: the full evidence with real ids; for questions, each tool call with its
  arguments (omitted when over 2,000 characters) and result;
- `output`: only when grounding passed. Output that failed is never stored;
- `grounding`: `passed`, `violations`, `warnings`;
- `provider`, `model`, `prompt_version`, `attempts`, `duration_ms`, `error`;
- `metrics` (`AIUsage`): model calls, load time, prompt and output tokens, prompt, output
  and total model time, as Ollama reported them. Kept for failed tasks too.

The worker fails a running task that started more than `AI_TIMEOUT_SECONDS` × 16 ago
("The worker running this AI task stopped unexpectedly.").

## 6. Measuring quality

All commands run from `backend/` against one organisation, by slug.

```
uv run python -m app.cli ai-report --org niit --days 30
uv run python -m app.cli ai-eval --org niit --project "NIIT website" --out before.json
uv run python -m app.cli ai-eval --org niit --project "NIIT website" --cases evals/niit-website.json
uv run python -m app.cli ai-eval --org niit --project "Admissions" --cases evals/niit-admissions.json
uv run python -m app.cli ai-eval --org niit --project "NIIT website" --model qwen2.5:7b
uv run python -m app.cli ai-feedback-cases --org niit --out feedback-cases.json
```

**`ai-report`** (`--days` 1 to 365, default 30): per task kind, the total, completed,
failed, model calls per task, median seconds, average prompt tokens per call and cold
starts (model load over one second); models used; the ten most common failure reasons,
grouped by violation type; feedback counts, reasons and the latest complaints.

**`ai-eval`** runs a cases file through the same `_execute` path as real tasks. Each
case runs in its own session that is rolled back, so it leaves no tasks,
recommendations, drafts or usage behind. It stops if the project has never been
analysed.
- Cases: `eval_cases.json` (14 generic cases) by default, or `--cases` with
  `backend/evals/niit-website.json` (8) or `niit-admissions.json` (7).
- Case kinds: `question`, `management_summary` and `issue_explanation` (always the
  highest-priority open issue). Page plans, metadata drafts and outlines have no cases.
- Each case reports pass or fail, completed, grounded, seconds, model calls, prompt
  tokens, cold start, problems (including grounding violations) and a preview.
- `--out` saves every answer in full, the titles of cited issues, the model and
  `PROMPT_VERSION`.

`Expect` checks (all optional):

| Field | Passes when |
|-------|-------------|
| `cites_top_issues` | It cites one of the five highest-priority open issues |
| `cites_rules` | It cites an open issue whose rule id starts with one of these; if the site has none, it says none were found |
| `cites_page_issues` | The question names a page, and it cites an open issue on it or says none were found |
| `answers` | It gives a real answer, not only "the data has no answer" (checked on replies up to 200 characters) |
| `admits_missing_data` | It says the platform has no such data within its first 250 characters |

`answers` and `admits_missing_data` cannot be combined. The checks cover structure, not
how useful the wording is; read the saved answers too.

**Feedback.** Every finished result (completed or failed) shows "Helpful" and "Not
helpful" in the dashboard. "Not helpful" asks for a reason (`wrong`, `off_topic`, `vague`,
`missed_data`, `other`) and an optional comment of up to 500 characters. Anyone who can
read the project may give one verdict per result and change it
(`PUT /ai-analyses/{id}/feedback`).

**`ai-feedback-cases`** (`--days`, default 90) writes questions marked not helpful as a
cases file. Expectations follow from the wording: missing-data questions must admit it;
others must give a real answer, plus `cites_rules` when the question matches a topic
and `cites_page_issues` when it names a page. Only questions are exported.

## 7. Changing a prompt safely

1. Record a baseline on the NIIT sets with the current code:
   `ai-eval --out before-website.json` with `--cases evals/niit-website.json`, the same
   for `evals/niit-admissions.json`, and once with the default set.
2. Make the change in one place: `prompts.py`, a task in `tasks.py`, the agent's
   messages, a topic or note in `topics.py`, a retry instruction in `grounding.py`, or a
   schema in `outputs.py`.
3. Bump `PROMPT_VERSION`.
4. Do not loosen a grounding check to make a case pass. If a check is wrong, fix the check
   and add a unit test for the phrase.
5. Run the AI tests, then the full suite:
   ```
   uv run pytest tests/unit/test_ai_grounding.py tests/unit/test_ai_refs.py \
     tests/unit/test_ai_topics.py tests/unit/test_ai_provider.py \
     tests/integration/test_ai_api.py tests/integration/test_ai_evaluation.py \
     tests/security/test_ai_isolation.py
   uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest
   ```
   Tests use local fakes and never contact Ollama or live NIIT sites.
6. Re-run step 1 with `--out after-*.json`, on the same model and with the model loaded.
   Compare passed, completed and grounded counts, median seconds and average prompt tokens.
   Read the answers that changed.
7. Keep the change only if no case got worse. A case that now correctly says "none
   found" because the site changed needs the case updated, not the code
   (`backend/evals/README.md`).
8. Update this document's version table, `docs/IMPLEMENTATION_PLAN.md` (what changed,
   results before and after) and `docs/ARCHITECTURE.md` section 9 if behaviour changed.

## 8. Configuration

Server environment (`backend/app/core/config.py`, `backend/.env.example`):

| Variable | Default | Meaning |
|----------|---------|---------|
| `AI_PROVIDER` | `none` | Platform switch: `none` or `ollama`. `none` disables AI for every organisation. |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama address. Operator-only; tenants cannot change it. Requests ignore proxy variables. The container stack sets `http://ollama:11434`. |
| `OLLAMA_DEFAULT_MODEL` | empty | Model used when the organisation names none. Empty means no model, so AI stays off. |
| `AI_TIMEOUT_SECONDS` | `180` | Longest wait for one model reply |
| `AI_CONTEXT_TOKENS` | `8192` | Sent as `num_ctx`. Set explicitly because some Ollama versions cut long prompts silently. |
| `AI_KEEP_ALIVE` | `30m` | Sent as `keep_alive`: how long the model stays loaded after a task. A number with `s`, `m` or `h`; negative keeps it until Ollama stops. |
| `AI_MAX_ACTIVE_JOBS_PER_ORG` | `3` | Queued or running AI tasks per organisation |

Organisation settings:

| Setting | Effect |
|---------|--------|
| `ai.provider` | `none` (default) or `ollama`. Both this and `AI_PROVIDER` must be `ollama`. |
| `ai.model` | Ollama model, up to 100 characters; falls back to `OLLAMA_DEFAULT_MODEL` |
| `brand_tone` | Added to the system prompt (up to 1,000 characters) |
| `approved_terminology` | Preferred terms and terms to avoid. The first 30 entries go into the system prompt; all are checked in metadata drafts, content outlines and page plans. |
| Organisation language | Language code in the system prompt |
| Plan `max_ai_tasks_per_day` | Daily AI task limit, when the plan sets one |

Project settings used by tasks: the title and description length thresholds, content
types, and the institutional profile's approved sources (section 1).

`GET /organisations/{id}/ai/status` reports whether AI is enabled, the provider and
model, and whether Ollama is reachable with that model installed.
