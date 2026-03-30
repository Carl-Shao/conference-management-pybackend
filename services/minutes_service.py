import requests
import json
import os
from config import Config

# ==================== 配置 ====================
OLLAMA_MODEL = "deepseek-r1:7b"
OLLAMA_API_URL = "http://localhost:11434/api/chat"
MINUTES_FILE = "meeting_minutes.md"

# ==================== 核心函数 ====================

def generate_meeting_minutes(transcript, room_dir):
    """
    调用本地Ollama模型，将完整转录稿生成结构化会议纪要
    """
    if not transcript:
        print("❌ 无转录文本，无法生成纪要")
        return ""

    prompt = f"""
请你作为专业的会议纪要助手，根据以下会议音频转录文本，生成一份规范的结构化会议纪要。
输出格式要求（严格按以下结构，使用Markdown）：
# 会议纪要
## 1. 会议主题
（自动从文本中提取核心主题，简洁明了）

## 2. 核心讨论要点
- 要点1（具体、不笼统）
- 要点2
- 要点3（最多5条）

## 3. 待办事项
- 事项1：内容（负责人/完成时间，如有则标注）
- 事项2：内容（无则标注"无"）

## 4. 会议总结
（总结会议达成的共识、决策或下一步行动方向）

会议转录文本：
{transcript}
"""

    try:
        response = requests.post(
            OLLAMA_API_URL,
            json={
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "temperature": 0.3,
                "top_p": 0.8,
            },
            timeout=60,
        )

        if response.status_code == 200:
            response_json = response.json()
            minutes = response_json["message"]["content"]
            # 保存会议纪要文件
            minutes_path = os.path.join(room_dir, MINUTES_FILE)
            with open(minutes_path, "w", encoding="utf-8") as f:
                f.write(minutes)
            print(f"\n✅ 会议纪要已生成：{minutes_path}")
            print("\n=== 会议纪要预览 ===")
            print(minutes)
            return minutes
        else:
            print(f"❌ 生成纪要失败：HTTP状态码 {response.status_code}，响应内容：{response.text}")
            return ""
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到本地Ollama服务！请确认：")
        print("  1. Ollama已安装并启动（命令：ollama serve）")
        print(f"  2. 本地模型 {OLLAMA_MODEL} 已下载（命令：ollama run {OLLAMA_MODEL}")
        return ""
    except Exception as e:
        print(f"❌ 调用本地模型失败：{e}")
        return ""

def get_meeting_minutes(room_id):
    """
    获取会议纪要
    """
    room_dir = os.path.join(Config.BASE_AUDIO_DIR, room_id)
    minutes_path = os.path.join(room_dir, MINUTES_FILE)
    
    if os.path.exists(minutes_path):
        with open(minutes_path, "r", encoding="utf-8") as f:
            minutes = f.read()
        return minutes
    return ""

def generate_minutes_from_transcript_file(room_id):
    """
    从转录文件生成会议纪要
    """
    room_dir = os.path.join(Config.BASE_AUDIO_DIR, room_id)
    transcript_path = os.path.join(room_dir, "transcript.txt")
    
    if not os.path.exists(transcript_path):
        print(f"❌ 转录文件不存在：{transcript_path}")
        return ""
    
    # 读取转录文本
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = f.read()
    
    # 生成会议纪要
    return generate_meeting_minutes(transcript, room_dir)