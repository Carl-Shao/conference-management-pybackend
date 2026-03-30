from flask import Blueprint, jsonify, request
from data.rooms import rooms

bp = Blueprint('room', __name__)

@bp.route('/', methods=['GET'])
def get_rooms():
    return jsonify({
        'code': 200,
        'data': rooms
    })

@bp.route('/<room_id>', methods=['GET'])
def get_room(room_id):
    room = next((r for r in rooms if r['id'] == int(room_id)), None)
    if not room:
        return jsonify({'code': 404, 'message': '会议室不存在'}), 404
    
    return jsonify({
        'code': 200,
        'data': room
    })

@bp.route('/<room_id>/status', methods=['PUT'])
def update_room_status(room_id):
    room = next((r for r in rooms if r['id'] == int(room_id)), None)
    if not room:
        return jsonify({'code': 404, 'message': '会议室不存在'}), 404
    
    data = request.json
    status = data.get('status')
    if status not in ['available', 'occupied']:
        return jsonify({'code': 400, 'message': '无效的状态值'}), 400
    
    room['status'] = status
    if status == 'available':
        room['currentMeeting'] = None
    
    return jsonify({
        'code': 200,
        'message': '状态更新成功',
        'data': room
    })
