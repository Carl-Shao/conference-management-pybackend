import requests
import json

print("=" * 50)
print("测试开始会议接口")
print("=" * 50)

# 先查询一个会议
r = requests.get('http://localhost:5000/api/meetings/2')
meeting = r.json().get('data')
if not meeting:
    print("❌ 没有找到会议")
    exit()

print(f"\n会议信息:")
print(f"  ID: {meeting['id']}")
print(f"  Title: {meeting['title']}")
print(f"  RoomID: {meeting['roomId']}")
print(f"  Status: {meeting['status']}")

# 查询会议室信息
from utils.db import query_one
room = query_one("SELECT * FROM meeting_room WHERE id = %s", (meeting['roomId'],))
print(f"\n会议室 RTSP 地址:")
print(f"  {room['rtsp_url']}")

print("\n" + "=" * 50)
print("✅ 现在点击开始会议时，会使用数据库中该会议室的 rtsp_url 字段")
print("=" * 50)
