import requests

res = requests.post("http://localhost:8000/api/auth/google", json={"credential": "abc"})
print("Status:", res.status_code)
print("Response:", res.text)
