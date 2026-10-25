"""MongoDB persistence functions for the imported education catalogue."""

from __future__ import annotations

from typing import Any


async def list_major_catalog_records(db: Any) -> list[dict[str, object]]:
    """Return imported major records, or an empty list when MongoDB is unavailable."""
    if db is None or not hasattr(db, "education_catalog"):
        return []

    try:
        return await db.education_catalog.find({"kind": "major"}).to_list(length=None)
    except Exception:
        return []


async def has_major_catalog_record(db: Any, major: str) -> bool:
    """Return whether an imported catalogue contains the requested major."""
    if db is None or not hasattr(db, "education_catalog"):
        return False

    try:
        return await db.education_catalog.find_one(
            {"kind": "major", "name": major},
            {"_id": 1},
        ) is not None
    except Exception:
        return False
