import subprocess
import os
import time
import threading
import queue
from aip import AipSpeech
from config import Config

# ==================== 全局变量 ====================
ffmpeg_process = None  # FFmpeg音频采集进程
transcription_queues = {}  # 转录文本队列，key为room_id
is_running = False  # 运行状态标识
current_room_id = None  # 当前处理的会议室ID

# ==================== 初始化百度ASR客户端 ====================
baidu_client = AipSpeech(
    Config.BAIDU_APP_ID, 
    Config.BAIDU_API_KEY, 
    Config.BAIDU_SECRET_KEY
)

def get_room_directory(room_id):
    """获取音频存储目录（简化版）"""
    dir_path = os.path.join(Config.BASE_AUDIO_DIR, room_id)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    return dir_path

def start_rtsp_audio_recording(rtsp_url, room_id):
    """启动FFmpeg从RTSP流提取音频并分片保存为WAV"""
    global ffmpeg_process, is_running, current_room_id
    room_dir = get_room_directory(room_id)
    
    # 删除之前的音频文件和转录文件
    try:
        for file in os.listdir(room_dir):
            if file.endswith(".wav") or file == "transcript.txt":
                os.remove(os.path.join(room_dir, file))
        print(f"✅ 已清理之前的会议文件：{room_dir}")
    except Exception as e:
        print(f"⚠️ 清理文件失败：{e}")
    
    # 创建新的转录队列
    global transcription_queues
    transcription_queues[room_id] = queue.Queue()
    
    # FFmpeg命令：仅提取音频，分片保存为16k/单声道/16bit WAV（适配百度ASR）
    ffmpeg_cmd = [
        "ffmpeg",
        "-rtsp_transport", "tcp",          # TCP协议更稳定
        "-i", rtsp_url,                    # RTSP流地址
        "-vn",                             # 禁用视频，只处理音频
        "-f", "segment",                   # 分片模式
        "-segment_time", str(Config.CHUNK_DURATION),  # 每10秒一个分片
        "-c:a", "pcm_s16le",               # 16bit PCM编码（百度ASR要求）
        "-ar", "16000",                    # 16k采样率
        "-ac", "1",                        # 单声道
        "-reset_timestamps", "1",          # 分片时间戳重置
        "-y",                              # 覆盖已有文件
        f"{room_dir}/chunk_%03d.wav"       # 分片文件名格式
    ]

    try:
        ffmpeg_process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        is_running = True
        current_room_id = room_id
        print(f"✅ 已启动音频采集：RTSP={rtsp_url}，分片存储至 {room_dir}")
        return True
    except Exception as e:
        print(f"❌ 启动音频采集失败：{e}")
        is_running = False
        current_room_id = None
        return False

def wait_file_stable(file_path, timeout=20, interval=0.5):
    """等待文件写入完成（避免读取未写完的音频文件）"""
    start = time.time()
    last_size = -1
    stable_count = 0

    while time.time() - start < timeout:
        if not os.path.exists(file_path):
            time.sleep(interval)
            continue

        size = os.path.getsize(file_path)
        if size > 0 and size == last_size:
            stable_count += 1
            if stable_count >= 2:  # 连续2次大小不变，认为写入完成
                return True
        else:
            stable_count = 0

        last_size = size
        time.sleep(interval)

    return False

def audio_to_text(audio_file_path):
    """调用百度ASR将WAV音频转文字"""
    # 读取音频文件二进制内容
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
            print(f"📝 音频转写结果：{text}")
            return text
        else:
            print(f"❌ 转写失败：{result.get('err_msg')}")
            return ""
    except Exception as e:
        print(f"❌ 调用百度ASR异常：{e}")
        return ""

def monitor_and_transcribe(room_id):
    """监控音频分片，实时转写为文字"""
    room_dir = get_room_directory(room_id)
    processed_files = set()
    full_transcript = ""  # 完整转录文本

    print(f"🔍 开始监控音频分片（按Ctrl+C停止）：{room_dir}")
    while is_running and current_room_id == room_id:
        # 获取当前目录下所有WAV分片文件
        try:
            current_files = set(f for f in os.listdir(room_dir) if f.endswith(".wav"))
            # 筛选未处理的新文件（按文件名排序，保证顺序）
            new_files = sorted(list(current_files - processed_files))

            for file in new_files:
                file_path = os.path.join(room_dir, file)
                # 等待文件写入稳定
                if not wait_file_stable(file_path):
                    print(f"⚠️ 文件 {file} 未写稳定，跳过")
                    processed_files.add(file)
                    continue

                # 音频转文字
                text = audio_to_text(file_path)
                if text:
                    full_transcript += text + "\n"
                    # 转写结果放入对应会议室的队列
                    global transcription_queues
                    if room_id in transcription_queues:
                        transcription_queues[room_id].put(text)
                    # 保存完整转录文本
                    with open(os.path.join(room_dir, "transcript.txt"), "w", encoding="utf-8") as f:
                        f.write(full_transcript)

                processed_files.add(file)

            time.sleep(1)  # 每秒检查一次新文件
        except Exception as e:
            print(f"❌ 监控音频分片异常：{e}")
            time.sleep(1)

def stop_audio_processing():
    """停止音频采集和转写"""
    global ffmpeg_process, is_running, current_room_id
    is_running = False
    current_room_id = None
    if ffmpeg_process:
        ffmpeg_process.terminate()
        ffmpeg_process = None
    print("🛑 音频处理已停止")

def get_transcription(room_id):
    """获取转录结果"""
    # 从 transcript.txt 文件中读取转录内容
    room_dir = get_room_directory(room_id)
    transcript_file = os.path.join(room_dir, "transcript.txt")
    
    transcriptions = []
    if os.path.exists(transcript_file):
        try:
            with open(transcript_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if content.strip():
                    # 按换行符分割，返回新增的内容
                    lines = content.strip().split('\n')
                    transcriptions = [line for line in lines if line.strip()]
        except Exception as e:
            print(f"❌ 读取转录文件失败：{e}")
    
    return transcriptions