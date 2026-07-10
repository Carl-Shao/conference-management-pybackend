"""
端到端验证：
audio_service -> RabbitMQ -> asr_service -> minutes_service -> ai_api_service
是否跑通。
 
用法：
1. 确认以下服务都已经在本机启动：
   - RabbitMQ (localhost:5672)
   - Ollama (localhost:11434，且已 ollama run qwen2.5:7b 过)
   - python ai_api_service.py （监听 localhost:5001）
2. 准备一个测试用的RTSP流地址（见下方TEST_RTSP_URL的说明）
3. python test_pipeline.py
 
如果你手头还没有真实摄像头/RTSP源，可以用本地视频文件模拟一个RTSP流：
  a. 安装 mediamtx (原 rtsp-simple-server)，直接跑默认配置即可起一个RTSP服务器
  b. 另起一个终端循环推流：
     ffmpeg -stream_loop -1 -re -i sample.mp4 -c copy -rtsp_transport tcp -f rtsp rtsp://127.0.0.1:8554/live
  c. 把下面 TEST_RTSP_URL 改成 rtsp://localhost:8554/test
sample.mp4 随便找一个几十秒、有人声说话的视频/录音转视频文件即可，
音频部分需要有实际语音内容，纯静音测不出ASR效果。
"""

import requests
import time
import sys
 
BASE_URL = "http://localhost:5001"
TEST_ROOM_ID = "test_room_001"
TEST_RTSP_URL = "rtsp://localhost:8554/test"  # 按需替换成你的测试流地址
 
RECORD_SECONDS = 15          # 录制多长时间做测试（够说几句话就行）
TRANSCRIPT_TIMEOUT = 60      # 等ASR处理完的超时时间
MINUTES_TIMEOUT = 180        # 等纪要生成完的超时时间（本地Ollama可能较慢）
 
 
def check(condition, message):
    status = "✅" if condition else "❌"
    print(f"{status} {message}")
    if not condition:
        print("\n测试在此中断，请根据上面的失败信息和对应服务的控制台日志排查。")
        sys.exit(1)
 
 
def step1_health_check():
    print("\n=== Step 1: 健康检查 ===")
    resp = requests.get(f"{BASE_URL}/api/health")
    check(resp.status_code == 200, "健康检查接口可访问")
    data = resp.json()["data"]
    print("  ", data)
    check(data["asrWorkerCount"] > 0, f"ASR worker已启动：{data['asrWorkerCount']}个")
    check(data["minutesWorkerCount"] > 0, f"纪要生成worker已启动：{data['minutesWorkerCount']}个")
 
 
def step2_start_recording():
    print("\n=== Step 2: 开始会议录制 ===")
    resp = requests.post(f"{BASE_URL}/api/meeting/start", json={
        "roomId": TEST_ROOM_ID,
        "rtspUrl": TEST_RTSP_URL
    })
    print("  ", resp.json())
    check(resp.status_code == 200 and resp.json()["code"] == 200, "录制启动成功")
 
 
def step3_record_for_a_while(seconds):
    print(f"\n=== Step 3: 录制{seconds}秒（模拟开会中）===")
    time.sleep(seconds)
 
 
def step4_stop_recording():
    print("\n=== Step 4: 停止会议录制 ===")
    resp = requests.post(f"{BASE_URL}/api/meeting/stop", json={"roomId": TEST_ROOM_ID})
    print("  ", resp.json())
    check(resp.status_code == 200 and resp.json()["code"] == 200, "录制已停止，MQ消息已发布给ASR")
 
 
def step5_poll_transcript(timeout, interval=3):
    print("\n=== Step 5: 轮询ASR转录结果 ===")
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
 
 
def step6_generate_minutes():
    print("\n=== Step 6: 提交会议纪要生成任务 ===")
    resp = requests.post(f"{BASE_URL}/api/meeting/{TEST_ROOM_ID}/minutes/generate")
    print("  ", resp.json())
    check(resp.status_code == 200 and resp.json()["code"] == 200, "纪要生成任务提交成功")
 
 
def step7_poll_minutes_status(timeout, interval=5):
    print("\n=== Step 7: 轮询纪要生成状态 ===")
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{BASE_URL}/api/meeting/{TEST_ROOM_ID}/minutes/status")
        status = resp.json()["data"]["status"]
        elapsed = int(time.time() - start)
        print(f"  [{elapsed}s] 状态: {status}")
        if status == "completed":
            return
        if status == "failed":
            check(False, "纪要生成失败，请检查Ollama服务是否正常、minutes_service worker日志")
        time.sleep(interval)
    check(False, f"{timeout}秒内纪要未生成完成")
 
 
def step8_get_minutes():
    print("\n=== Step 8: 获取最终会议纪要 ===")
    resp = requests.get(f"{BASE_URL}/api/meeting/{TEST_ROOM_ID}/minutes")
    minutes = resp.json()["data"]["minutes"]
    check(bool(minutes), "成功拿到完整的会议纪要内容")
    print("\n--- 会议纪要预览（前500字）---")
    print(minutes[:500])
    print("...\n")
 
 
if __name__ == "__main__":
    print(f"开始端到端测试，测试会议室: {TEST_ROOM_ID}")
    print(f"测试RTSP地址: {TEST_RTSP_URL}\n")
 
    step1_health_check()
    step2_start_recording()
    step3_record_for_a_while(RECORD_SECONDS)
    step4_stop_recording()
    step5_poll_transcript(TRANSCRIPT_TIMEOUT)
    step6_generate_minutes()
    step7_poll_minutes_status(MINUTES_TIMEOUT)
    step8_get_minutes()
 
    print("🎉 全链路测试通过！接口契约验证完毕，可以开始接入ruoyi了。")