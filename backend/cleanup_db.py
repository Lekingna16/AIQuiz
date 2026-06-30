import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import get_settings
from app.services.ai_service import DeepSeekService
from bson import ObjectId

async def main():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.MONGODB_DB_NAME]
    
    ai_service = DeepSeekService(api_key=settings.DEEPSEEK_API_KEY)
    
    print("Fetching quizzes from DB...")
    quizzes = await db.quizzes.find({}).to_list(None)
    print(f"Found {len(quizzes)} quizzes.")
    
    for quiz in quizzes:
        doc_id = quiz.get("document_id")
        quiz_id = str(quiz.get("_id"))
        
        if not doc_id:
            print(f"Quiz {quiz_id} has no document_id.")
            continue
            
        doc = await db.documents.find_one({"_id": ObjectId(doc_id)})
        if not doc:
            print(f"Quiz {quiz_id} doc {doc_id} not found.")
            continue
            
        text = doc.get("extracted_text", "")
        if not text:
            print(f"Quiz {quiz_id} doc {doc_id} has no extracted_text.")
            continue
            
        if not quiz.get("subject") or not quiz.get("school") or not quiz.get("exam_type") or not quiz.get("chapter"):
            print(f"Extracting metadata for quiz ID: {quiz_id}...")
            try:
                metadata = await ai_service.extract_metadata(text[:3000])
            except Exception as e:
                print(f"Error extracting metadata for {quiz_id}: {e}")
                continue
            
            update_data = {}
            if metadata.get("subject"): update_data["subject"] = metadata["subject"]
            if metadata.get("chapter"): update_data["chapter"] = metadata["chapter"]
            if metadata.get("exam_type"): update_data["exam_type"] = metadata["exam_type"]
            if metadata.get("school"): update_data["school"] = metadata["school"]
            
            # Đảm bảo bài luôn là public
            if not quiz.get("is_public"):
                update_data["is_public"] = True
                
            if update_data:
                print(f"   -> Updating quiz {quiz_id} keys: {list(update_data.keys())}")
                await db.quizzes.update_one({"_id": quiz["_id"]}, {"$set": update_data})
            else:
                print("   -> AI couldn't find any metadata.")
        else:
            # Cũng nên force update_data["is_public"] = True nếu chưa public
            if not quiz.get("is_public"):
                await db.quizzes.update_one({"_id": quiz["_id"]}, {"$set": {"is_public": True}})
                print(f"Quiz {quiz_id} set to public.")
            print(f"Quiz {quiz_id} already has metadata.")
            
    print("Cleanup completed!")

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.run(main())
