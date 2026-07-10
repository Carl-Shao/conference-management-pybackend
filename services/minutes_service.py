import requests
import json
import os
import time
import pika
import threading
from config import Config

# ==================== 配置 ====================
OLLAMA_MODEL = "qwen2.5:7b"
OLLAMA_API_URL = "http://localhost:11434/api/chat"
MINUTES_FILE = "meeting_minutes.md"
STATUS_FILE = "minutes_status.json"

# ==================== 全局变量（worker线程管理）====================

_worker_threads = []
_stop_flag = threading.Event()

def get_mq_connection():
    """create connection to RabbitMQ"""
    credentials = pika.PlainCredentials(Config.RABBITMQ_USER, Config.RABBITMQ_PASS)
    return pika.BlockingConnection(
        pika.ConnectionParameters(
            host=Config.RABBITMQ_HOST,
            port=Config.RABBITMQ_PORT,
            credentials=credentials
        )
    )

# ==================== 状态管理 ====================

def _status_path(room_dir):
    return os.path.join(room_dir, STATUS_FILE)
 
 
def _write_status(room_dir, status, extra=None):
    data = {"status": status, "updatedAt": time.time()}
    if extra:
        data.update(extra)
    try:
        with open(_status_path(room_dir), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        print(f"❌ 写入纪要生成状态失败：{e}")

def get_minutes_status(room_id):
    """
    获取会议纪要生成状态
    :return: {"status": "pending"/"processing"/"completed"/"failed"/"not_found"}
    """
    room_dir = os.path.join(Config.BASE_AUDIO_DIR, room_id)
    status_path = _status_path(room_dir)
 
    if not os.path.exists(status_path):
        return {"status": "not_found"}
 
    try:
        with open(status_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 读取纪要生成状态失败：{e}")
        return {"status": "unknown"}

# ==================== 核心函数 ====================

def generate_meeting_minutes(transcript, room_dir):
    """
    调用本地Ollama模型，将完整转录稿生成结构化会议纪要
    """
    if not transcript:
        print("❌ 无转录文本，无法生成纪要")
        return ""

    prompt = f"""
你是一名专业的会议纪要分析助手。

你的任务是：根据输入的会议音频转录文本，将非结构化、口语化的会议内容转换为一份准确、规范、结构化的会议纪要。

你的工作不是简单总结会议内容，而是进行信息提取与重构：
- 理解会议背景和目标；
- 识别核心议题；
- 提取关键事实和讨论内容；
- 区分个人观点、客观事实和最终决策；
- 提取明确的行动任务；
- 总结会议共识、未解决问题和后续方向。

请严格遵守以下规则。


====================
一、内部处理流程
====================

请按照以下流程完成任务：

阶段1：文本理解与清洗

- 去除无意义口语词：
  如“嗯”“那个”“然后”“就是”等。
- 合并重复表达。
- 修正明显的语音识别错误。
- 保留原始语义，不改变事实。

阶段2：信息提取

从会议文本中识别：
- 会议背景；
- 会议目标；
- 参会人员；
- 核心议题；
- 客观事实；
- 讨论观点；
- 最终决策；
- 行动任务；
- 风险和未解决问题。

阶段3：信息校验

生成结果前，内部检查：
- 是否存在原文没有的信息；
- 是否将个人观点错误识别为会议决定；
- 是否把建议错误转换成任务；
- 是否遗漏重要行动；
- 是否存在逻辑冲突。

以上检查过程不要输出，只输出最终会议纪要。


====================
二、信息真实性规则
====================

所有内容必须基于会议转录文本。

禁止：
- 编造不存在的事实；
- 添加不存在的数据；
- 虚构负责人；
- 虚构时间节点；
- 虚构会议决定。

信息可信度按照以下规则处理：

1. 明确事实：
原文直接说明的信息。

例如：
“李明负责完成接口开发。”

可以直接记录：
负责人：李明。


2. 上下文合理关联：
允许根据明确上下文进行指代解析。

例如：

前文：
“小王是前端开发。”

后文：
“小王负责页面联调。”

可以理解为：
前端人员小王负责页面联调。


3. 无法确认的信息：

如果负责人、时间、决定等关键信息无法从上下文推导：

填写：
“未明确”。

禁止进行猜测。


====================
三、会议基础信息提取
====================

如果文本包含相关信息，请提取：
- 会议时间；
- 会议地点；
- 参会人员；
- 会议主持人。

如果没有提供：
填写：
“未明确”。

不要自行补充。


====================
四、会议主题提取规则
====================

从会议内容中提取最核心主题。

要求：
- 使用简洁的名词短语；
- 不超过20个字；
- 体现会议目的，而不是简单描述讨论过程。

错误：
“讨论了一些项目问题”

正确：
“项目进度风险评估”

“新版本上线计划讨论”


====================
五、核心讨论要点提取规则
====================

根据会议实际信息量动态提取。

建议3-8条。

每条讨论内容需要包含：

1. 讨论对象：
会议讨论的问题或事项。

2. 当前情况：
相关背景、状态或存在的问题。

3. 关键观点：
主要原因、影响、方案或意见。


避免输出空泛描述。

错误：
“讨论项目进展。”

正确：
“项目当前开发进度低于计划，主要原因是接口联调延期，需要协调后端资源解决。”


====================
六、观点、事实、决策区分规则
====================

必须严格区分：

## 1. 事实

已经发生或确定存在的信息。

例如：
“系统当前存在登录失败问题。”


## 2. 观点

个人意见、建议或分析。

例如：
“张三认为应该延期上线。”


## 3. 决策

会议最终确定执行的事项。


只有满足以下条件，才能记录为决策：

显式决策：
- “通过”
- “采用”
- “确定执行”
- “决定”

隐式决策：
- “那就按照这个方案推进”
- “后续就这么安排”
- “可以，就这样执行”

但隐式决策必须满足：
- 有明确执行对象；
- 有明确行动方向；
- 没有明显反对意见。


如果会议没有形成决定：
填写：
“无明确决策”。


====================
七、冲突观点处理规则
====================

如果会议存在不同意见：

不要强行合并为统一结论。

例如：

张三：
支持方案A。

李四：
支持方案B。


应记录：
“会议针对方案A和方案B存在不同意见，暂未形成最终决定。”


只有后续明确选择方案：
才能记录为最终决策。


====================
八、待办事项提取规则
====================

只记录明确行动任务。


有效待办至少包含：
- 明确行动；
- 明确目标。


例如：

有效：
“李明本周完成接口测试。”

无效：
“以后考虑优化数据库。”


禁止：
把建议、想法、讨论方向转换为任务。


待办事项包含：
- 事项；
- 负责人；
- 完成时间；
- 当前状态。


状态包括：
- 待开始；
- 进行中；
- 已完成；
- 未明确。


如果缺少：

负责人：
填写“未明确”。

时间：
填写“未明确”。


如果没有明确待办：
保持表格结构，内容填写“无”。


====================
九、人员角色识别规则
====================

如果文本包含发言人信息：
识别：
- 任务负责人；
- 决策提出者；
- 关键参与人员。

禁止根据姓名、职位称呼推测身份。

例如：
原文：
“王经理负责测试。”

输出：
负责人：王经理。


不要输出：
项目经理王经理。

除非文本明确说明。


====================
十、异常输入处理
====================

如果会议文本：
- 为空；
- 内容过短；
- 不包含有效会议讨论；

输出：
“未检测到有效会议内容，无法生成会议纪要。”


====================
十一、输出格式要求
====================

必须严格使用 Markdown 格式。


输出结构如下：

# 会议纪要


## 1. 会议信息

|字段|内容|
|-|-|
|会议主题| |
|会议时间| |
|会议地点| |
|参会人员| |
|主持人| |


## 2. 核心讨论要点

- 要点1：
  （讨论事项 + 当前情况 + 关键观点）

- 要点2：
  （讨论事项 + 当前情况 + 关键观点）


## 3. 关键决策

- 决策1：
  （明确形成的会议决定）

如果没有明确决策：
无明确决策。


## 4. 待办事项

|事项|负责人|完成时间|状态|
|-|-|-|-|
|任务内容|负责人或未明确|时间或未明确|状态或未明确|


如果没有明确待办事项：
|事项|负责人|完成时间|状态|
|-|-|-|-|
|无|无|无|无|


## 5. 风险与未解决问题

记录：
- 尚未解决的问题；
- 存在争议的问题；
- 后续需要关注的风险。

如果没有：
无。


## 6. 会议总结

总结：
- 已达成的共识；
- 已解决的问题；
- 未解决的问题；
- 下一步行动方向。

要求：
- 简洁；
- 客观；
- 商务化表达；
- 不加入个人评价。


====================

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
            timeout=120,
        )

        if response.status_code == 200:
            response_json = response.json()
            minutes = response_json["message"]["content"]
            # 保存会议纪要文件
            minutes_path = os.path.join(room_dir, MINUTES_FILE)
            with open(minutes_path, "w", encoding="utf-8") as f:
                f.write(minutes)
            print(f"\n✅[线程 {threading.current_thread().name}] 会议纪要已生成：{minutes_path}")
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

# ==================== 异步任务提交 ====================

def request_minutes_generation(room_id):
    """
    提交一个"生成会议纪要"的异步任务到MQ，立即返回，不等待Ollama处理完成。
    真正的生成动作由下面的worker线程池并发执行，多个会议室的任务可以同时被不同worker领走处理。
    :param room_id: 会议ID
    :return: 是否提交成功
    """
    room_dir = os.path.join(Config.BASE_AUDIO_DIR, room_id)
    if not os.path.exists(room_dir):
        os.makedirs(room_dir)
 
    transcript_path = os.path.join(room_dir, "transcript.txt")
    if not os.path.exists(transcript_path):
        print(f"❌ 会议{room_id}转录文件不存在，无法提交纪要生成任务")
        return False
 
    try:
        connection = get_mq_connection()
        channel = connection.channel()
        channel.exchange_declare(exchange='minutes_events', exchange_type='direct', durable=True)
        channel.queue_declare(queue='minutes_generate', durable=True)
        channel.queue_bind(queue='minutes_generate', exchange='minutes_events', routing_key='minutes.generate')
 
        message = json.dumps({'room_id': room_id, 'timestamp': time.time()})
        channel.basic_publish(
            exchange='minutes_events',
            routing_key='minutes.generate',
            body=message,
            properties=pika.BasicProperties(delivery_mode=2)
        )
        connection.close()
 
        _write_status(room_dir, "pending")
        print(f"📤 已提交会议纪要生成任务：会议{room_id}")
        return True
    except Exception as e:
        print(f"❌ 提交纪要生成任务失败：{e}")
        return False


# ==================== Worker线程（并发处理多个会议室的纪要生成）====================
 
def _minutes_worker_entrypoint(worker_index):
    """
    单个worker线程的完整生命周期：独立连接RabbitMQ，prefetch=1串行消费任务。
 
    Ollama运行在自己的服务进程里，不是加载进Python进程的内存，
    只发HTTP请求、等待响应
    多个线程可以真正并发地发请求、并发地等待响应，不需要额外的进程级隔离。
 
    并发上限取决于Ollama服务端自身的并发配置（OLLAMA_NUM_PARALLEL环境变量）。
    """
    connection = get_mq_connection()
    channel = connection.channel()
 
    channel.exchange_declare(exchange='minutes_events', exchange_type='direct', durable=True)
    channel.queue_declare(queue='minutes_generate', durable=True)
    channel.queue_bind(queue='minutes_generate', exchange='minutes_events', routing_key='minutes.generate')
 
    channel.basic_qos(prefetch_count=1)
 
    def callback(ch, method, properties, body):
        try:
            data = json.loads(body)
            room_id = data['room_id']
            room_dir = os.path.join(Config.BASE_AUDIO_DIR, room_id)
 
            print(f"📩 [minutes-worker-{worker_index}] 收到纪要生成任务：会议{room_id}")
            _write_status(room_dir, "processing")
 
            minutes = generate_minutes_from_transcript_file(room_id)
 
            if minutes:
                _write_status(room_dir, "completed")
                print(f"✅ [minutes-worker-{worker_index}] 会议{room_id}纪要生成完成")
            else:
                _write_status(room_dir, "failed")
                print(f"❌ [minutes-worker-{worker_index}] 会议{room_id}纪要生成失败")
 
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            print(f"❌ [minutes-worker-{worker_index}] 处理纪要生成任务异常：{e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
 
    channel.basic_consume(queue='minutes_generate', on_message_callback=callback)
    print(f"🔍 [minutes-worker-{worker_index}] 已就绪，开始监听纪要生成队列")
 
    # 用process_data_events轮询代替start_consuming()的死循环，
    # 这样可以定期检查_stop_flag，支持优雅停止
    try:
        while not _stop_flag.is_set():
            connection.process_data_events(time_limit=1)
    finally:
        try:
            channel.stop_consuming()
            connection.close()
        except Exception:
            pass
 
 
def start_minutes_service(worker_count=None):
    """
    启动会议纪要生成服务：拉起N个worker线程并发消费MQ任务
    :param worker_count: worker线程数，默认读取 Config.MINUTES_WORKER_COUNT
    """
    global _worker_threads
    _stop_flag.clear()
 
    worker_count = worker_count or getattr(Config, "MINUTES_WORKER_COUNT", 4)
    print(f"🚀 启动会议纪要生成服务，worker数量：{worker_count}...")
 
    for i in range(worker_count):
        t = threading.Thread(
            target=_minutes_worker_entrypoint,
            args=(i,),
            daemon=True,
            name=f"minutes-worker-{i}"
        )
        t.start()
        _worker_threads.append(t)
        print(f"✅ minutes worker-{i} 已启动")
 
    return _worker_threads
 
 
def stop_minutes_service():
    """停止会议纪要生成服务的所有worker线程"""
    global _worker_threads
    _stop_flag.set()
    for t in _worker_threads:
        t.join(timeout=5)
    _worker_threads = []
    print("🛑 会议纪要生成服务已停止")