# Connecting Google Search Console

The platform imports clicks, impressions, click-through rate and average position from
your own Google Search Console property. It is free, read-only, and uses a service account
in your own Google Cloud project. Nothing is shown until real data has been imported.

## What you need

- A verified Search Console property for the site, for example `sc-domain:niit.edu.pk`
  (a domain property covers every subdomain, so one connection serves all portals).
- A Google account that can create a Google Cloud project. Google Cloud does not charge
  for the Search Console API.

## Steps

1. **Create a Google Cloud project.** Go to https://console.cloud.google.com/, open the
   project list and choose *New project*, for example "niit-seo".
2. **Enable the API.** In *APIs & Services → Library*, search for **Google Search Console
   API** and choose *Enable*.
3. **Create a service account.** In *IAM & Admin → Service accounts*, choose *Create
   service account*, give it a name such as "seo-reader", and finish. It needs no roles.
4. **Create a key.** Open the service account, go to *Keys → Add key → Create new key*,
   choose **JSON** and download the file. Keep it safe: it is a credential.
5. **Give it read access.** In Search Console, open the property, then *Settings → Users
   and permissions → Add user*. Enter the service account's email (it ends in
   `iam.gserviceaccount.com`) and choose **Restricted**.
6. **Save it in the platform.** As an owner or administrator, open **Integrations → Add
   integration**, choose *Google Search Console*, enter the property exactly as Search
   Console shows it (`sc-domain:niit.edu.pk` or `https://www.example.org/`), save, then
   choose the JSON key file and *Save credential*. The server needs
   `INTEGRATIONS_ENCRYPTION_KEYS` set to store it.
7. **Test and import.** Choose *Test connection*, then *Import now*. The worker imports the
   last 90 days (`SEARCH_CONSOLE_DAYS`). Turn the integration **on** to import once a day.
8. **Look at the figures** in **Search Performance**, and on each page's detail. The AI
   assistant uses them when asked about clicks, impressions or positions.

## Click opportunities

Search Performance lists up to ten **click opportunities**: pages on Google's first page
(average position 10 or better) with at least 100 impressions in the period, whose
click-through rate is below this site's own rate for pages at a similar position (top 3,
or 4 to 10). The comparison uses only this site's imported figures, never an industry
benchmark. The largest gap comes first.

Each row shows the page's current title from the latest analysed crawl and its open
title or description issues. *Open page* leads to the page's details, where *Draft title
and description* asks the AI for a draft. The draft is given the Google queries the page
appeared for, so it can use searchers' wording where the page text covers it. Queries
containing digits are left out, so years, fees and figures in a draft come from the page
only. Every draft goes through review and approval; nothing is published automatically.

## Troubleshooting

| What you see | Cause and fix |
|--------------|---------------|
| Search Console says the email was not found when adding the user | Copy the address from the *Email* column of the service account list (not its name or ID). A new account can take a few minutes to be recognised; try again. |
| "The stored secret cannot be decrypted with the configured keys" | The credential was saved under another `INTEGRATIONS_ENCRYPTION_KEYS` value. Keep a single key line in `.env`, restart the API and the worker, then delete the integration and add it again with the key file. |
| *Test connection* reports `siteOwner` or `siteFullUser` | It works, but the account has more access than it needs. Change it to **Restricted** in Search Console; the test then reports `siteRestrictedUser`. |
| The import stays at *Waiting for the worker* | The worker is not running. Start it (`uv run python -m app.worker`). |

## Notes

- Google reports data with a delay of two to three days, and withholds rare queries for
  privacy, so query totals can be lower than page totals.
- Clicks are visits from Google Search only, not all visitors.
- Average position is weighted by impressions; 1 is the top of the results.
- Each import replaces the imported period, so revised figures from Google are picked up.
- To disconnect, remove the credential or delete the integration, and remove the service
  account from the property in Search Console.
