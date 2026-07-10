"""
test asr and minutes only

如果手头还没有可用的RTSP测试源，用这个脚本可以跳过录制这一步，
拿一个.wav文件模拟"音频已就绪"，只测 ASR + 会议纪要。
 
用法：
1. 准备一个包含语音的 .wav 文件（16k采样率、单声道最佳，和audio_service产出的格式一致；
   不是这个格式也没关系，FunASR一般能处理，但建议尽量贴近真实格式）
2. 确认 RabbitMQ、Ollama、ai_api_service.py 已启动
3. python test_asr_minutes_only.py /path/to/your/sample.wav
"""

import sys
import os
import time
import requests
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import Config
import services.audio_service  # 复用 publish_audio_ready，不调用真实录制逻辑

BASE_URL = "http://localhost:5000"
TEST_ROOM_ID = "test_room_asr_only"

TRANSCRIPT_TIMEOUT = 60
MINUTES_TIMEOUT = 180


def check(condition, message):
    status = "✅" if condition else "❌"
    print(f"{status} {message}")
    if not condition:
        sys.exit(1)

def inject_test_audio(sample_wav_path):
    """
    把现成的wav文件复制到room目录下，模拟"录制已完成"，
    然后直接调用 publish_audio_ready 发MQ消息，跳过ffmpeg录制环节
    """
    room_dir = os.path.join(Config.BASE_AUDIO_DIR, "audio", TEST_ROOM_ID)
    os.makedirs(room_dir, exist_ok=True)
 
    target_path = os.path.join(room_dir, f"audio_{TEST_ROOM_ID}.wav")
    shutil.copy(sample_wav_path, target_path)
    print(f"✅ 测试音频已放置：{target_path}")
 
    services.audio_service.publish_audio_ready(TEST_ROOM_ID, target_path)
    print("✅ 已模拟发布音频就绪MQ消息")


def poll_transcript(timeout, interval=3):
    print("\n=== 轮询ASR转录结果 ===")
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{BASE_URL}/api/meeting/{TEST_ROOM_ID}/transcript")
        transcript = resp.json()["data"].get("transcript", [])
        if transcript:
            print(f"✅ 转录完成，共{len(transcript)}条记录：")
            for item in transcript:
                print("    -", item["text"])
            return
        elapsed = int(time.time() - start)
        print(f"  ...等待ASR worker处理中（已等待{elapsed}s）")
        time.sleep(interval)
    check(False, f"{timeout}秒内未获得转录结果，请检查 asr_service worker 控制台日志")


def generate_and_poll_minutes(timeout, interval=5):
    print("\n=== 提交纪要生成任务 ===")
    resp = requests.post(f"{BASE_URL}/api/meeting/{TEST_ROOM_ID}/minutes/generate")
    print("  ", resp.json())
    check(resp.status_code == 200 and resp.json()["code"] == 200, "纪要生成任务提交成功")
 
    print("\n=== 轮询纪要生成状态 ===")
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{BASE_URL}/api/meeting/{TEST_ROOM_ID}/minutes/status")
        status = resp.json()["data"]["status"]
        elapsed = int(time.time() - start)
        print(f"  [{elapsed}s] 状态: {status}")
        if status == "completed":
            return
        if status == "failed":
            check(False, "纪要生成失败，请检查Ollama服务和worker日志")
        time.sleep(interval)
    check(False, f"{timeout}秒内纪要未生成完成")


def show_minutes():
    resp = requests.get(f"{BASE_URL}/api/meeting/{TEST_ROOM_ID}/minutes")
    minutes = resp.json()["data"]["minutes"]
    check(bool(minutes), "成功拿到完整的会议纪要内容")
    print("\n--- 会议纪要预览（前500字）---")
    print(minutes[:500])
    print("...\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: python test_asr_minutes_only.py /path/to/sample.wav")
        sys.exit(1)
 
    sample_wav = sys.argv[1]
    check(os.path.exists(sample_wav), f"测试音频文件存在: {sample_wav}")
 
    inject_test_audio(sample_wav)
    poll_transcript(TRANSCRIPT_TIMEOUT)
    generate_and_poll_minutes(MINUTES_TIMEOUT)
    show_minutes()
 
    print("🎉 ASR + 纪要生成链路测试通过！")