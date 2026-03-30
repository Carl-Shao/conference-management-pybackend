from flask import Blueprint, jsonify, request
import jwt
import threading
from config import Config
from utils.db import query_one, query_list, execute
from services.rtsp_service import start_rtsp_audio_recording, monitor_and_transcribe, stop_audio_processing
from services.minutes_service import generate_minutes_from_transcript_file
from services.recording_service import start_recording, stop_recording, get_recording_path
import json
from datetime import date, timedelta

bp = Blueprint('meeting', __name__)

def get_current_user():
    """从请求中获取当前登录用户"""
    token = request.headers.get('Authorization')
    if not token:
        return None
    
    try:
        token = token.split(' ')[1]
        payload = jwt.decode(token, Config.SECRET_KEY, algorithms=['HS256'])
        user = query_one(
            "SELECT employee_no, employee_name, role, department FROM meeting_employee WHERE employee_no = %s",
            (payload['user_id'],)
        )
        return user
    except Exception as e:
        return None

def convert_meeting_row(row):
    """将数据库查询结果转换为前端需要的格式"""
    if not row:
        return None
    
    # 解析 JSON 格式的参会人员
    participant_nos = json.loads(row['participant_nos']) if row['participant_nos'] else []
    
    # 转换日期和时间
    meeting_date = row['meeting_date']
    if isinstance(meeting_date, date):
        meeting_date = meeting_date.strftime('%Y-%m-%d')
    
    start_time = row['start_time']
    if isinstance(start_time, timedelta):
        total_seconds = int(start_time.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        start_time = f"{hours:02d}:{minutes:02d}"
    
    end_time = row['end_time']
    if isinstance(end_time, timedelta):
        total_seconds = int(end_time.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        end_time = f"{hours:02d}:{minutes:02d}"
    
    return {
        'id': row['id'],
        'title': row['title'],
        'roomId': row['room_id'],
        'date': meeting_date,
        'startTime': start_time,
        'endTime': end_time,
        'participants': participant_nos,
        'organizer': row['organizer_no'],
        'status': row['status'],
        'description': row['description'] or '',
        'createdAt': row['create_time'].strftime('%Y-%m-%d %H:%M:%S') if row['create_time'] else ''
    }

@bp.route('/', methods=['GET'])
def get_meetings():
    # 获取用户 ID 参数
    user_id = request.args.get('userId')
    
    # 如果提供了用户 ID，只返回用户参与的未完成的会议（scheduled 或 active）
    if user_id:
        # 查询用户参与的未完成的会议
        meetings_data = query_list("""
            SELECT * FROM meeting 
            WHERE (organizer_no = %s OR JSON_CONTAINS(participant_nos, %s))
            AND status IN ('scheduled', 'active')
            ORDER BY meeting_date DESC, start_time DESC
        """, (user_id, json.dumps(user_id)))
        
        user_meetings = [convert_meeting_row(m) for m in meetings_data]
        return jsonify({
            'code': 200,
            'data': user_meetings
        })
    
    # 否则返回所有未完成的会议
    meetings_data = query_list("""
        SELECT * FROM meeting 
        WHERE status IN ('scheduled', 'active')
        ORDER BY meeting_date DESC, start_time DESC
    """)
    all_meetings = [convert_meeting_row(m) for m in meetings_data]
    return jsonify({
        'code': 200,
        'data': all_meetings
    })

@bp.route('/', methods=['POST'])
def create_meeting():
    data = request.json
    
    # 验证必填字段
    required_fields = ['title', 'roomId', 'date', 'startTime', 'endTime', 'participants']
    for field in required_fields:
        if field not in data:
            return jsonify({'code': 400, 'message': f'缺少字段：{field}'}), 400
    
    # 获取当前登录用户
    current_user = get_current_user()
    organizer_no = current_user['employee_no'] if current_user else 'admin'
    
    # 创建会议，确保组织者也在参会人员列表中
    participants = data['participants'].copy()
    if organizer_no not in participants:
        participants.append(organizer_no)
    
    # 将参会人员列表转换为 JSON 字符串
    participants_json = json.dumps(participants)
    
    # 保存到数据库
    meeting_id = execute("""
        INSERT INTO meeting (title, room_id, meeting_date, start_time, end_time, organizer_no, participant_nos, description, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'scheduled')
    """, (
        data['title'],
        data['roomId'],
        data['date'],
        data['startTime'],
        data['endTime'],
        organizer_no,
        participants_json,
        data.get('description', '')
    ))
    
    # 查询刚创建的会议
    meeting_data = query_one("SELECT * FROM meeting WHERE id = %s", (meeting_id,))
    
    return jsonify({
        'code': 200,
        'message': '会议创建成功',
        'data': convert_meeting_row(meeting_data)
    })

@bp.route('/<meeting_id>', methods=['GET'])
def get_meeting(meeting_id):
    import time
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'='*60}")
    print(f"[{timestamp}] 🔍 获取会议详情 - meeting_id: {meeting_id}")
    print(f"{'='*60}")
    
    # 1. 查询会议信息
    print(f"[{timestamp}] 步骤 1: 查询会议信息")
    meeting_data = query_one("SELECT * FROM meeting WHERE id = %s", (int(meeting_id),))
    if not meeting_data:
        print(f"[{timestamp}] ❌ 会议不存在")
        return jsonify({'code': 404, 'message': '会议不存在'}), 404
    
    print(f"[{timestamp}] ✅ 会议信息: ID={meeting_data['id']}, Title={meeting_data['title']}, Status={meeting_data['status']}, RoomID={meeting_data['room_id']}")
    
    # 2. 转换会议数据
    print(f"[{timestamp}] 步骤 2: 转换会议数据")
    meeting = convert_meeting_row(meeting_data)
    print(f"[{timestamp}] ✅ 转换后会议数据: {meeting}")
    
    # 3. 如果会议已结束，生成录音和会议纪要信息
    if meeting_data['status'] == 'completed':
        room_id = str(meeting_data['room_id'])
        print(f"[{timestamp}] 步骤 3: 处理已结束会议 (room_id={room_id})")
        
        # 3.1 获取会议纪要（直接读取已生成的文件）
        print(f"[{timestamp}] 步骤 3.1: 获取会议纪要")
        try:
            from services.minutes_service import get_meeting_minutes
            minutes = get_meeting_minutes(room_id)
            meeting['minutes'] = minutes
            print(f"[{timestamp}] ✅ 会议纪要读取成功: {minutes[:100]}..." if minutes else "[{timestamp}] ⚠️  会议纪要为空")
        except Exception as e:
            print(f"[{timestamp}] ❌ 获取会议纪要失败: {e}")
            meeting['minutes'] = ''
        
        # 3.2 获取录音文件路径
        print(f"[{timestamp}] 步骤 3.2: 获取录音文件路径")
        try:
            recording_path = get_recording_path(room_id)
            print(f"[{timestamp}] 录音文件路径: {recording_path}")
            if recording_path:
                # 设置录音文件的 API 访问路径
                meeting['recordingUrl'] = f'/api/recordings/{room_id}/recording.wav'
                print(f"[{timestamp}] ✅ 录音文件URL: {meeting['recordingUrl']}")
            else:
                meeting['recordingUrl'] = ''
                print(f"[{timestamp}] ⚠️  录音文件不存在")
        except Exception as e:
            print(f"[{timestamp}] ❌ 获取录音文件路径失败: {e}")
            meeting['recordingUrl'] = ''
    
    # 4. 返回响应
    print(f"[{timestamp}] 步骤 4: 返回响应")
    print(f"[{timestamp}] 最终返回数据: {meeting}")
    print(f"{'='*60}\n")
    
    return jsonify({
        'code': 200,
        'data': meeting
    })

@bp.route('/<meeting_id>/start', methods=['POST'])
def start_meeting(meeting_id):
    import time
    start_time = time.time()
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"\n{'='*60}")
    print(f"[{timestamp}] 🚀 开始会议请求 - meeting_id: {meeting_id}")
    print(f"{'='*60}")
    
    # 1. 查询会议信息
    print(f"[{timestamp}] 🔍 步骤 1: 查询会议信息")
    meeting_data = query_one("SELECT * FROM meeting WHERE id = %s", (int(meeting_id),))
    if not meeting_data:
        print(f"[{timestamp}] ❌ 会议不存在")
        return jsonify({'code': 404, 'message': '会议不存在'}), 404
    
    print(f"[{timestamp}] ✅ 会议信息: ID={meeting_data['id']}, Title={meeting_data['title']}, Status={meeting_data['status']}, RoomID={meeting_data['room_id']}")
    
    # 2. 获取会议室信息
    print(f"[{timestamp}] 🔍 步骤 2: 查询会议室信息 (room_id={meeting_data['room_id']})")
    room = query_one("SELECT * FROM meeting_room WHERE id = %s", (meeting_data['room_id'],))
    if not room:
        print(f"[{timestamp}] ❌ 会议室不存在")
        return jsonify({'code': 404, 'message': '会议室不存在'}), 404
    
    print(f"[{timestamp}] ✅ 会议室信息: ID={room['id']}, Name={room['room_name']}, Status={room['status']}")
    
    # 3. 获取 RTSP URL
    print(f"[{timestamp}] 🔍 步骤 3: 获取 RTSP URL")
    rtsp_url = room['rtsp_url']
    if not rtsp_url:
        print(f"[{timestamp}] ❌ 会议室未配置 RTSP 地址")
        return jsonify({'code': 500, 'message': '该会议室未配置 RTSP 地址'}), 500
    
    print(f"[{timestamp}] ✅ RTSP URL: {rtsp_url}")
    
    # 4. 启动音频采集
    print(f"[{timestamp}] 🎙️  步骤 4: 启动音频采集")
    room_id_str = str(meeting_data['room_id'])
    print(f"[{timestamp}] 会议室 ID: {room_id_str}")
    
    try:
        if start_rtsp_audio_recording(rtsp_url, room_id_str):
            print(f"[{timestamp}] ✅ 音频采集启动成功")
            
            # 5. 启动完整录音
            print(f"[{timestamp}] 📹 步骤 5: 启动完整录音")
            start_recording(room_id_str, rtsp_url)
            print(f"[{timestamp}] ✅ 完整录音启动成功")
            
            # 6. 启动转写监控线程
            print(f"[{timestamp}] 📝 步骤 6: 启动转写监控线程")
            transcribe_thread = threading.Thread(
                target=monitor_and_transcribe, 
                args=(room_id_str,)
            )
            transcribe_thread.daemon = True
            transcribe_thread.start()
            print(f"[{timestamp}] ✅ 转写线程启动成功 (Thread ID: {transcribe_thread.ident})")
            
            # 7. 更新会议状态为 active
            print(f"[{timestamp}] 📋 步骤 7: 更新会议状态为 active")
            execute("UPDATE meeting SET status = 'active' WHERE id = %s", (int(meeting_id),))
            print(f"[{timestamp}] ✅ 会议状态更新成功")
            
            # 8. 更新会议室状态
            print(f"[{timestamp}] 📋 步骤 8: 更新会议室状态为 occupied")
            execute("UPDATE meeting_room SET status = 'occupied' WHERE id = %s", 
                   (meeting_data['room_id'],))
            print(f"[{timestamp}] ✅ 会议室状态更新成功")
            
            # 9. 返回更新后的会议信息
            print(f"[{timestamp}] 📤 步骤 9: 返回响应")
            meeting_data['status'] = 'active'
            end_time = time.time()
            print(f"[{timestamp}] 🎉 会议开始流程完成，耗时: {end_time - start_time:.2f}秒")
            print(f"{'='*60}\n")
            
            return jsonify({
                'code': 200,
                'message': '会议已开始，音频采集和录音已启动',
                'data': convert_meeting_row(meeting_data)
            })
        else:
            print(f"[{timestamp}] ❌ 音频采集启动失败")
            end_time = time.time()
            print(f"[{timestamp}] ⚠️  会议开始流程失败，耗时: {end_time - start_time:.2f}秒")
            print(f"{'='*60}\n")
            
            return jsonify({
                'code': 500,
                'message': '会议已开始，但音频采集启动失败',
                'data': convert_meeting_row(meeting_data)
            }), 500
    except Exception as e:
        print(f"[{timestamp}] 💥 开始会议过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        end_time = time.time()
        print(f"[{timestamp}] ⚠️  会议开始流程异常，耗时: {end_time - start_time:.2f}秒")
        print(f"{'='*60}\n")
        
        return jsonify({
            'code': 500,
            'message': f'会议开始失败: {str(e)}',
            'data': convert_meeting_row(meeting_data)
        }), 500

@bp.route('/<meeting_id>/end', methods=['POST'])
def end_meeting(meeting_id):
    import time
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'='*60}")
    print(f"[{timestamp}] 🛑 结束会议请求 - meeting_id: {meeting_id}")
    print(f"{'='*60}")
    
    # 1. 查询会议信息
    print(f"[{timestamp}] 步骤 1: 查询会议信息")
    meeting_data = query_one("SELECT * FROM meeting WHERE id = %s", (int(meeting_id),))
    if not meeting_data:
        print(f"[{timestamp}] ❌ 会议不存在")
        return jsonify({'code': 404, 'message': '会议不存在'}), 404
    
    print(f"[{timestamp}] ✅ 会议信息: ID={meeting_data['id']}, Title={meeting_data['title']}, RoomID={meeting_data['room_id']}")
    
    # 2. 停止音频处理和录音
    print(f"[{timestamp}] 步骤 2: 停止音频处理和录音")
    stop_audio_processing()
    stop_recording()
    print(f"[{timestamp}] ✅ 音频处理和录音已停止")
    
    # 3. 更新会议状态为 completed
    print(f"[{timestamp}] 步骤 3: 更新会议状态为 completed")
    execute("UPDATE meeting SET status = 'completed' WHERE id = %s", (int(meeting_id),))
    print(f"[{timestamp}] ✅ 会议状态更新成功")
    
    # 4. 生成会议纪要
    print(f"[{timestamp}] 步骤 4: 生成会议纪要")
    room_id = str(meeting_data['room_id'])
    minutes = generate_minutes_from_transcript_file(room_id)
    print(f"[{timestamp}] ✅ 会议纪要生成成功: {minutes[:100]}..." if minutes else "[{timestamp}] ⚠️  会议纪要为空")
    
    # 5. 获取录音文件路径
    print(f"[{timestamp}] 步骤 5: 获取录音文件路径")
    recording_path = get_recording_path(room_id)
    if recording_path:
        # 设置录音文件的 API 访问路径
        recording_url = f'/api/recordings/{room_id}/recording.wav'
        print(f"[{timestamp}] ✅ 录音文件URL: {recording_url}")
    else:
        recording_url = ''
        print(f"[{timestamp}] ⚠️  录音文件不存在")
    
    # 6. 存入会议资源到 meeting_resource 表
    print(f"[{timestamp}] 步骤 6: 存入会议资源到 meeting_resource 表")
    try:
        # 读取transcript.txt文件内容
        import os
        from config import Config
        transcript_path = os.path.join(Config.BASE_AUDIO_DIR, room_id, "transcript.txt")
        full_transcript = ""
        if os.path.exists(transcript_path):
            try:
                with open(transcript_path, "r", encoding="utf-8") as f:
                    full_transcript = f.read()
                print(f"[{timestamp}] ✅ 成功读取transcript.txt文件")
            except Exception as e:
                print(f"[{timestamp}] ⚠️  读取transcript.txt文件失败: {e}")
        else:
            print(f"[{timestamp}] ⚠️  transcript.txt文件不存在: {transcript_path}")
        
        # 插入会议资源记录
        resource_id = execute("""
            INSERT INTO meeting_resource (meeting_id, meeting_title, full_transcript, summary_content, recording_path, create_time, update_time)
            VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
        """, (
            int(meeting_id),
            meeting_data['title'],
            full_transcript,
            minutes,
            recording_url
        ))
        print(f"[{timestamp}] ✅ 会议资源存入成功，资源ID: {resource_id}")
    except Exception as e:
        print(f"[{timestamp}] ❌ 存入会议资源失败: {e}")
    
    # 7. 更新会议室状态
    print(f"[{timestamp}] 步骤 7: 更新会议室状态为 available")
    execute("UPDATE meeting_room SET status = 'available' WHERE id = %s", 
           (meeting_data['room_id'],))
    print(f"[{timestamp}] ✅ 会议室状态更新成功")
    
    # 8. 返回更新后的会议信息
    print(f"[{timestamp}] 步骤 8: 返回响应")
    meeting_data['status'] = 'completed'
    meeting_data['minutes'] = minutes
    meeting_data['recordingUrl'] = recording_url
    
    print(f"[{timestamp}] 🎉 会议结束流程完成")
    print(f"{'='*60}\n")
    
    return jsonify({
        'code': 200,
        'message': '会议已结束，音频处理和录音已停止，会议纪要已生成，资源已存入数据库',
        'data': convert_meeting_row(meeting_data)
    })

@bp.route('/history', methods=['GET'])
def get_history_meetings():
    # 获取用户 ID 参数
    user_id = request.args.get('userId')
    
    # 如果提供了用户 ID，只返回用户参与的历史会议（包括组织者和参与者）
    if user_id:
        # 查询用户参与的已完成的会议
        meetings_data = query_list("""
            SELECT * FROM meeting 
            WHERE (organizer_no = %s OR JSON_CONTAINS(participant_nos, %s))
            AND status = 'completed'
            ORDER BY meeting_date DESC, start_time DESC
        """, (user_id, json.dumps(user_id)))
        
        user_meetings = [convert_meeting_row(m) for m in meetings_data]
        return jsonify({
            'code': 200,
            'data': user_meetings
        })
    
    # 否则返回所有历史会议
    meetings_data = query_list("SELECT * FROM meeting WHERE status = 'completed' ORDER BY meeting_date DESC, start_time DESC")
    history_meetings = [convert_meeting_row(m) for m in meetings_data]
    return jsonify({
        'code': 200,
        'data': history_meetings
    })

@bp.route('/<meeting_id>', methods=['DELETE'])
def delete_meeting(meeting_id):
    meeting_data = query_one("SELECT * FROM meeting WHERE id = %s", (int(meeting_id),))
    if not meeting_data:
        return jsonify({'code': 404, 'message': '会议不存在'}), 404
    
    # 不能删除进行中的会议
    if meeting_data['status'] == 'active':
        return jsonify({'code': 400, 'message': '不能删除进行中的会议'}), 400
    
    # 从数据库删除会议
    execute("DELETE FROM meeting WHERE id = %s", (int(meeting_id),))
    
    # 如果会议室状态是被该会议占用，恢复为可用
    execute("UPDATE meeting_room SET status = 'available' WHERE id = %s", 
           (meeting_data['room_id'],))
    
    return jsonify({
        'code': 200,
        'message': '会议删除成功'
    })