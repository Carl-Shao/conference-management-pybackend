import subprocess
import os
import time
from config import Config

# ==================== 全局变量 ====================
video_recording_process = None  # FFmpeg视频录制进程
is_video_recording = False      # 是否正在录制视频

def get_room_directory(room_id):
    """获取指定会议室的存储目录（确保目录存在）"""
    # 使用BASE_AUDIO_DIR作为基础目录，创建video子目录
    base_dir = Config.BASE_AUDIO_DIR
    room_dir = os.path.join(base_dir, "video", room_id)  # 在音频目录下创建video子目录
    if not os.path.exists(room_dir):
        os.makedirs(room_dir)
    return room_dir

def start_video_recording(room_id, rtsp_url):
    """
    开始录制RTSP流到MP4文件，包含视频和音频
    :param room_id: 会议室ID（用于区分存储目录）
    :param rtsp_url: RTSP流地址
    :return: (录制是否成功启动, 录制文件路径)
    """
    global video_recording_process, is_video_recording

    # 获取录制文件存储路径
    room_dir = get_room_directory(room_id)
    output_filename = f"meeting_{room_id}.mp4"
    recording_path = os.path.join(room_dir, output_filename)

    # FFmpeg命令：录制RTSP流到MP4文件，音频编码为AAC，视频编码为H.264
    ffmpeg_cmd = [
        "ffmpeg",
        "-rtsp_transport", "tcp",          # 强制TCP协议，避免丢包
        "-i", rtsp_url,                    # RTSP流地址
        "-c:v", "libx264",                 # 视频编码为H.264
        "-preset", "fast",                 # 编码速度预设
        "-c:a", "aac",                     # 音频编码为AAC
        "-strict", "experimental",         # 启用实验性编解码器
        "-f", "mp4",                       # 输出格式为MP4
        "-y",                              # 覆盖已有文件
        recording_path                      # 输出文件路径
    ]

    try:
        # 启动FFmpeg录制进程
        video_recording_process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.DEVNULL,     # 屏蔽FFmpeg输出
            stderr=subprocess.PIPE,        # 捕获错误信息
        )
        is_video_recording = True
        print(f"📹 MP4视频录制已开始：{recording_path}")
        return True, recording_path
    except Exception as e:
        print(f"❌ 启动MP4视频录制失败：{e}")
        return False, ""

def stop_video_recording():
    """
    停止视频录制（安全终止FFmpeg进程）
    :return: 停止是否成功
    """
    global video_recording_process, is_video_recording

    if not is_video_recording or not video_recording_process:
        print("❌ 视频录制未启动，无需停止")
        return False

    try:
        # 终止FFmpeg进程（安全停止录制）
        video_recording_process.terminate()
        # 等待进程退出，确保文件写入完成
        stderr_output, _ = video_recording_process.communicate(timeout=10)
        print(f"📹 FFmpeg stderr: {stderr_output.decode() if stderr_output else 'No stderr'}")
    except subprocess.TimeoutExpired:
        # 超时则强制杀死进程
        video_recording_process.kill()
        print("⚠️ 录制进程超时，已强制终止")
    except Exception as e:
        print(f"⚠️ 停止录制时出错：{e}")

    # 重置状态
    video_recording_process = None
    is_video_recording = False
    print("📹 MP4录制已停止")
    return True

def get_video_recording_path(room_id):
    """
    获取视频录制文件路径
    :param room_id: 会议室ID
    :return: 视频文件路径，如果不存在则返回空字符串
    """
    room_dir = get_room_directory(room_id)
    recording_path = os.path.join(room_dir, f"meeting_{room_id}.mp4")

    if os.path.exists(recording_path):
        return recording_path

    return ""