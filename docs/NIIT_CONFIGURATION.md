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
| AI provider and model | `none` or `ollama` in Phase 1 to 5 |
| Crawl limits | Organisation-wide caps that project settings cannot exceed |
| Report branding | Colours, footer text, logo placement (Phase 5) |
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
| Allowed extra hosts | empty | For example a separate admissions portal, if owned by NIIT |
| Excluded paths | empty | Glob patterns, for example `/wp-admin/*` |
| Important pages | empty | URLs that raise issue priority |
| Page groups | empty | Named groups of URL patterns |
| Content types | see below | Used to classify pages and tailor recommendations |
| Institutional profile | empty | Description, contacts, approved sources |
| Editorial approval required | true | All drafts need human approval |

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

Each content type holds a label, URL patterns, and optional expected sections (for
example "eligibility" and "how to apply" for admissions). Missing expected sections
are reported as editorial suggestions, never as definite errors.

## 5. Protected content

The agent must not propose changes to official claims, dates, eligibility criteria,
fees or admission requirements unless the change is backed by a verified source
recorded in the institutional profile and approved by a human reviewer. Drafts that
touch these areas are flagged for mandatory review.

## 6. Separation from future tenants

NIIT data lives in its own organisation. Commercial tenants get their own
organisations with independent settings. No NIIT value is used as a fallback for
another tenant.
