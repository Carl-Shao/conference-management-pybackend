from flask import Blueprint, jsonify, request
import json
import os
import time
from config import Config
from services.rtsp_service import (
    start_rtsp_audio_recording,
    monitor_and_transcribe,
    stop_audio_processing,
    get_transcription
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

bp = Blueprint('transcript', __name__)

@bp.route('/<meeting_id>', methods=['GET'])
def get_transcript(meeting_id):
    # 模拟获取会议转录
    transcript_file = os.path.join(Config.TRANSCRIPT_FOLDER, f'meeting_{meeting_id}.json')

    if os.path.exists(transcript_file):
        with open(transcript_file, 'r', encoding='utf-8') as f:
            transcript = json.load(f)
        return jsonify({
            'code': 200,
            'data': transcript
        })
    else:
        # 返回模拟数据
        return jsonify({
            'code': 200,
            'data': {
                'meetingId': meeting_id,
                'transcript': [
                    {
                        'time': '10:00:00',
                        'speaker': '张三',
                        'content': '大家好，今天我们来讨论新产品的需求'
                    },
                    {
                        'time': '10:01:30',
                        'speaker': '李四',
                        'content': '我认为我们应该优先考虑用户体验'
                    },
                    {
                        'time': '10:03:20',
                        'speaker': '王五',
                        'content': '技术实现上可能会有一些挑战'
                    }
                ]
            }
        })

@bp.route('/realtime/<room_id>', methods=['GET'])
def get_realtime_transcript(room_id):
    # 确保 room_id 是字符串类型
    room_id_str = str(room_id)

    # 获取实时转录结果（从文件读取）
    transcriptions = get_transcription(room_id_str)

    print(f"📊 请求实时转录 - room_id: {room_id_str}")
    print(f"   获取到的转录数量：{len(transcriptions)}")
    if transcriptions:
        print(f"   转录内容：{transcriptions}")

    # 构建转录数据格式
    transcript_data = []
    for i, content in enumerate(transcriptions):
        transcript_data.append({
            'id': i + 1,
            'speaker': '发言人',
            'content': content,
            'time': time.strftime('%H:%M:%S')
        })

    return jsonify({
        'code': 200,
        'data': {
            'transcript': transcript_data
        }
    })

@bp.route('/start-recording', methods=['POST'])
def start_recording_endpoint():
    """
    启动RTSP音频录制
    参数：
    - rtsp_url: RTSP流地址
    - room_id: 会议室ID
    """
    try:
        data = request.get_json()
        rtsp_url = data.get('rtsp_url')
        room_id = data.get('room_id')

        if not rtsp_url or not room_id:
            return jsonify({
                'code': 400,
                'message': 'Missing rtsp_url or room_id'
            }), 400

        success = start_rtsp_audio_recording(rtsp_url, room_id)

        if success:
            # 在后台启动监听和转录
            import threading
            thread = threading.Thread(target=monitor_and_transcribe, args=(room_id,))
            thread.daemon = True
            thread.start()

            return jsonify({
                'code': 200,
                'message': 'Audio recording started successfully',
                'data': {
                    'room_id': room_id,
                    'rtsp_url': rtsp_url
                }
            })
        else:
            return jsonify({
                'code': 500,
                'message': 'Failed to start audio recording'
            }), 500

    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'Server error: {str(e)}'
        }), 500

@bp.route('/start-full-recording', methods=['POST'])
def start_full_recording_endpoint():
    """
    启动完整RTSP音频录制
    参数：
    - rtsp_url: RTSP流地址
    - room_id: 会议室ID
    """
    try:
        data = request.get_json()
        rtsp_url = data.get('rtsp_url')
        room_id = data.get('room_id')

        if not rtsp_url or not room_id:
            return jsonify({
                'code': 400,
                'message': 'Missing rtsp_url or room_id'
            }), 400

        success = start_recording(room_id, rtsp_url)

        if success:
            return jsonify({
                'code': 200,
                'message': 'Full audio recording started successfully',
                'data': {
                    'room_id': room_id,
                    'rtsp_url': rtsp_url
                }
            })
        else:
            return jsonify({
                'code': 500,
                'message': 'Failed to start full audio recording'
            }), 500

    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'Server error: {str(e)}'
        }), 500

@bp.route('/stop-recording', methods=['POST'])
def stop_recording_endpoint():
    """
    停止音频录制
    """
    try:
        stop_audio_processing()
        return jsonify({
            'code': 200,
            'message': 'Audio processing stopped successfully'
        })
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'Server error: {str(e)}'
        }), 500

@bp.route('/stop-full-recording', methods=['POST'])
def stop_full_recording_endpoint():
    """
    停止完整音频录制
    """
    try:
        success = stop_recording()
        if success:
            return jsonify({
                'code': 200,
                'message': 'Full audio recording stopped successfully'
            })
        else:
            return jsonify({
                'code': 400,
                'message': 'No active full recording to stop'
            }), 400
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'Server error: {str(e)}'
        }), 500

@bp.route('/recording-path/<room_id>', methods=['GET'])
def get_recording_path_endpoint(room_id):
    """
    获取完整录音文件路径
    """
    try:
        recording_path = get_recording_path(room_id)

        if recording_path:
            return jsonify({
                'code': 200,
                'data': {
                    'room_id': room_id,
                    'recording_path': recording_path
                }
            })
        else:
            return jsonify({
                'code': 404,
                'message': 'No recording file found for this room'
            }), 404
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'Server error: {str(e)}'
        }), 500

@bp.route('/generate-minutes/<room_id>', methods=['POST'])
def generate_minutes_endpoint(room_id):
    """
    从转录文件生成会议纪要
    """
    try:
        minutes = generate_minutes_from_transcript_file(room_id)
        if minutes:
            return jsonify({
                'code': 200,
                'message': 'Meeting minutes generated successfully',
                'data': {
                    'room_id': room_id,
                    'minutes': minutes
                }
            })
        else:
            return jsonify({
                'code': 500,
                'message': 'Failed to generate meeting minutes'
            }), 500
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'Server error: {str(e)}'
        }), 500

@bp.route('/minutes/<room_id>', methods=['GET'])
def get_minutes(room_id):
    """
    获取会议纪要
    """
    try:
        minutes = get_meeting_minutes(room_id)
        if minutes:
            return jsonify({
                'code': 200,
                'data': {
                    'room_id': room_id,
                    'minutes': minutes
                }
            })
        else:
            return jsonify({
                'code': 404,
                'message': 'No meeting minutes found for this room'
            }), 404
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'Server error: {str(e)}'
        }), 500
