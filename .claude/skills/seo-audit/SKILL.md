---
name: seo-audit
description: Run a structured SEO audit of a website, page or sitemap and produce a prioritised findings report. Use when asked to audit, review or improve search visibility, crawlability, indexing, on-page SEO, structured data or Core Web Vitals for NIIT web properties.
---

# SEO Audit

Produce an evidence-based, prioritised SEO audit. Every finding must cite where it was
observed and how it was measured. Never invent scores or rankings.

## Inputs

Confirm these before starting. Ask if any are missing and the answer changes the work.

- **Target**: a URL, list of URLs, or sitemap. Default scope is `https://niit.edu.pk`.
- **Environment**: production or staging. Crawl production read-only and politely.
- **Focus**: full audit, technical only, on-page only, or a single page.
- **Baseline**: a previous report in `reports/` to compare against, if one exists.

## Procedure

1. **Reconnaissance**
   - Fetch `robots.txt`, `sitemap.xml` and the home page. Note the CMS, framework,
     hosting and CDN if detectable.
   - Record the crawl date, user agent and any rate limit applied.

2. **Technical SEO**
   - Crawlability: robots directives, `noindex`/`nofollow`, canonical tags, redirect
     chains, 4xx/5xx responses, orphan pages, sitemap coverage vs discovered URLs.
   - Indexing: duplicate content, parameter handling, pagination, hreflang if present.
   - Performance: Core Web Vitals (LCP, INP, CLS) from Lighthouse or PageSpeed
     Insights. Report lab vs field data separately.
   - Rendering: JavaScript-dependent content, lazy-loaded critical content, blocked
     resources.
   - Security signals: HTTPS everywhere, mixed content, HSTS, valid certificate.
   - Mobile: viewport, tap targets, responsive images.

3. **On-page SEO**
   - Title tags, meta descriptions, heading hierarchy, image alt text, internal link
     structure, anchor text quality, URL structure.
   - Structured data: validate JSON-LD for `Organization`, `EducationalOrganization`,
     `Course`, `Event`, `BreadcrumbList` and `FAQPage` where relevant.
   - Content: thin or duplicate pages, outdated programme or admissions information,
     keyword coverage for priority terms (programmes, admissions, faculty, research).

4. **Off-page and authority** (only if tooling and access are available)
   - Backlink profile, referring domains, brand mentions. State the data source.

5. **Accessibility overlap**
   - Flag accessibility defects found along the way (missing alt text, colour
     contrast, form labels). They are reported as findings, not deferred.

## Severity scale

| Level | Meaning |
|-------|---------|
| Critical | Blocks indexing or breaks the site for users (noindex on key pages, 5xx, broken HTTPS) |
| High | Materially hurts ranking or UX (poor CWV, missing titles, redirect chains) |
| Medium | Clear improvement with moderate effort (thin descriptions, weak internal linking) |
| Low | Polish and hygiene (alt text on decorative images, minor schema gaps) |

## Output

Write the report to `reports/<yyyy-mm-dd>-<target-slug>.md` with this structure:

```
# SEO Audit: <target>  (<date>)

## Summary
Three to five sentences. Overall health, top three issues, biggest quick win.

## Scorecard
| Area | Status | Notes |

## Findings
For each finding:
### [Severity] Short title
- Where: URL(s) or pattern
- Evidence: what was observed and the tool or command used
- Impact: why it matters
- Fix: concrete recommendation, with code or config where useful
- Effort: S / M / L

## Prioritised action plan
Ordered list, critical first. Group items that ship together.

## Method and limitations
Tools, dates, sample size, anything not checked and why.
```

Also give the user a short summary in chat with the top findings and the report path.

## Rules

- Respect `robots.txt` and keep crawl concurrency low against production.
- Do not submit URLs to search engines or change any live configuration during an audit.
- Do not report a metric you did not measure. Write "not measured" instead.
- When a fix requires code, hand off to `/fullstack-development` with the finding ID.
