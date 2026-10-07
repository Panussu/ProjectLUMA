# บริการค้นหาแท็ก Danbooru สำหรับระบบ Tag Auto-Complete
"""Danbooru Tag search service for prompt autocomplete."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TAGS_CACHE: list[list[Any]] | None = None


def load_tags() -> list[list[Any]]:
    global TAGS_CACHE
    if TAGS_CACHE is not None:
        return TAGS_CACHE

    json_path = Path(__file__).resolve().parent.parent / "frontend" / "assets" / "danbooru_tags.json"
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                TAGS_CACHE = json.load(f)
                return TAGS_CACHE
        except Exception:
            pass

    TAGS_CACHE = []
    return TAGS_CACHE


def search_tags(query: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """Search tags by prefix or substring, returning formatted tag objects."""
    all_tags = load_tags()
    q = query.strip().lower().replace(" ", "_")

    if not q:
        # Return top tags
        selected = all_tags[:limit]
    else:
        # 1. Prefix matches first
        prefix_matches = []
        substring_matches = []

        for item in all_tags:
            tag_name = item[0]
            aliases = item[3] if len(item) > 3 else ""

            if tag_name.startswith(q):
                prefix_matches.append(item)
                if len(prefix_matches) >= limit:
                    break
            elif q in tag_name or (aliases and q in aliases.lower()):
                substring_matches.append(item)

        selected = (prefix_matches + substring_matches)[:limit]

    return [
        {
            "name": t[0],
            "type": t[1],
            "count": t[2],
            "aliases": t[3] if len(t) > 3 else "",
        }
        for t in selected
    ]
