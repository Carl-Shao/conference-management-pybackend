import subprocess
import pika
import os
import time
import json
from config import Config

# ==================== 全局变量 ====================
audio_recording_process = None  # FFmpeg音频录制进程
is_audio_recording = False      # 是否正在录制音频
    

def get_mq_connection():
    credentials = pika.PlainCredentials(Config.RABBITMQ_USER, Config.RABBITMQ_PASS)
    return pika.BlockingConnection(
        pika.ConnectionParameters(host=Config.RABBITMQ_HOST, port=Config.RABBITMQ_PORT, credentials=credentials)
    )

def publish_audio_ready(room_id, audio_path):
    """
    音频文件写完后，发一条消息到MQ，替代原来靠asr_service扫文件夹发现新文件
    :param room_id: 会议室ID（消息里字段名为meeting_id，与asr_service保持一致）
    :param audio_path: 音频文件路径
    """
    try:
        connection = get_mq_connection()
        channel = connection.channel()
        channel.exchange_declare(
            exchange='audio_events',
            exchange_type='direct',
            durable=True
        )
        channel.queue_declare(queue='audio_ready', durable=True)
        channel.queue_bind(
            queue='audio_ready',
            exchange='audio_ready',
            routing_key='audio.ready'
        )

        message = json.dump({
            'meeting_id':room_id,
            'audio_path':audio_path,
            'timestamp':time.time()
        })
        channel.basic_publish(
            exchange='audio_events',
            routing_key='audio.ready',
            body=message,
            properties=pika.BasicProperties(delivery_mode=2)   #持久化消息
        )
        connection.close()
        print("📤 已发布音频就绪消息：会议{room_id}, 文件{audio_path}")

    except Exception as e:
        print(f"❌ 发布MQ消息失败：{e}")


def get_room_directory(room_id):
    """获取指定会议室的存储目录（确保目录存在）"""
    # 使用BASE_AUDIO_DIR作为基础目录，创建audio子目录
    base_dir = Config.BASE_AUDIO_DIR
    room_dir = os.path.join(base_dir, "audio", room_id)  # 在音频目录下创建audio子目录
    if not os.path.exists(room_dir):
        os.makedirs(room_dir)
    return room_dir

def start_audio_recording(room_id, rtsp_url):
    """
    开始从RTSP流提取音频到WAV文件
    :param room_id: 会议室ID（用于区分存储目录）
    :param rtsp_url: RTSP流地址
    :return: (录制是否成功启动, 录制文件路径)
    """
    global audio_recording_process, is_audio_recording

    # 获取录制文件存储路径
    room_dir = get_room_directory(room_id)
    output_filename = f"audio_{room_id}.wav"
    recording_path = os.path.join(room_dir, output_filename)

    # FFmpeg命令：仅提取音频，保存为WAV格式
    ffmpeg_cmd = [
        "ffmpeg",
        "-rtsp_transport", "tcp",          # 强制TCP协议，避免丢包
        "-i", rtsp_url,                    # RTSP流地址
        "-vn",                             # 禁用视频
        "-c:a", "pcm_s16le",               # 音频编码为16bit PCM（无损）
        "-ar", "16000",                    # 16k采样率
        "-ac", "1",                        # 单声道
        "-f", "wav",                       # 输出格式为WAV
        "-y",                              # 覆盖已有文件
        recording_path                      # 输出文件路径
    ]

    try:
        # 启动FFmpeg录制进程
        audio_recording_process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.DEVNULL,     # 屏蔽FFmpeg输出
            stderr=subprocess.PIPE,        # 捕获错误信息
        )
        is_audio_recording = True
        print(f"🔊 WAV音频录制已开始：{recording_path}")
        return True, recording_path
    except Exception as e:
        print(f"❌ 启动WAV音频录制失败：{e}")
        return False, ""

def stop_audio_recording(room_id, recording_path):
    """
    停止音频录制（安全终止FFmpeg进程），并发布MQ消息通知ASR服务
    :param room_id: 会议室ID
    :param recording_path: 录制文件路径（可用get_audio_recording_path获取）
    :return: 停止是否成功
    """
    global audio_recording_process, is_audio_recording

    if not is_audio_recording or not audio_recording_process:
        print("❌ 音频录制未启动，无需停止")
        return False

    try:
        # 终止FFmpeg进程（安全停止录制）
        audio_recording_process.terminate()
        # 等待进程退出，确保文件写入完成
        stderr_output, _ = audio_recording_process.communicate(timeout=10)
        print(f"🔊 FFmpeg stderr: {stderr_output.decode() if stderr_output else 'No stderr'}")
    except subprocess.TimeoutExpired:
        # 超时则强制杀死进程
        audio_recording_process.kill()
        print("⚠️ 音频录制进程超时，已强制终止")
    except Exception as e:
        print(f"⚠️ 停止音频录制时出错：{e}")

    # 重置状态
    audio_recording_process = None
    is_audio_recording = False
    print("🔊 WAV音频录制已停止")

    # 文件确认写完后，发布消息通知ASR服务处理，替代原来的文件夹扫描发现机制
    publish_audio_ready(room_id, recording_path)
    return True

def get_audio_recording_path(room_id):
    """
    获取音频录制文件路径
    :param room_id: 会议室ID
    :return: 音频文件路径，如果不存在则返回空字符串
    """
    room_dir = get_room_directory(room_id)
    recording_path = os.path.join(room_dir, f"audio_{room_id}.wav")

    if os.path.exists(recording_path):
        return recording_path

    return ""

def convert_to_wav(input_path, output_path):
    """
    将输入文件转换为WAV格式
    :param input_path: 输入文件路径
    :param output_path: 输出WAV文件路径
    :return: 转换是否成功
    """
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", input_path,                  # 输入文件路径
        "-c:a", "pcm_s16le",              # 音频编码为16bit PCM（无损）
        "-ar", "16000",                   # 16k采样率
        "-ac", "1",                       # 单声道
        "-f", "wav",                      # 输出格式为WAV
        "-y",                             # 覆盖已有文件
        output_path                       # 输出文件路径
    ]

    try:
        result = subprocess.run(
            ffmpeg_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True
        )
        print(f"✅ 文件已转换为WAV：{output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ WAV转换失败：{e.stderr.decode()}")
        return False
    except Exception as e:
        print(f"❌ WAV转换异常：{e}")
        return False