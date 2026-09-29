"""The settings snapshot a crawl job runs with."""

from pydantic import BaseModel, Field


class CrawlConfig(BaseModel):
    root_url: str
    allowed_hosts: list[str]
    excluded_paths: list[str] = Field(default_factory=list)
    max_pages: int
    max_depth: int
    concurrency: int
    timeout_seconds: int
    delay_ms: int
    user_agent: str
    render_javascript: bool = False
    extra_ports: list[int] = Field(default_factory=list)
