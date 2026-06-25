"""
Quick test: Thử các model Gemini khác nhau xem model nào còn quota.
"""
import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import google.generativeai as genai
from app.config import get_settings

settings = get_settings()
genai.configure(api_key=settings.GEMINI_API_KEY)

models_to_try = [
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-2.0-flash",
]

for model_name in models_to_try:
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            "Say 'hello' in one word only.",
            generation_config=genai.GenerationConfig(temperature=0),
        )
        print(f"  ✓ {model_name}: OK — {response.text.strip()}")
    except Exception as e:
        err = str(e)[:100]
        print(f"  ✗ {model_name}: {err}")
