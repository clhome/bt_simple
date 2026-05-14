import requests

url = "https://timor.tech/api/holiday/info/2026-05-09"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

try:
    response = requests.get(url, headers=headers, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Content: {response.text[:200]}...")
except Exception as e:
    print(f"Error: {e}")
