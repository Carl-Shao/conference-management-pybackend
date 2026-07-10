import pika
import os
import time
import threading
import json
import multiprocessing
from funasr import AutoModel
from config import Config

# ==================== 全局变量 ====================
asr_results = {}    
_worker_processes = []

# ==================== 每个worker进程独立加载一份 ====================
# 模型改为懒加载，每个worker进程各自维护自己的实例，互不共享、互不影响。
_process_local_model = None

def get_asr_model():
    """
    获取当前进程的模型实例（懒加载，进程内单例）
    每个worker子进程第一次调用时会加载一份自己的模型
    """
    global _process_local_model
    if _process_local_model is None:
        print(f"[PID {os.getpid()}] 🔄 正在加载FunASR模型...")
        _process_local_model = AutoModel(
            model = "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
            vad_model = "fsmn-vad",
            device = "cuda"
        )
        print(f"[PID {os.getpid()}] ✅ FunASR模型加载完成")
    return _process_local_model

def get_room_directory(room_id):
    """获取音频存储目录"""
    dir_path = os.path.join(Config.BASE_AUDIO_DIR, room_id)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    return dir_path

def get_mq_connection():
    "create connection to RabbitMQ"
    credentials = pika.PlainCredentials(Config.RABBITMQ_USER, Config.RABBITMQ_PASS)
    return pika.BlockingConnection(
        pika.ConnectionParameters(
            host=Config.RABBITMQ_HOST,
            port=Config.RABBITMQ_PORT,
            credentials=credentials
        )
    )

def process_asr_with_local(audio_file_path):
    try:
        print(f"🎧 [PID {os.getpid()}] 开始本地ASR识别:{audio_file_path}")
        model = get_asr_model()
        result = model.generate(input=audio_file_path)

        text = ""
        if result:
            text = result[0].get("text", "")

        print(f"📝 [PID {os.getpid()}] ASR结果:{text}")
        return text

    except Exception as e:
        print(f"❌ [PID {os.getpid()}] FunASR识别失败:{e}")
        return ""

def handle_asr_task(meeting_id, audio_path):
    """
    处理ASR任务 - 执行识别并将结果存储
    :param meeting_id: 会议ID
    :param audio_path: 音频文件路径
    """
    print(f"👂 [PID {os.getpid()}] 开始处理ASR任务：会议{meeting_id}, 音频{audio_path}")

    result_text = process_asr_with_local(audio_path)
    if meeting_id not in asr_results:
        asr_results[meeting_id] = []
    asr_results[meeting_id].append({
        'audio_path': audio_path,
        'text': result_text,
        'timestamp': time.time()
    })

    room_dir = os.path.join(Config.BASE_AUDIO_DIR, meeting_id)
    if not os.path.exists(room_dir):
        os.makedirs(room_dir)

    transcript_file = os.path.join(room_dir, "transcript.txt")
    with open(transcript_file, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {result_text}\n")
 
    print(f"✅ [PID {os.getpid()}] ASR任务处理完成：会议{meeting_id}")


# ==================== Worker进程入口 ====================

def _consumer_worker_entrypoint():
    """
    单个worker进程的完整生命周期：
    1. 加载自己的模型实例
    2. 独立连接RabbitMQ
    3. prefetch_count=1，串行消费（保证同一进程内不并发调用model.generate）
 
    多个worker同时跑，就是多个模型实例并发工作 —— 并发数只受你起多少个worker（进而受硬件算力）限制，
    不受代码结构限制。
    """
    # 提前加载模型，避免第一条消息到来时才现加载、拖慢首次响应
    get_asr_model()

    connection = get_mq_connection()
    channel = connection.channel()

    channel.exchange_declare(exchange='audio_events', exchange_type='direct', durable=True)
    channel.queue_declare(queue='audio_ready', durable=True)
    channel.queue_bind(queue='audio_ready', exchange='audio_events', routing_key='audio.ready')

    def callback(ch, method, properties, body):
        try:
            data = json.load(body)
            meeting_id = data['meeting_id']
            audio_path = data['audio_path']
            print(f"📩 [PID {os.getpid()}] 收到音频就绪消息：会议{meeting_id}, 文件{audio_path}")

            handle_asr_task(meeting_id, audio_path)

            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            print(f"❌ [PID {os.getpid()}] ASR任务处理失败：{e}")
            # 失败不重投，避免坏文件反复消费；建议给队列配死信队列(DLX)方便排查
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    channel.basic_consume(queue="audio_ready", on_message_callback=callback)
    print(f"🔍 [PID {os.getpid()}] worker已就绪，开始监听RabbitMQ音频就绪队列")
    channel.start_consuming()


def start_asr_service(worker_count=None):
    """
    启动ASR服务：拉起N个独立worker进程，每个进程各自持有一份模型实例，并发消费MQ任务。
 
    :param worker_count: worker进程数，默认读取 Config.ASR_WORKER_COUNT，
                          不设置时退化为1（与原来单进程行为一致）
    """
    global _worker_processes
    worker_count = worker_count or getattr(Config, "ASR_WORKER_COUNT", 1)
    print(f"🚀 启动ASR服务，worker数量：{worker_count}...")

    for i in range (worker_count):
        p = multiprocessing.Process(
            target = _consumer_worker_entrypoint,
            daemon = True,
            name = f"asr-worker-{i}"
        )
        p.start()
        _worker_processes.append(p)
        print(f"✅ ASR worker-{i} 已启动 (PID {p.pid})")

    return _worker_processes


def stop_asr_service():
    """
    停止ASR服务
    """
    global _worker_processes

    for p in _worker_processes:
        if p.is_alive():
            p.terminate()

    for p in _worker_processes:
        p.join(timeout=5)

    _worker_processes = []
    print("🛑 ASR服务已停止")



def get_transcript(room_id):
    """
    获取会议转录文本
    :param room_id: 会议ID
    :return: 转录文本列表
    """
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