import subprocess
import pika
import os
import time
import threading
import json
from funasr import AutoModel
from config import Config

# ==================== 全局变量 ====================
asr_results = {}  # 存储ASR识别结果，key为meeting_id
_mq_channel = None      # 保存消费者channel引用，便于停止
_mq_connection = None   # 保存消费者connection引用，便于停止

# =================== 本地ASR模型 ===================
asr_model = AutoModel(
    model = "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    vad_model = "fsmn-vad",
    device = "cuda"
)
print("FunASR Model Loading Successfully.")

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

def start_mq_consumer():
    """
    start RabbitMQ consumer, listen audio ready queue
    """
    global _mq_channel, _mq_connection
    
    def consume():
        global _mq_channel, _mq_connection
        try:
            _mq_connection = get_mq_connection()
            _mq_channel = _mq_connection.channel()

            _mq_channel.exchange_declare(
                exchange='audio_events',
                exchange_type='direct',
                durable=True
            )
            _mq_channel.queue_declare(queue='audio_ready', durable=True)
            _mq_channel.queue_bind(
                queue='audio_ready',
                exchange='audio_events',
                routing_key='audio.ready'
            )

            # prefetch=1: 保证同一时刻只处理一条消息
            # asr_model是单个模型实例，多线程并发调用generate容易有问题
            # 如需提速应该是"多开消费者进程"做水平扩展，而不是同进程内并发
            _mq_channel.basic_qos(prefetch_count=1)

            def callback(ch, method, properties, body):
                try:
                    data = json.load(body)
                    meeting_id = data['meeting_id']
                    audio_path = data['audio_path']
                    print(f"📩 收到音频就绪消息：会议{meeting_id}, 文件{audio_path}")

                    handle_asr_task(meeting_id, audio_path)

                    ch.basic_ack(delivery_tag=method.delivery_tag)

                except Exception as e:
                    print(f"❌ ASR任务处理失败：{e}")
                    # 失败不重投，避免坏文件反复消费；建议给队列配死信队列(DLX)方便排查
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            _mq_channel.basic_consume(
                queue='audio_ready', 
                on_message_callback=callback
            )
            print("🔍 开始监听RabbitMQ音频就绪队列")
            _mq_channel.start_consuming()

        except Exception as e:
            print(f"❌ MQ消费者异常退出：{e}")

    consumer_thread = threading.Thread(target=consume, daemon=True)
    consumer_thread.start()
    return consumer_thread

def stop_mq_consumer():
    """stop consumer"""
    global _mq_channel, _mq_connection
    try:
        if _mq_channel is not None:
            _mq_channel.stop_consuming
        if _mq_connection is not None:
            _mq_connection.close()
        print("🔍 已停止监听RabbitMQ音频就绪队列")

    except Exception as e:
        print(f"⚠️ 停止MQ消费者时出错：{e}")
    finally:
        _mq_channel = None
        _mq_connection = None

def process_asr_with_local(audio_file_path):
    try:
        print(f"🎧 开始本地ASR识别:{audio_file_path}")

        result = asr_model.generate(
            input = audio_file_path
        )

        text = ""

        if result:
            text = result[0].get("text", "")

        print(f"📝 ASR结果:{text}")
        return text

    except Exception as e:
        print(f"❌ FunASR识别失败:{e}")
        return ""

def handle_asr_task(meeting_id, audio_path):
    """
    处理ASR任务 - 执行识别并将结果存储
    :param meeting_id: 会议ID
    :param audio_path: 音频文件路径
    """
    print(f"👂 开始处理ASR任务：会议{meeting_id}, 音频{audio_path}")

    # 执行ASR识别
    result_text = process_asr_with_local(audio_path)

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