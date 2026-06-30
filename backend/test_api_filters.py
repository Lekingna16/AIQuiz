import requests

res = requests.get("http://localhost:8000/api/quizzes/filters")
print("Status:", res.status_code)
print("Response:", res.text)
