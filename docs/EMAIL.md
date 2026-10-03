# Setting up email

Email is optional. With it, invitations and password-reset links are sent to people
directly. Without it, an administrator shares invitation links by hand and resets
passwords with `app.cli reset-password`.

The platform sends through a mail account you already have, over SMTP. No email service
is bundled, and nothing here costs money.

## Choose an account

Use a dedicated sending account if you can, for example `seo-noreply@niit.edu.pk`, rather
than a person's mailbox. It keeps the password separate and the sender obvious.

| Your email | SMTP_HOST | SMTP_PORT | Password |
|------------|-----------|-----------|----------|
| Google Workspace (for example `@niit.edu.pk` on Google) or Gmail | `smtp.gmail.com` | `587` | An **app password** (below), not the account password |
| Microsoft 365 / Outlook | `smtp.office365.com` | `587` | The account password; the Microsoft 365 administrator must allow "Authenticated SMTP" for the mailbox |
| Your own mail server | ask its administrator | `587` (STARTTLS) or `465` (TLS) | as given |

Gmail and Google Workspace accounts can send about 500 to 2,000 messages a day, far more
than invitations and resets need.

### App password for Google Workspace or Gmail

1. Sign in to the sending account at https://myaccount.google.com/.
2. **Security → 2-Step Verification**: turn it on if it is off. App passwords need it.
3. Open https://myaccount.google.com/apppasswords, give it a name such as "SEO Agent", and
   choose **Create**.
4. Copy the 16-letter password. Google shows it once. Spaces in it do not matter; you can
   leave them out.

If the app passwords page says the setting is not available, the Google Workspace
administrator has turned it off. Ask them to allow it for this account, or to give you the
details of the organisation's SMTP relay instead.

To stop the platform sending, delete the app password on the same page. Nothing else about
the account changes.

## Configure

### On a laptop or server running from source

Add these lines to `backend/.env` (each setting once):

```
PUBLIC_BASE_URL=http://localhost:3000
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_STARTTLS=true
SMTP_USERNAME=seo-noreply@niit.edu.pk
SMTP_PASSWORD=abcdefghijklmnop
SMTP_FROM="NIIT AI SEO Agent <seo-noreply@niit.edu.pk>"
```

- `PUBLIC_BASE_URL` is the address people open the dashboard at. Links in emails point
  there, so it must be reachable by the people you invite. `localhost` only works on the
  same computer.
- `SMTP_FROM` must be the account itself or an address it is allowed to send as.

Restart the API after changing `.env`.

### In the container install

Add the same lines to `deploy/.env`, then run `docker compose up -d` in `deploy/`. Running
the installer again keeps these lines.

## Test

From `backend/`:

```
uv run python -m app.cli send-test-email --to you@niit.edu.pk
```

In the container install, from `deploy/`:

```
docker compose exec api python -m app.cli send-test-email --to you@niit.edu.pk
```

It sends one message and says what to check if that fails. The password is never shown.

| Message | Fix |
|---------|-----|
| Email is off | `SMTP_HOST` or `SMTP_FROM` is empty, or the API was not restarted |
| The mail server refused the username or password | For Google, use an app password; check `SMTP_USERNAME` is the full address |
| The server refused the sender | Set `SMTP_FROM` to the account's own address |
| The secure connection failed | Use port 587 with `SMTP_STARTTLS=true`, or 465 |
| Could not reach the mail server | Check the host and port; some networks block outgoing mail ports |

When the test works, invite someone from **Administration → Invitations**. The result says
"Invitation emailed to …". The link is also shown once, in case the email goes astray.

## Security

- The password lives only in `.env`, which git ignores. Never put it in source code or a
  ticket.
- The connection is encrypted (STARTTLS on 587, TLS on 465).
- Invitation and reset links are single-use and expire (`INVITATION_TTL_DAYS`,
  `PASSWORD_RESET_TTL_MINUTES`). The forgot-password page answers the same whether or not
  an account exists.
- Send failures are logged without the server's reply or any credential, and never stop
  the request that triggered them.
