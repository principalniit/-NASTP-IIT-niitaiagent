# Organisation-specific AI test sets

`ai-eval` runs a built-in starter set that works for any site. Files here add questions
about one organisation's own sites, using pages and findings from its real crawls. They
are data, not code: the engine has no knowledge of any organisation.

```
uv run python -m app.cli ai-eval --org niit --project "NIIT website" --cases evals/niit-website.json
uv run python -m app.cli ai-eval --org niit --project "Admissions" --cases evals/niit-admissions.json
```

Expectations (all optional):

| Field | Passes when |
|-------|-------------|
| `cites_top_issues` | the answer cites one of the five highest-priority open issues |
| `cites_rules` | it cites an open issue whose rule id starts with one of these; if the site has none, it says none were found |
| `cites_page_issues` | the question names a page, and the answer cites an open issue on it, or says none were found |
| `answers` | it gives a real answer, not only "the data has no answer" |
| `admits_missing_data` | it opens by saying the platform has no such data |

Questions people mark "not helpful" in the dashboard can be exported as more cases with
`ai-feedback-cases --org <slug> --out feedback-cases.json`.

When a site changes (for example its titles are fixed), a case may correctly answer "none
found"; update the case rather than the code.
