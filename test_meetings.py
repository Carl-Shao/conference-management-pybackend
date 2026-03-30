import requests
import json

print("=" * 50)
print("测试孙八 (E006) 的会议")
print("=" * 50)

print("\n【会议列表】")
r = requests.get('http://localhost:5000/api/meetings', params={'userId': 'E006'})
data = r.json()
print(f"返回数量：{len(data.get('data', []))}")
for m in data.get('data', []):
    print(f"  ID:{m['id']} Title:{m['title']} Status:{m['status']}")

print("\n【历史会议】")
r = requests.get('http://localhost:5000/api/meetings/history', params={'userId': 'E006'})
data = r.json()
print(f"返回数量：{len(data.get('data', []))}")
for m in data.get('data', []):
    print(f"  ID:{m['id']} Title:{m['title']} Status:{m['status']}")

print("\n" + "=" * 50)
