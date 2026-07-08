from flask import Flask, request, jsonify
import threading
import time
from services.asr_service import handle_asr_task

app = Flask(__name__)

@app.route('/asr/task', methods=['POST'])
def receive_asr_task():
    """
    接收ASR任务的HTTP API端点
    请求体示例:
    {
        "meetingId": "1001",
        "audioPath": "/path/to/audio/chunk001.wav"
    }
    """
    try:
        # 获取JSON请求数据
        data = request.get_json()

        if not data or 'meetingId' not in data or 'audioPath' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing meetingId or audioPath in request body'
            }), 400

        meeting_id = data['meetingId']
        audio_path = data['audioPath']

        print(f"📥 收到ASR任务请求：会议{meeting_id}, 音频{audio_path}")

        # 在后台线程中处理ASR任务，以便快速响应HTTP请求
        asr_thread = threading.Thread(
            target=handle_asr_task,
            args=(meeting_id, audio_path)
        )
        asr_thread.daemon = True
        asr_thread.start()

        # 返回成功响应
        response = {
            'success': True,
            'message': 'ASR task received and processing started',
            'meetingId': meeting_id,
            'audioPath': audio_path,
            'timestamp': time.time()
        }

        return jsonify(response), 200

    except Exception as e:
        print(f"❌ 处理ASR任务请求时出错：{e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/asr/status', methods=['GET'])
def get_asr_status():
    """
    获取ASR服务状态
    """
    return jsonify({
        'status': 'running',
        'service': 'ASR HTTP Receiver',
        'timestamp': time.time()
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=False)