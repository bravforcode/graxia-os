"""Decode Thaifxbook's Next.js App Router RSC flight payload.

Thaifxbook server-renders every page as a Next.js RSC flight payload: the
visible data (tables, stats, trade rows) lives inside escaped JSON strings of
``self.__next_f.push([<id>,"..."])`` calls — there is no plain-HTML data and no
public JSON API (verified 2026-08-06: only /api/ad/click and /api/ad/impression
exist, and they carry no page data).

This module extracts and decodes those pushes. The decoded text is a serialized
React element tree; ``parser.py`` applies label-anchored regexes to it (the same
flatten-then-regex strategy the myfxbook collector uses on tag-stripped HTML).
"""

from __future__ import annotations

import json
import re

# Each push is: self.__next_f.push([<id>,"<js-escaped-string>"])
_PUSH_RE = re.compile(r'\[(\d+),("(?:[^"\\]|\\.)*")\]\)', re.S)


def decode_flight_payload(html: str) -> str:
    """Return the concatenated, unescaped text of all RSC pushes in ``html``.

    Raises ValueError if no pushes are found (page is not a Thaifxbook RSC page).
    """
    matches = _PUSH_RE.findall(html)
    if not matches:
        raise ValueError("no self.__next_f.push payloads found in HTML")
    parts = []
    for _, escaped in matches:
        try:
            parts.append(json.loads(escaped))
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise ValueError(f"failed to decode RSC payload: {exc}") from exc
    return "\n".join(parts)
