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
    
    # 百度ASR配置
    BAIDU_APP_ID = "7528270"
    BAIDU_API_KEY = "sacHUMQacicQRXx4qeUDqwKb"
    BAIDU_SECRET_KEY = "sjpWq0MuJ8HsH3kg47hM0Nh0fls0QZu6"
    
    # 音频处理配置
    CHUNK_DURATION = 10                      # 音频分片时长（秒）
    BASE_AUDIO_DIR = r"D:\project_all\rstp1\storage"   # 音频存储目录
