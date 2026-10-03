import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.modules.search_data.models import SyncStatus


class SyncOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: SyncStatus
    start_date: date | None
    end_date: date | None
    page_day_rows: int
    query_rows: int
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class ConnectionTest(BaseModel):
    permission_level: str
    service_account_email: str


class Totals(BaseModel):
    clicks: int
    impressions: int
    ctr: float | None
    # Average position weighted by impressions; 1 is the top of Google's results.
    position: float | None


class DayRow(BaseModel):
    day: date
    clicks: int
    impressions: int


class PageRow(BaseModel):
    page: str
    clicks: int
    impressions: int
    ctr: float | None
    position: float | None


class QueryRow(BaseModel):
    query: str
    clicks: int
    impressions: int
    ctr: float | None
    position: float | None


class OpportunityRow(PageRow):
    # top_3 or positions_4_10, and this site's own click-through rate for that band.
    band: Literal["top_3", "positions_4_10"]
    band_ctr: float
    # The page in the latest analysed crawl, when it is there.
    crawl_id: uuid.UUID | None
    page_id: uuid.UUID | None
    title: str | None
    meta_description: str | None
    metadata_issues: int


class PerformanceOut(BaseModel):
    # not_connected: no Search Console key saved; no_data: connected, but nothing imported
    # for this project's host yet; ready: figures below are Google's.
    state: Literal["not_connected", "no_data", "ready"]
    connected: bool
    properties: list[str]
    last_synced_at: datetime | None
    start: date | None = None
    end: date | None = None
    totals: Totals | None = None
    daily: list[DayRow] = []
    top_pages: list[PageRow] = []
    top_queries: list[QueryRow] = []
    opportunities: list[OpportunityRow] = []


class PagePerformanceOut(BaseModel):
    state: Literal["no_data", "ready"]
    start: date | None = None
    end: date | None = None
    totals: Totals | None = None
    top_queries: list[QueryRow] = []
