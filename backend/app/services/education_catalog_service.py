"""Database-backed additions to the built-in education catalogue."""

from __future__ import annotations

from typing import Any

from app.education_catalog import MAJOR_COURSES
from app.repositories.education_catalog_repository import (
    has_major_catalog_record,
    list_major_catalog_records,
)


def _normalise_courses(courses: object) -> list[str]:
    if not isinstance(courses, list):
        return []

    # Preserve the published curriculum order while removing blank/duplicate rows.
    return list(dict.fromkeys(
        course.strip() for course in courses
        if isinstance(course, str) and course.strip()
    ))


async def get_courses_by_major(db: Any = None) -> dict[str, list[str]]:
    """Return built-in suggestions extended or replaced by imported curricula."""
    catalog = {major: list(courses) for major, courses in MAJOR_COURSES.items()}

    # Keep the public filters endpoint available if MongoDB is temporarily down.
    records = await list_major_catalog_records(db)

    for record in records:
        name = record.get("name")
        courses = _normalise_courses(record.get("courses"))
        if isinstance(name, str) and name.strip() and courses:
            catalog[name.strip()] = courses

    return catalog


async def is_known_major(db: Any, major: str) -> bool:
    """Check both the built-in catalogue and imported curriculum records."""
    if major in MAJOR_COURSES:
        return True
    return await has_major_catalog_record(db, major)
