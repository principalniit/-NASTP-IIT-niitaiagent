"""Provider interfaces.

Every external capability sits behind one of these protocols so it can be swapped for a
commercial provider later without touching the core. Only local, free implementations are
built; see docs/ARCHITECTURE.md section 10 for the phase that delivers each one.
"""

from app.providers.interfaces import (
    AIHealth,
    AIProvider,
    AnalyticsProvider,
    CMSProvider,
    CrawlerProvider,
    KeywordProvider,
    NotificationProvider,
    RankingProvider,
    ReportProvider,
    SearchConsoleProvider,
    SEOAnalysisProvider,
    SERPProvider,
)

__all__ = [
    "AIHealth",
    "AIProvider",
    "AnalyticsProvider",
    "CMSProvider",
    "CrawlerProvider",
    "KeywordProvider",
    "NotificationProvider",
    "RankingProvider",
    "ReportProvider",
    "SEOAnalysisProvider",
    "SERPProvider",
    "SearchConsoleProvider",
]
