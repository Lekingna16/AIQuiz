import requests
from pymongo import MongoClient
client = MongoClient("mongodb://localhost:27017/")
db = client["aiquiz"]
question = db.questions.find_one()
if question:
    qid = str(question["_id"])
    print("Found question ID:", qid)
    
    # Test POST comment
    res = requests.post(f"http://localhost:8000/api/comments/question/{qid}", json={
        "content": "Đây là bình luận test",
        "guest_name": "Test User"
    })
    print("POST comment:", res.status_code, res.text)
    
    # Test GET comment
    res2 = requests.get(f"http://localhost:8000/api/comments/question/{qid}")
    print("GET comments:", res2.status_code, res2.text)
else:
    print("No questions in DB")
