import subprocess
import os
import time
from config import Config

# ==================== 核心配置 ====================
RECORDING_FILE = "recording.wav"                 # 完整录音文件

# ==================== 全局变量 ====================
recording_process = None  # FFmpeg完整录制进程
is_recording = False      # 是否正在录制


def get_room_directory(room_id):
    """获取指定会议室的存储目录（确保目录存在）"""
    room_dir = os.path.join(Config.BASE_AUDIO_DIR, room_id)
    if not os.path.exists(room_dir):
        os.makedirs(room_dir)
    return room_dir


def start_recording(room_id, rtsp_url):
    """
    开始录制完整的RTSP音频
    :param room_id: 会议室ID（用于区分存储目录）
    :param rtsp_url: RTSP流地址
    :return: 录制是否成功启动
    """
    global recording_process, is_recording
    
    # 获取录音文件存储路径
    room_dir = get_room_directory(room_id)
    recording_path = os.path.join(room_dir, RECORDING_FILE)
    
    # FFmpeg命令：仅录制音频
    ffmpeg_cmd = [
        "ffmpeg",
        "-rtsp_transport", "tcp",          # 强制TCP协议，避免丢包
        "-i", rtsp_url,                    # RTSP流地址
        "-vn",                             # 禁用视频
        "-c:a", "pcm_s16le",               # 音频编码（16bit PCM，音质无损）
        "-ar", "16000",                    # 16k采样率
        "-ac", "1",                        # 单声道
        "-y",                              # 覆盖已有文件
        recording_path                     # 完整录音文件路径
    ]

    try:
        # 启动FFmpeg录制进程
        recording_process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.DEVNULL,     # 屏蔽FFmpeg输出
            stderr=subprocess.DEVNULL,
        )
        is_recording = True
        print(f"📹 完整录音已开始：{recording_path}")
        return True
    except Exception as e:
        print(f"❌ 启动完整录音失败：{e}")
        return False


def stop_recording():
    """
    停止完整录音（安全终止FFmpeg进程）
    :return: 停止是否成功
    """
    global recording_process, is_recording
    
    if not is_recording or not recording_process:
        print("❌ 录音未启动，无需停止")
        return False
    
    try:
        # 终止FFmpeg进程（安全停止录制）
        recording_process.terminate()
        # 等待进程退出，确保文件写入完成
        recording_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        # 超时则强制杀死进程
        recording_process.kill()
        print("⚠️ 录音进程超时，已强制终止")
    except Exception as e:
        print(f"⚠️ 停止录音时出错：{e}")
    
    # 重置状态
    recording_process = None
    is_recording = False
    print("📹 完整录音已停止")
    return True


def get_recording_path(room_id):
    """
    获取录音文件路径
    :param room_id: 会议室ID
    :return: 录音文件路径
    """
    room_dir = get_room_directory(room_id)
    recording_path = os.path.join(room_dir, RECORDING_FILE)
    if os.path.exists(recording_path):
        return recording_path
    return ""
