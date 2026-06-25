import httpx
import asyncio
import json

async def test_upload():
    url = "http://localhost:8000/api/documents/upload"
    params = {"num_questions": 5, "difficulty": "mixed", "language": "vi"}
    
    print("Testing upload to FastAPI...")
    with open("test_document.txt", "rb") as f:
        files = {"file": ("test_document.txt", f, "text/plain")}
        
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(url, params=params, files=files)
            
            print(f"Status Code: {response.status_code}")
            if response.status_code == 200:
                print("SUCCESS! Quiz Data:")
                print(json.dumps(response.json(), indent=2, ensure_ascii=False))
            else:
                print("FAILED!")
                print(response.text)

if __name__ == "__main__":
    asyncio.run(test_upload())
