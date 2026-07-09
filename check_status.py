from utils.db import query_list

print("=" * 50)
print("查询数据库中所有会议的状态")
print("=" * 50)

meetings = query_list("SELECT id, title, status FROM meeting ORDER BY id")
for m in meetings:
    print(f"  ID:{m['id']} Title:{m['title']} Status:{m['status']}")

print("=" * 50)
