"""Import a numbered major/course text file into MongoDB.

Usage:
    python scripts/import_curriculum_catalog.py path/to/curricula.txt
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient, UpdateOne

# Make direct execution from ``backend/scripts`` work without requiring callers
# to set PYTHONPATH manually.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings


HEADING = re.compile(r"^(?P<number>\d+)\.\s+(?P<name>.+?)(?:\s+\((?P<code>\d{7})\))?$")
ALIASES = {
    "Răng – Hàm – Mặt": "Răng - Hàm - Mặt",
    "Y đa khoa / Y khoa": "Y khoa",
    "Logistics và Quản lý chuỗi cung ứng": "Logistics và quản lý chuỗi cung ứng",
    "Các học phần đại cương": "Đại cương",
}


def parse_catalog(text: str) -> list[dict[str, object]]:
    sections: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = HEADING.match(line)
        if match:
            if current:
                sections.append(current)
            original_name = match.group("name").strip()
            current = {
                "number": int(match.group("number")),
                "name": ALIASES.get(original_name, original_name),
                "code": match.group("code"),
                "courses": [],
            }
            continue

        if current and line.startswith("- "):
            current["courses"].append(line[2:].strip())

    if current:
        sections.append(current)

    records: list[dict[str, object]] = []
    for section in sections:
        name = str(section["name"])
        # The supplied health-sciences section is explicitly a group rather than
        # a selectable major, so it must not appear as one in the product.
        if name.casefold().startswith("khối ngành"):
            continue
        courses = list(dict.fromkeys(course for course in section["courses"] if course))
        if courses:
            records.append({
                "kind": "major",
                "name": name,
                "code": section["code"],
                "courses": courses,
                "source_section": section["number"],
            })
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Import major/course suggestions into MongoDB.")
    parser.add_argument("source", type=Path, help="UTF-8 text file containing numbered majors and bullet courses")
    args = parser.parse_args()

    text = args.source.read_text(encoding="utf-8-sig")
    records = parse_catalog(text)
    if not records:
        raise SystemExit("No curriculum records found in the source file.")

    settings = get_settings()
    timestamp = datetime.now(timezone.utc)
    operations = [
        UpdateOne(
            {"kind": "major", "name": record["name"]},
            {"$set": {**record, "source_file": args.source.name, "updated_at": timestamp}},
            upsert=True,
        )
        for record in records
    ]

    client = MongoClient(settings.MONGODB_URL, serverSelectionTimeoutMS=5000)
    try:
        collection = client[settings.MONGODB_DB_NAME].education_catalog
        collection.create_index([("kind", 1), ("name", 1)], unique=True)
        result = collection.bulk_write(operations, ordered=False)
    finally:
        client.close()

    course_count = sum(len(record["courses"]) for record in records)
    print(
        f"Imported {len(records)} majors and {course_count} course suggestions "
        f"(matched={result.matched_count}, modified={result.modified_count}, upserted={len(result.upserted_ids)})."
    )


if __name__ == "__main__":
    main()
