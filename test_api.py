import requests
import json

print("=" * 50)
print("测试 API 返回")
print("=" * 50)

print("\n【GET /api/meetings?userId=E006】")
r = requests.get('http://localhost:5000/api/meetings', params={'userId': 'E006'})
print(f"Status Code: {r.status_code}")
data = r.json()
print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")

print("\n【GET /api/meetings/history?userId=E006】")
r = requests.get('http://localhost:5000/api/meetings/history', params={'userId': 'E006'})
print(f"Status Code: {r.status_code}")
data = r.json()
print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
