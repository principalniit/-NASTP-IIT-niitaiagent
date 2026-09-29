"""Deterministic text helpers: tokens, simhash near-duplicate detection, title cleanup."""

import hashlib
import re
from collections import Counter
from collections.abc import Iterable

_WORD = re.compile(r"\w+", re.UNICODE)
_SEPARATORS = (" | ", " - ", " \u2013 ", " \u2014 ", " :: ", " \u00bb ")


def tokens(text: str | None) -> list[str]:
    return [t.lower() for t in _WORD.findall(text or "")]


def simhash(text: str | None, shingle: int = 3) -> int | None:
    """64-bit simhash over word shingles. Returns None for texts too short to compare."""
    words = tokens(text)
    if len(words) < shingle * 5:
        return None
    vector = [0] * 64
    for i in range(len(words) - shingle + 1):
        digest = hashlib.blake2b(" ".join(words[i : i + shingle]).encode(), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        for bit in range(64):
            vector[bit] += 1 if value >> bit & 1 else -1
    return sum(1 << bit for bit in range(64) if vector[bit] > 0)


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def near_duplicate_pairs(
    hashes: dict[str, int], max_distance: int = 3
) -> list[tuple[str, str, int]]:
    """Pairs within max_distance bits, found with band indexing instead of all pairs.

    With 4 bands of 16 bits, any two hashes differing in at most 3 bits share at least one
    identical band (pigeonhole), so no qualifying pair is missed.
    """
    buckets: dict[tuple[int, int], list[str]] = {}
    for key, value in hashes.items():
        for band in range(4):
            buckets.setdefault((band, value >> (band * 16) & 0xFFFF), []).append(key)
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str, int]] = []
    for members in buckets.values():
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                pair = (a, b) if a < b else (b, a)
                if pair in seen:
                    continue
                seen.add(pair)
                distance = hamming(hashes[a], hashes[b])
                if distance <= max_distance:
                    pairs.append((*pair, distance))
    return pairs


def connected_groups(pairs: Iterable[tuple[str, str]]) -> list[list[str]]:
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in pairs:
        parent[find(a)] = find(b)
    groups: dict[str, list[str]] = {}
    for x in list(parent):
        groups.setdefault(find(x), []).append(x)
    return [sorted(g) for g in groups.values() if len(g) > 1]


def common_title_suffix(titles: Iterable[str | None]) -> str | None:
    """A branding suffix such as ' | Example Institute' shared by at least half the titles."""
    candidates: Counter[str] = Counter()
    count = 0
    for title in titles:
        if not title:
            continue
        count += 1
        for sep in _SEPARATORS:
            if sep in title:
                candidates[sep + title.rsplit(sep, 1)[1]] += 1
    if not candidates or count < 2:
        return None
    suffix, hits = candidates.most_common(1)[0]
    return suffix if hits >= max(2, count / 2) else None


def strip_suffix(title: str | None, suffix: str | None) -> str:
    title = (title or "").strip()
    if suffix and title.endswith(suffix):
        return title[: -len(suffix)].strip()
    return title
