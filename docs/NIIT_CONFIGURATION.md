# NIIT Configuration

NIIT is configured as ordinary data: one organisation and one project. The generic
SEO engine contains no NIIT-specific code. Everything below is edited by authorised
users in the dashboard or through the API, and every change is audit-logged.

## 1. What is pre-filled and what is not

The `seed-niit` command creates only facts supplied in the project brief:

| Field | Value | Source |
|-------|-------|--------|
| Organisation name | NASTP Institute of Information Technology | Project brief |
| Short name | NIIT | Project brief |
| Website | `https://niit.edu.pk` | Project owner's domain; editable |
| Time zone | `Asia/Karachi` | Assumed from location; editable |
| Preferred language | `en` | Assumed; editable |

Everything else starts empty. The platform does not invent institutional facts,
programmes, fees, dates, eligibility criteria, rankings or statistics. An authorised
user must enter them, ideally with a source link.

## 2. Organisation settings

| Setting | Purpose |
|---------|---------|
| Name, logo URL, website domain | Identity and report branding |
| Time zone, preferred language | Dates in reports; language of AI drafts |
| Brand tone | Short description of voice used for AI drafts |
| Approved terminology | Preferred terms and terms to avoid, for example preferred programme names |
| AI provider and model | `none` (the NIIT default) or `ollama`. Leave the model empty to use the server's `OLLAMA_DEFAULT_MODEL`. AI also needs the server operator to set `AI_PROVIDER=ollama` |
| Crawl limits | Organisation-wide caps that project settings cannot exceed |
| Report branding | Primary colour (hex, for example the NIIT brand colour) and footer text such as "Internal: for NIIT management". The logo comes from the organisation's logo URL (HTTPS, PNG, JPEG, GIF or WebP) |
| Notification preferences | Channels and events (later phase) |

## 3. Project settings

| Setting | Default | Notes |
|---------|---------|-------|
| Max pages | 100 | Per crawl |
| Max depth | 5 | Link hops from the root URL |
| Concurrency | 2 | Parallel requests |
| Request timeout | 15 s | Per request |
| Delay between requests | 1000 ms | Per host |
| User agent | `NIIT-SEO-Agent/<version> (+contact URL)` | Identify the crawler honestly |
| Respect robots.txt | true | Cannot be disabled for sites the organisation does not own |
| Render JavaScript | false | Enable only for pages that need it |
| Allowed extra hosts | empty | For example a separate admissions portal, if owned by NIIT. The `www.` and bare names of the project's host are always included |
| Excluded paths | empty | Glob patterns, for example `/wp-admin/*` |
| Important pages | empty | URLs that raise issue priority |
| Page groups | empty | Named groups of URL patterns |
| Content types | see below | Used to classify pages and tailor recommendations |
| Institutional profile | empty | Description, contacts, approved sources |
| Editorial approval required | true | All drafts need human approval |
| Analysis thresholds | see below | Limits the SEO rules use, for example title length and thin-content word count |
| Score weights | technical 30, on-page 30, content 20, internal linking 10, structured data 10 | Must total 100 |

Analysis thresholds (defaults): title 30 to 60 characters, meta description 70 to 160
characters, thin content below 200 words, slow response from 1000 ms and very slow from
3000 ms, at most 150 links per page, at least 3 internal links to each important page,
URLs up to 115 characters, important pages within 3 clicks of the home page. These are
generic starting points; adjust them to NIIT's own editorial standards.

## 4. Content types

Content types are configurable records, not code. Suggested starting set for NIIT,
created empty so an authorised user can attach URL patterns:

| Key | Label |
|-----|-------|
| about | About NIIT |
| programmes | Academic programmes |
| admissions | Admissions |
| faculty | Faculty |
| research | Research |
| news_events | News and events |
| training | Training courses |
| student_resources | Student resources |
| contact | Contact information |

Each content type holds a label, URL patterns, optional expected sections (for example
"eligibility" and "how to apply" for admissions) and optional recommended schema.org
types. Missing expected sections are reported as editorial suggestions, never as
definite errors. Missing recommended schema types are reported as optional
enhancements.

The seed suggests these schema types, which authorised users can change: About NIIT →
EducationalOrganization, Academic programmes → Course, Training courses → Course,
Faculty → Person, News and events → Event. Content types only take effect once URL
patterns matching the real NIIT site are added.

## 5. Protected content

The agent must not propose changes to official claims, dates, eligibility criteria,
fees or admission requirements unless the change is backed by a verified source
recorded in the institutional profile and approved by a human reviewer. Drafts that
touch these areas are flagged for mandatory review.

How this works since Phase 4:

- The AI is told never to state or change official facts. Where content needs one, it
  writes `[verify: what is needed]` instead of a value.
- Any draft that adds, changes or removes a money amount, percentage, date, year or
  grade, or mentions fees, tuition, eligibility, deadlines, merit, scholarships,
  refunds or accreditation, is marked **protected**. The reasons are shown to the reviewer.
- A protected draft can only be approved with a verified source reference, such as an
  approved notice, document or page. The reference is stored in the approval trail.
- Nobody can approve their own work: the author or submitter of a version needs a
  second reviewer (owner, admin or SEO manager).
- Approved drafts are never published by the platform. The web team makes the change
  in the CMS and records it as published; the original text is kept for rollback.

## 5a. AI settings for NIIT

| Setting | Where | Recommended value |
|---------|-------|-------------------|
| Platform AI switch | Server `.env`: `AI_PROVIDER` | `ollama` once Ollama is installed; `none` otherwise |
| Ollama address | Server `.env`: `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` (only operators can change it) |
| Default model | Server `.env`: `OLLAMA_DEFAULT_MODEL` | A model the server can run, for example `llama3.1` (8B) on a machine with 16 GB RAM |
| Organisation AI | Settings, AI provider | Off until the owner has checked the output quality on NIIT pages |
| Brand tone and approved terminology | Settings | Enter NIIT's preferred names (for example the official programme names) so drafts use them and reviewers see warnings when they do not |

AI output depends on the model. Validate it on NIIT pages before relying on it; see
the Phase 4 report in `docs/IMPLEMENTATION_PLAN.md`.

## 5b. Reports and scheduled crawls for NIIT

- Generate reports from **Reports** after each analysed crawl. Each report covers the
  latest analysed crawl and does not change afterwards, so it can be shared as a record.
- Leave **Include AI summary** off for reports that go outside the web team until the
  AI output has been reviewed on NIIT pages (see the Phase 4 report).
- Scheduling is off. When the owner wants it, a weekly crawl at a quiet hour (for
  example 02:00 Asia/Karachi) is a sensible start. The server operator must also set
  `SCHEDULER_ENABLED=true`, and the NIIT web host should be told crawls will happen.
- PDF export needs Chromium on the server: `uv run playwright install chromium` in the
  backend folder.

## 5c. Plan, retention, integrations and branding for NIIT

- **Plan.** NIIT uses the default `internal` plan, which has no limits. A platform
  administrator can assign another plan under Administration; do not assign the example
  `starter` or `professional` plans to NIIT.
- **Data retention.** Off. Keep it off until the owner decides how much crawl history to
  keep. If disk space becomes a concern, keeping page data for the newest 10 crawls and
  reports for 365 days is a reasonable start. Only an owner can change it, and every run
  is audit-logged.
- **Integrations.** None recorded. A Search Console, Analytics, WordPress, email or
  webhook record can be saved for later, but the platform does not connect to any of
  them. Connecting one, and any paid service, needs the owner's authorisation. Storing a
  credential needs `INTEGRATIONS_ENCRYPTION_KEYS` on the server.
- **Report branding.** Colour, footer, logo URL, display name and cover note are empty
  until an authorised user enters NIIT's official values. Nothing is pre-filled.
- **Approved sources.** Enter NIIT's official pages (for example the admissions notices
  page) under the project's institutional profile. A reviewer approving a draft that
  changes fees, dates or eligibility must cite a page on one of these sources, or an
  official document by name and reference.
- **Accounts.** Owners and administrators can create accounts for new staff. Only a
  platform administrator can add a person who already has an account.

## 6. Separation from future tenants

NIIT data lives in its own organisation. Commercial tenants get their own
organisations with independent settings. No NIIT value is used as a fallback for
another tenant.

## Google Search Console

NIIT's sites can be connected with one domain property, `sc-domain:niit.edu.pk`, which
covers the main site and every portal subdomain. Figures are then shown per project by
host. Follow `docs/SEARCH_CONSOLE.md`; the property must already be verified in Search
Console by whoever manages NIIT's DNS or website.
