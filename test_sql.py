from utils.db import query_list
import json

print("测试 SQL 查询 E006 的未完成会议")
sql = """
    SELECT * FROM meeting 
    WHERE (organizer_no = %s OR JSON_CONTAINS(participant_nos, %s))
    AND status IN ('scheduled', 'active')
    ORDER BY meeting_date DESC, start_time DESC
"""
result = query_list(sql, ('E006', json.dumps('E006')))
print(f"查询结果数量：{len(result)}")
for r in result:
    print(f"  ID:{r['id']} Title:{r['title']} Status:{r['status']}")

print("\n测试 SQL 查询 E006 的已完成会议")
sql = """
    SELECT * FROM meeting 
    WHERE (organizer_no = %s OR JSON_CONTAINS(participant_nos, %s))
    AND status = 'completed'
    ORDER BY meeting_date DESC, start_time DESC
"""
result = query_list(sql, ('E006', json.dumps('E006')))
print(f"查询结果数量：{len(result)}")
for r in result:
    print(f"  ID:{r['id']} Title:{r['title']} Status:{r['status']}")
