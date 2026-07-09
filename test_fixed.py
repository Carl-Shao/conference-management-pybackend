import requests
import json

print("=" * 50)
print("测试修复后的 API")
print("=" * 50)

print("\n【GET /api/meetings?userId=E006】- 会议列表")
r = requests.get('http://localhost:5000/api/meetings', params={'userId': 'E006'})
data = r.json()
print(f"返回数量：{len(data.get('data', []))}")
for m in data.get('data', []):
    print(f"  ID:{m['id']} Title:{m['title']} Status:{m['status']}")

print("\n【GET /api/meetings/history?userId=E006】- 历史会议")
r = requests.get('http://localhost:5000/api/meetings/history', params={'userId': 'E006'})
data = r.json()
print(f"返回数量：{len(data.get('data', []))}")
for m in data.get('data', []):
    print(f"  ID:{m['id']} Title:{m['title']} Status:{m['status']}")

print("\n" + "=" * 50)
print("✅ 如果会议列表只显示 scheduled/active，历史会议只显示 completed，则修复成功！")
print("=" * 50)
