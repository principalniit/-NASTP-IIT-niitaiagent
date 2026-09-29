"""Reusable Pydantic field validators."""

from typing import Annotated
from zoneinfo import available_timezones

from pydantic import AfterValidator, Field, StringConstraints

from app.core.urls import UnsafeURLError, normalise_site_url

_TIMEZONES = frozenset(available_timezones())


def _timezone(value: str) -> str:
    if value not in _TIMEZONES:
        raise ValueError("Unknown IANA time zone")
    return value


def _hostname(value: str) -> str:
    try:
        _, host = normalise_site_url(value)
    except UnsafeURLError as exc:
        raise ValueError(str(exc)) from exc
    return host


def _https_url(value: str) -> str:
    try:
        url, _ = normalise_site_url(value)
    except UnsafeURLError as exc:
        raise ValueError(str(exc)) from exc
    if not url.startswith("https://"):
        raise ValueError("Must be an https URL")
    return url


def _site_url(value: str) -> str:
    try:
        url, _ = normalise_site_url(value)
    except UnsafeURLError as exc:
        raise ValueError(str(exc)) from exc
    return url


TimeZone = Annotated[str, AfterValidator(_timezone)]
Hostname = Annotated[str, Field(max_length=253), AfterValidator(_hostname)]
HttpsURL = Annotated[str, Field(max_length=2048), AfterValidator(_https_url)]
SiteURL = Annotated[str, Field(max_length=2048), AfterValidator(_site_url)]
LanguageCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}(-[A-Z]{2})?$")]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
HexColour = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$")]
