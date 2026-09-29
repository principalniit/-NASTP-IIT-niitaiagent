"""robots.txt parsing and matching following RFC 9309.

Python's urllib.robotparser does not support the `*` and `$` wildcards that most sites
use, so this small parser implements the standard directly:

- Groups are selected by matching the crawler's product token case-insensitively; groups
  for the same agent are merged; `*` is the fallback.
- The longest matching rule wins; on a tie, Allow wins.
- `/robots.txt` itself is always allowed.
"""

import contextlib
import re
from dataclasses import dataclass, field

MAX_ROBOTS_BYTES = 512 * 1024
MAX_CRAWL_DELAY_SECONDS = 30.0


@dataclass
class Rule:
    allow: bool
    pattern: str
    regex: re.Pattern[str]


@dataclass
class Group:
    agents: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
    crawl_delay: float | None = None


def _compile(pattern: str) -> re.Pattern[str]:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in body)
    return re.compile(regex + ("$" if anchored else ""))


def product_token(user_agent: str) -> str:
    """'NIIT-SEO-Agent/0.1 (+https://x)' -> 'niit-seo-agent'."""
    token = user_agent.strip().split("/", 1)[0].split(" ", 1)[0]
    return token.lower()


class RobotsTxt:
    def __init__(self, groups: list[Group], sitemaps: list[str]) -> None:
        self.groups = groups
        self.sitemaps = sitemaps

    @classmethod
    def parse(cls, content: str) -> "RobotsTxt":
        groups: list[Group] = []
        sitemaps: list[str] = []
        current: Group | None = None
        last_was_agent = False
        for raw_line in content[:MAX_ROBOTS_BYTES].splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.lower()
            if key == "sitemap":
                if value:
                    sitemaps.append(value)
                continue
            if key == "user-agent":
                if current is None or not last_was_agent:
                    current = Group()
                    groups.append(current)
                current.agents.append(value.lower())
                last_was_agent = True
                continue
            last_was_agent = False
            if current is None:
                continue  # rules before any user-agent line are ignored
            if key in ("allow", "disallow"):
                if not value:
                    continue  # an empty Disallow allows everything
                if not value.startswith(("/", "*")):
                    value = "/" + value
                current.rules.append(Rule(key == "allow", value, _compile(value)))
            elif key == "crawl-delay":
                with contextlib.suppress(ValueError):
                    current.crawl_delay = max(0.0, float(value))
        return cls(groups, sitemaps)

    def _groups_for(self, user_agent: str) -> list[Group]:
        token = product_token(user_agent)
        specific = [g for g in self.groups if token in g.agents]
        if specific:
            return specific
        return [g for g in self.groups if "*" in g.agents]

    def can_fetch(self, user_agent: str, path: str) -> bool:
        if path == "/robots.txt":
            return True
        best: Rule | None = None
        for group in self._groups_for(user_agent):
            for rule in group.rules:
                if rule.regex.match(path) and (
                    best is None
                    or len(rule.pattern) > len(best.pattern)
                    or (len(rule.pattern) == len(best.pattern) and rule.allow)
                ):
                    best = rule
        return best is None or best.allow

    def crawl_delay(self, user_agent: str) -> float | None:
        delays = [g.crawl_delay for g in self._groups_for(user_agent) if g.crawl_delay is not None]
        return min(max(delays), MAX_CRAWL_DELAY_SECONDS) if delays else None


@dataclass
class RobotsPolicy:
    """Outcome of fetching robots.txt for one host.

    status: 'found' (parsed), 'not_found' (4xx: everything allowed), or 'unreachable'
    (5xx or network error: everything disallowed, as RFC 9309 requires).
    """

    status: str
    robots: RobotsTxt | None = None

    def can_fetch(self, user_agent: str, path: str) -> bool:
        if self.status == "unreachable":
            return path == "/robots.txt"
        if self.robots is None:
            return True
        return self.robots.can_fetch(user_agent, path)

    def crawl_delay(self, user_agent: str) -> float | None:
        return self.robots.crawl_delay(user_agent) if self.robots else None

    @property
    def sitemaps(self) -> list[str]:
        return self.robots.sitemaps if self.robots else []
