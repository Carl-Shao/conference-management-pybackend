import subprocess

# test 0
# 环境是否就绪
# RabbitMQ是否在跑
result_rabbitmq = subprocess.run(
    ['curl -u shaoqi:Shaoqi2006 http://localhost:15672/api/overview'],
    shell=True, 
    capture_output=True,
    text=True
    )

print("\n\n\nRabbitMQ:\n", result_rabbitmq.stdout)

# Ollama是否在跑，模型是否已下载
result_ollama = subprocess.run(
    ['curl http://localhost:11434/api/tags'],
    shell=True,
    capture_output=True,
    text=True
)

print("\n\n\nOllama:\n", result_ollama.stdout)

# ffmpeg是否装好
result_ffmepeg = subprocess.run(
    ['ffmpeg -version'],
    shell=True,
    capture_output=True,
    text=True
)

print("\n\n\nFFmpeg:\n", result_ollama.stdout)

# GPU/CUDA是否可用（FunASR需要）
print("\n\n\n")
command = ["python3", "-c", "import torch; print(torch.cuda.is_available())"]
subprocess.run(command)