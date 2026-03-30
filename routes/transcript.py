from flask import Blueprint, jsonify, request
import json
import os
import time
from config import Config
from services.rtsp_service import get_transcription

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
