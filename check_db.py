from utils.db import query_list
import json

print("=" * 50)
print("查询数据库中 E006 相关的所有会议")
print("=" * 50)

# 查询所有会议
all_meetings = query_list("SELECT * FROM meeting ORDER BY id")
print(f"\n数据库总共有 {len(all_meetings)} 个会议:")
for m in all_meetings:
    participants = json.loads(m['participant_nos']) if m['participant_nos'] else []
    is_e006 = m['organizer_no'] == 'E006' or 'E006' in participants
    marker = " <-- E006" if is_e006 else ""
    print(f"  ID:{m['id']} Title:{m['title']} Status:{m['status']} Organizer:{m['organizer_no']}{marker}")

print("\n" + "=" * 50)
print("查询 E006 组织的会议")
print("=" * 50)
org_meetings = query_list("SELECT * FROM meeting WHERE organizer_no = %s", ('E006',))
for m in org_meetings:
    print(f"  ID:{m['id']} Status:{m['status']} Title:{m['title']}")

print("\n" + "=" * 50)
print("查询 participant_nos 包含 E006 的会议")
print("=" * 50)
part_sql = "SELECT * FROM meeting WHERE JSON_CONTAINS(participant_nos, %s)"
part_meetings = query_list(part_sql, (json.dumps('E006'),))
for m in part_meetings:
    print(f"  ID:{m['id']} Status:{m['status']} Title:{m['title']}")
