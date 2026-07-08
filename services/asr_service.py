import subprocess
import os
import time
import threading
import json
import requests
from aip import AipSpeech
from config import Config

# ==================== 全局变量 ====================
asr_threads = {}  # 存储各个会议的ASR线程
asr_status = {}   # 存储各个会议的ASR状态
asr_results = {}  # 存储ASR识别结果，key为meeting_id

def get_room_directory(room_id):
    """获取音频存储目录"""
    dir_path = os.path.join(Config.BASE_AUDIO_DIR, room_id)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    return dir_path

def send_asr_task_http(meeting_id, audio_path):
    """
    通过HTTP发送ASR任务
    :param meeting_id: 会议ID
    :param audio_path: 音频文件路径
    """
    try:
        # 准备请求数据
        payload = {
            'meetingId': meeting_id,
            'audioPath': audio_path
        }

        # 发送HTTP POST请求到ASR任务端点
        response = requests.post(
            f"http://localhost:5001/asr/task",  # 假设服务运行在5001端口
            json=payload,
            headers={'Content-Type': 'application/json'}
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✅ ASR任务HTTP请求成功：会议{meeting_id}, 音频{audio_path}")
            return True, result
        else:
            print(f"❌ ASR任务HTTP请求失败：状态码{response.status_code}")
            return False, response.text

    except Exception as e:
        print(f"❌ 发送ASR任务HTTP请求失败：{e}")
        return False, str(e)

def process_asr_with_baidu(audio_file_path):
    """
    使用百度ASR处理音频文件
    :param audio_file_path: 音频文件路径
    :return: 识别结果文本
    """
    # 初始化百度ASR客户端
    baidu_client = AipSpeech(
        Config.BAIDU_APP_ID,
        Config.BAIDU_API_KEY,
        Config.BAIDU_SECRET_KEY
    )

    # 读取音频文件
    def get_file_content(file_path):
        with open(file_path, 'rb') as fp:
            return fp.read()

    try:
        result = baidu_client.asr(
            get_file_content(audio_file_path),
            'wav',
            16000,
            {'dev_pid': 1537}  # 普通话（含英文）识别
        )

        if result.get("err_no") == 0:
            text = "".join(result.get("result", []))
            print(f"📝 ASR识别结果：{text}")
            return text
        else:
            print(f"❌ ASR识别失败：{result.get('err_msg')}")
            return ""
    except Exception as e:
        print(f"❌ 调用百度ASR异常：{e}")
        return ""

def handle_asr_task(meeting_id, audio_path):
    """
    处理ASR任务 - 执行识别并将结果存储
    :param meeting_id: 会议ID
    :param audio_path: 音频文件路径
    """
    print(f"👂 开始处理ASR任务：会议{meeting_id}, 音频{audio_path}")

    # 执行ASR识别
    result_text = process_asr_with_baidu(audio_path)

    # 存储识别结果
    if meeting_id not in asr_results:
        asr_results[meeting_id] = []

    result_data = {
        'audio_path': audio_path,
        'text': result_text,
        'timestamp': time.time()
    }

    asr_results[meeting_id].append(result_data)

    # 保存到会议目录的转录文件
    room_dir = os.path.join(Config.BASE_AUDIO_DIR, meeting_id)
    if not os.path.exists(room_dir):
        os.makedirs(room_dir)

    transcript_file = os.path.join(room_dir, "transcript.txt")
    with open(transcript_file, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {result_text}\n")

    print(f"✅ ASR任务处理完成：会议{meeting_id}")

def start_asr_service():
    """
    启动ASR服务
    """
    print("🚀 启动ASR服务...")
    print("✅ ASR服务已启动")
    return True

def monitor_audio_ready_events(room_id):
    """
    监听音频就绪事件，当audio_service生成新的音频文件时触发
    :param room_id: 会议ID
    """
    room_dir = os.path.join(Config.BASE_AUDIO_DIR, "audio", room_id)

    processed_files = set()

    def check_new_files():
        nonlocal processed_files

        if not os.path.exists(room_dir):
            return

        # 获取当前目录下所有WAV文件
        try:
            current_files = set(f for f in os.listdir(room_dir) if f.endswith(".wav"))
            # 获取新文件
            new_files = current_files - processed_files

            for audio_file in new_files:
                audio_path = os.path.join(room_dir, audio_file)

                # 触发AudioReady事件 - 发送ASR任务
                print(f"🎧 检测到音频就绪：会议{room_id}, 文件{audio_file}")

                # 通过HTTP发送ASR任务
                success, response = send_asr_task_http(room_id, audio_path)

                if success:
                    # 在后台线程中处理ASR任务
                    asr_thread = threading.Thread(
                        target=handle_asr_task,
                        args=(room_id, audio_path),
                        daemon=True
                    )
                    asr_thread.start()

                    # 存储线程引用
                    if room_id not in asr_threads:
                        asr_threads[room_id] = []
                    asr_threads[room_id].append(asr_thread)

                # 记录已处理的文件
                processed_files.add(audio_file)

        except Exception as e:
            print(f"❌ 监听音频就绪事件异常：{e}")

    # 启动定时检查线程
    def monitor_loop():
        while asr_status.get(room_id, {}).get('monitoring', False):
            check_new_files()
            time.sleep(2)  # 每2秒检查一次

    # 启动监控线程
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()

    # 更新监控状态
    if room_id not in asr_status:
        asr_status[room_id] = {}
    asr_status[room_id]['monitoring'] = True
    asr_status[room_id]['thread'] = monitor_thread

    print(f"🔍 开始监控会议{room_id}的音频就绪事件")

def stop_monitoring_audio_events(room_id):
    """
    停止监听音频就绪事件
    :param room_id: 会议ID
    """
    if room_id in asr_status:
        asr_status[room_id]['monitoring'] = False
        print(f"⏹️ 停止监控会议{room_id}的音频就绪事件")

def get_transcript(room_id):
    """
    获取会议转录文本
    :param room_id: 会议ID
    :return: 转录文本列表
    """
    if room_id in asr_results:
        return asr_results[room_id]
    else:
        # 从文件中读取历史记录
        room_dir = os.path.join(Config.BASE_AUDIO_DIR, room_id)
        transcript_file = os.path.join(room_dir, "transcript.txt")

        if os.path.exists(transcript_file):
            try:
                with open(transcript_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    result_list = []
                    for line in lines:
                        result_list.append({
                            'text': line.strip(),
                            'timestamp': time.time()
                        })
                    return result_list
            except Exception as e:
                print(f"❌ 读取转录文件失败：{e}")

        return []

def stop_asr_service():
    """
    停止ASR服务
    """
    print("🛑 ASR服务已停止")