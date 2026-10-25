"""Clear generated quiz content while preserving user accounts.

Run ``python scripts/clear_quiz_data.py --confirm`` from ``backend`` only
when the generated documents, quizzes, questions, and attempts are
intentionally being reset.
"""

import argparse
import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings


COLLECTIONS = ("documents", "quizzes", "questions", "quiz_attempts")


async def clear_quiz_data(confirm: bool) -> None:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    try:
        counts = {
            collection: await db[collection].count_documents({})
            for collection in COLLECTIONS
        }
        print("Quiz data counts:", counts)

        if not confirm:
            print("Dry run only. Re-run with --confirm to delete these records.")
            return

        deleted = {}
        for collection in COLLECTIONS:
            result = await db[collection].delete_many({})
            deleted[collection] = result.deleted_count
        print("Deleted:", deleted)
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", action="store_true")
    arguments = parser.parse_args()
    asyncio.run(clear_quiz_data(confirm=arguments.confirm))
