#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
会议管理系统AI服务API
提供ASR语音转文字和会议纪要生成功能给Java后端调用
"""

from flask import Flask, request, jsonify
import os
import sys
import logging
from threading import Thread

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from services.rtsp_service import (
    start_rtsp_audio_recording,
    monitor_and_transcribe,
    stop_audio_processing,
    get_transcription,
    is_running
)
from services.recording_service import (
    start_recording,
    stop_recording,
    get_recording_path
)
from services.minutes_service import (
    generate_meeting_minutes,
    get_meeting_minutes,
    generate_minutes_from_transcript_file
)

app = Flask(__name__)
app.config.from_object(Config)

# 手动添加CORS头
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

# 全局变量用于跟踪正在运行的监控线程
monitoring_threads = {}

@app.route("/")
def index():
    return "ai services are running."

@app.route('/api/v1/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'healthy',
        'service': 'Conference AI Services API',
        'version': '1.0.0'
    })

@app.route('/api/v1/asr/start-recording', methods=['POST'])
def start_asr_recording():
    """
    启动RTSP音频录制和实时ASR转录
    Request Body:
    {
        "rtsp_url": "rtsp://...",
        "room_id": "meeting_room_001"
    }
    """
    try:
        data = request.get_json()
        rtsp_url = data.get('rtsp_url')
        room_id = data.get('room_id')

        if not rtsp_url or not room_id:
            return jsonify({
                'error': 'Missing rtsp_url or room_id',
                'code': 400
            }), 400

        logger.info(f"Starting ASR recording for room {room_id}, RTSP: {rtsp_url}")

        success = start_rtsp_audio_recording(rtsp_url, room_id)

        if success:
            # 检查是否已经有监控线程在运行，如果有则停止
            if room_id in monitoring_threads and monitoring_threads[room_id].is_alive():
                logger.warning(f"Stopping existing monitoring thread for room {room_id}")
                stop_audio_processing()

            # 启动新的监控线程
            thread = Thread(target=monitor_and_transcribe, args=(room_id,), daemon=True)
            thread.start()
            monitoring_threads[room_id] = thread

            return jsonify({
                'success': True,
                'message': 'ASR recording started successfully',
                'data': {
                    'room_id': room_id,
                    'rtsp_url': rtsp_url,
                    'status': 'recording'
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to start ASR recording',
                'error': 'FFmpeg process failed to start'
            }), 500

    except Exception as e:
        logger.error(f"Error starting ASR recording: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Server error occurred',
            'error': str(e)
        }), 500

@app.route('/api/v1/recording/start-full', methods=['POST'])
def start_full_recording():
    """
    启动完整RTSP音频录制（不分片，生成一个完整文件）
    Request Body:
    {
        "rtsp_url": "rtsp://...",
        "room_id": "meeting_room_001"
    }
    """
    try:
        data = request.get_json()
        rtsp_url = data.get('rtsp_url')
        room_id = data.get('room_id')

        if not rtsp_url or not room_id:
            return jsonify({
                'error': 'Missing rtsp_url or room_id',
                'code': 400
            }), 400

        logger.info(f"Starting full recording for room {room_id}, RTSP: {rtsp_url}")

        success = start_recording(room_id, rtsp_url)

        if success:
            return jsonify({
                'success': True,
                'message': 'Full recording started successfully',
                'data': {
                    'room_id': room_id,
                    'rtsp_url': rtsp_url,
                    'status': 'recording'
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to start full recording',
                'error': 'FFmpeg process failed to start'
            }), 500

    except Exception as e:
        logger.error(f"Error starting full recording: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Server error occurred',
            'error': str(e)
        }), 500

@app.route('/api/v1/asr/stop-recording', methods=['POST'])
def stop_asr_recording():
    """
    停止ASR录音
    Request Body:
    {
        "room_id": "meeting_room_001"  # 可选，如果不提供则停止所有
    }
    """
    try:
        data = request.get_json()
        room_id = data.get('room_id', None)

        logger.info(f"Stopping ASR recording for room {room_id if room_id else 'all rooms'}")

        stop_audio_processing()

        # 如果指定了room_id，则移除对应的线程
        if room_id and room_id in monitoring_threads:
            del monitoring_threads[room_id]

        return jsonify({
            'success': True,
            'message': 'ASR recording stopped successfully'
        })
    except Exception as e:
        logger.error(f"Error stopping ASR recording: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Server error occurred',
            'error': str(e)
        }), 500

@app.route('/api/v1/recording/stop-full', methods=['POST'])
def stop_full_recording():
    """
    停止完整录音
    """
    try:
        logger.info("Stopping full recording")

        success = stop_recording()

        if success:
            return jsonify({
                'success': True,
                'message': 'Full recording stopped successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No active recording to stop'
            }), 400

    except Exception as e:
        logger.error(f"Error stopping full recording: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Server error occurred',
            'error': str(e)
        }), 500

@app.route('/api/v1/recording/path/<room_id>', methods=['GET'])
def get_recording_path_api(room_id):
    """
    获取完整录音文件路径
    """
    try:
        logger.info(f"Getting recording path for room {room_id}")
        recording_path = get_recording_path(room_id)

        if recording_path:
            return jsonify({
                'success': True,
                'data': {
                    'room_id': room_id,
                    'recording_path': recording_path
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No recording file found for this room'
            }), 404

    except Exception as e:
        logger.error(f"Error getting recording path: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Server error occurred',
            'error': str(e)
        }), 500

@app.route('/api/v1/asr/get-transcript/<room_id>', methods=['GET'])
def get_transcript_api(room_id):
    """
    获取实时转录文本
    """
    try:
        logger.info(f"Getting transcript for room {room_id}")
        transcriptions = get_transcription(room_id)

        return jsonify({
            'success': True,
            'data': {
                'room_id': room_id,
                'transcript': transcriptions,
                'count': len(transcriptions) if transcriptions else 0
            }
        })
    except Exception as e:
        logger.error(f"Error getting transcript: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Server error occurred',
            'error': str(e)
        }), 500

@app.route('/api/v1/minutes/generate', methods=['POST'])
def generate_minutes_api():
    """
    从转录文本生成会议纪要
    Request Body:
    {
        "room_id": "meeting_room_001",
        "transcript": "..."  # 可选，如果提供则使用此转录，否则从文件读取
    }
    """
    try:
        data = request.get_json()
        room_id = data.get('room_id')
        transcript = data.get('transcript', None)

        if not room_id:
            return jsonify({
                'success': False,
                'message': 'Missing room_id',
                'code': 400
            }), 400

        logger.info(f"Generating meeting minutes for room {room_id}")

        if transcript:
            # 使用提供的转录文本
            from config import Config
            import os
            room_dir = os.path.join(Config.BASE_AUDIO_DIR, room_id)
            os.makedirs(room_dir, exist_ok=True)

            transcript_file = os.path.join(room_dir, "transcript.txt")
            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write(transcript)

            minutes = generate_meeting_minutes(transcript, room_dir)
        else:
            # 从文件生成
            minutes = generate_minutes_from_transcript_file(room_id)

        if minutes:
            return jsonify({
                'success': True,
                'message': 'Meeting minutes generated successfully',
                'data': {
                    'room_id': room_id,
                    'minutes': minutes
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to generate meeting minutes',
                'error': 'No transcript available or generation failed'
            }), 500

    except Exception as e:
        logger.error(f"Error generating minutes: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Server error occurred',
            'error': str(e)
        }), 500

@app.route('/api/v1/minutes/get/<room_id>', methods=['GET'])
def get_minutes_api(room_id):
    """
    获取已生成的会议纪要
    """
    try:
        logger.info(f"Getting meeting minutes for room {room_id}")
        minutes = get_meeting_minutes(room_id)

        if minutes:
            return jsonify({
                'success': True,
                'data': {
                    'room_id': room_id,
                    'minutes': minutes
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No meeting minutes found for this room'
            }), 404

    except Exception as e:
        logger.error(f"Error getting minutes: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Server error occurred',
            'error': str(e)
        }), 500

@app.route('/api/v1/status', methods=['GET'])
def get_status():
    """
    获取服务状态
    """
    global is_running
    return jsonify({
        'asr_status': {
            'is_running': is_running,
            'active_rooms': list(monitoring_threads.keys())
        },
        'service_info': {
            'asr_model': 'Baidu ASR',
            'llm_model': 'Ollama deepseek-r1:7b',
            'base_audio_dir': Config.BASE_AUDIO_DIR
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('AI_SERVICES_PORT', 5001))
    host = os.environ.get('AI_SERVICES_HOST', '0.0.0.0')

    logger.info(f"Starting Conference AI Services API on {host}:{port}")
    app.run(host=host, port=port, debug=False)