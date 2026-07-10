class Config:
    SECRET_KEY = 'your-secret-key-here'
    DEBUG = True
    PORT = 5000
    
    # 数据库配置
    DB_HOST = 'localhost'
    DB_PORT = 3306
    DB_USER = 'root'
    DB_PASSWORD = '123456'
    DB_NAME = '若依2026'
    DB_CHARSET = 'utf8mb4'
    
    # RTSP配置
    RTSP_URL = 'rtsp://localhost:8554/stream'
    
    # 静态文件路径
    STATIC_FOLDER = 'static'
    
    # 音频和转录文件存储路径
    AUDIO_FOLDER = 'static/audio'
    TRANSCRIPT_FOLDER = 'static/transcripts'
    
    # 音频处理配置
    CHUNK_DURATION = 10                      # 音频分片时长（秒）
    BASE_AUDIO_DIR = r"D:\project_all\rstp1\storage"   # 音频存储目录

    # 并发处理转录配置
    ASR_WORKER_COUNT = 10 # 并发处理10个会议室的转录

    # Ollama并发配置
    MINUTES_WORKER_COUNT = 4

    # RabbitMQ 配置 
    RABBITMQ_HOST = 'localhost'
    RABBITMQ_PORT = 5672
    RABBITMQ_USER = 'shaoqi'
    RABBITMQ_PASS = 'Shaoqi2006'
    RABBITMQ_QUEUE = 'audio_ready_queue'
