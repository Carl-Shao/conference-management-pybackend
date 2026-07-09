from flask import Blueprint, jsonify
from data.users import users

bp = Blueprint('user', __name__)

@bp.route('/', methods=['GET'])
def get_users():
    # 返回用户列表，去除密码字段
    users_without_password = []
    for user in users:
        user_data = {
            'id': user['id'],
            'name': user['name'],
            'username': user['username'],
            'role': user['role']
        }
        users_without_password.append(user_data)
    
    return jsonify({
        'code': 200,
        'data': users_without_password
    })

@bp.route('/<user_id>', methods=['GET'])
def get_user(user_id):
    user = next((u for u in users if u['id'] == user_id), None)
    if not user:
        return jsonify({'code': 404, 'message': '用户不存在'}), 404
    
    return jsonify({
        'code': 200,
        'data': {
            'id': user['id'],
            'name': user['name'],
            'username': user['username'],
            'role': user['role']
        }
    })
