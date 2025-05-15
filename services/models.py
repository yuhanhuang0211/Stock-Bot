import requests
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

url = f"https://generativelanguage.googleapis.com/v1/models?key={API_KEY}"
response = requests.get(url)

print("狀態碼：", response.status_code)
print("回應：")
print(response.json())
