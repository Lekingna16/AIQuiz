import requests
import json

# Lấy token từ file môi trường test hoặc giả lập (ở đây ta sẽ lấy một token giả, mong đợi trả về 401)
# Hoặc tốt hơn, gọi endpoint với token sai để xem nó trả về gì
res = requests.get("http://localhost:8000/api/quizzes/attempts/me", headers={"Authorization": "Bearer fake_token"})
print("Status:", res.status_code)
print("Response:", res.text)
