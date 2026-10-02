"""Google Search Console through a service account (free, read-only).

The organisation creates a service account in its own Google Cloud project, adds the
account's email as a user of its Search Console property, and stores the JSON key in the
integration's encrypted credential. The server signs a short-lived JWT with that key and
exchanges it for an access token (the OAuth 2.0 JWT bearer flow), then calls the
Search Analytics API.

Outbound requests go only to the two fixed Google endpoints in settings. The key file's
own `token_uri` is ignored, so a tampered key cannot point the server at another address.
Errors are turned into safe messages; Google's response bodies are never shown or logged.
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import quote

import httpx
import jwt

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
PAGE_SIZE = 25_000  # the API's maximum rows per request
TIMEOUT_SECONDS = 30.0

# Replaced in tests with an httpx.MockTransport.
transport: httpx.AsyncBaseTransport | None = None


class SearchConsoleError(Exception):
    """A failure with a message that is safe to show to the organisation's admins."""


@dataclass(frozen=True)
class ServiceAccountKey:
    client_email: str
    private_key: str
    private_key_id: str | None


def parse_key(raw: str) -> ServiceAccountKey:
    """Validate a service account JSON key without contacting Google."""
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise SearchConsoleError("The credential is not a JSON key file.") from exc
    if not isinstance(data, dict) or data.get("type") != "service_account":
        raise SearchConsoleError("The JSON key must be a Google service account key.")
    email, key = data.get("client_email"), data.get("private_key")
    if not isinstance(email, str) or not email.endswith(".gserviceaccount.com"):
        raise SearchConsoleError("The key has no valid service account email.")
    if not isinstance(key, str) or "PRIVATE KEY" not in key:
        raise SearchConsoleError("The key has no private key.")
    key_id = data.get("private_key_id")
    return ServiceAccountKey(email, key, key_id if isinstance(key_id, str) else None)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT_SECONDS, transport=transport, trust_env=False, follow_redirects=False
    )


def _explain(status: int, during: str) -> SearchConsoleError:
    if status in (400, 401) and during == "sign-in":
        return SearchConsoleError(
            "Google rejected the service account key. Create a new key and save it again."
        )
    if status == 403:
        return SearchConsoleError(
            "The service account has no access to this Search Console property. Add its email "
            "as a user of the property in Search Console, then try again."
        )
    if status == 404:
        return SearchConsoleError(
            "Search Console has no property with this address. Use the exact property, for "
            "example sc-domain:example.org or https://www.example.org/."
        )
    if status == 429:
        return SearchConsoleError("Google's daily request quota is used up. Try again later.")
    return SearchConsoleError(f"Search Console could not be reached (HTTP {status}).")


async def access_token(key: ServiceAccountKey) -> str:
    settings = get_settings()
    now = int(time.time())
    claims = {
        "iss": key.client_email,
        "scope": SCOPE,
        "aud": settings.google_token_url,
        "iat": now,
        "exp": now + 3600,
    }
    headers = {"kid": key.private_key_id} if key.private_key_id else None
    try:
        assertion = jwt.encode(claims, key.private_key, algorithm="RS256", headers=headers)
    except (ValueError, TypeError, jwt.PyJWTError) as exc:
        raise SearchConsoleError("The private key in the JSON key file is not valid.") from exc
    try:
        async with _client() as client:
            response = await client.post(
                settings.google_token_url,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
    except httpx.HTTPError as exc:
        raise SearchConsoleError("Google could not be reached to sign in.") from exc
    if response.status_code != 200:
        logger.warning("Google sign-in refused", extra={"status": response.status_code})
        raise _explain(response.status_code, "sign-in")
    token = response.json().get("access_token")
    if not isinstance(token, str):
        raise SearchConsoleError("Google returned no access token.")
    return token


def _site(property_url: str) -> str:
    return f"{get_settings().google_search_console_url}/sites/{quote(property_url, safe='')}"


async def check_property(key: ServiceAccountKey, property_url: str) -> str:
    """The service account's permission level on the property, or a SearchConsoleError."""
    token = await access_token(key)
    try:
        async with _client() as client:
            response = await client.get(
                _site(property_url), headers={"Authorization": f"Bearer {token}"}
            )
    except httpx.HTTPError as exc:
        raise SearchConsoleError("Search Console could not be reached.") from exc
    if response.status_code != 200:
        raise _explain(response.status_code, "property")
    level = response.json().get("permissionLevel", "")
    if level == "siteUnverifiedUser":
        raise SearchConsoleError(
            "The service account has no access to this Search Console property. Add its email "
            "as a user of the property in Search Console, then try again."
        )
    return str(level)


async def query(
    key: ServiceAccountKey,
    property_url: str,
    start: date,
    end: date,
    dimensions: list[str],
    max_rows: int,
) -> list[dict[str, Any]]:
    """Search Analytics rows for the period, paged up to `max_rows`."""
    token = await access_token(key)
    rows: list[dict[str, Any]] = []
    async with _client() as client:
        while len(rows) < max_rows:
            limit = min(PAGE_SIZE, max_rows - len(rows))
            body = {
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "dimensions": dimensions,
                "rowLimit": limit,
                "startRow": len(rows),
            }
            try:
                response = await client.post(
                    f"{_site(property_url)}/searchAnalytics/query",
                    json=body,
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError as exc:
                raise SearchConsoleError("Search Console could not be reached.") from exc
            if response.status_code != 200:
                raise _explain(response.status_code, "query")
            batch = response.json().get("rows") or []
            rows.extend(batch)
            if len(batch) < limit:
                break
    return rows
