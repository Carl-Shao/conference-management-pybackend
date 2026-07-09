from flask import Blueprint, request, jsonify
import time
from config import Config
from utils.db import query_one
import jwt

bp = Blueprint('auth', __name__)

def generate_token(user_id, role):
    payload = {
        'user_id': user_id,
        'role': role,
        'exp': time.time() + 3600  # 1 小时过期
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm='HS256')

@bp.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')  # 工号
    password = data.get('password')  # 默认 123456
    role = data.get('role')  # secretary 或 participant
    
    # 从数据库查询用户（工号）
    user = query_one(
        "SELECT * FROM meeting_employee WHERE employee_no = %s",
        (username,)
    )
    
    if not user:
        return jsonify({'code': 401, 'message': '用户名不存在'}), 401
    
    # 验证密码（默认都是 123456）
    if password != '123456':
        return jsonify({'code': 401, 'message': '密码错误'}), 401
    
    # 验证角色
    if user['role'] != role:
        return jsonify({'code': 403, 'message': '角色权限错误'}), 403
    
    # 生成 token
    token = generate_token(user['employee_no'], user['role'])
    
    return jsonify({
        'code': 200,
        'message': '登录成功',
        'data': {
            'token': token,
            'user': {
                'id': user['employee_no'],
                'name': user['employee_name'],
                'username': user['employee_no'],
                'role': user['role'],
                'department': user.get('department', '')
            }
        }
    })

@bp.route('/logout', methods=['POST'])
def logout():
    # 简单的登出，实际项目中可能需要处理token黑名单
    return jsonify({'code': 200, 'message': '登出成功'})

@bp.route('/check', methods=['GET'])
def check():
    # 验证 token
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'code': 401, 'message': '未登录'}), 401
    
    try:
        token = token.split(' ')[1]
        payload = jwt.decode(token, Config.SECRET_KEY, algorithms=['HS256'])
        
        # 从数据库查询用户
        user = query_one(
            "SELECT * FROM meeting_employee WHERE employee_no = %s",
            (payload['user_id'],)
        )
        
        if not user:
            return jsonify({'code': 401, 'message': '用户不存在'}), 401
        
        return jsonify({
            'code': 200,
            'data': {
                'user': {
                    'id': user['employee_no'],
                    'name': user['employee_name'],
                    'username': user['employee_no'],
                    'role': user['role'],
                    'department': user.get('department', '')
                }
            }
        })
    except Exception as e:
        return jsonify({'code': 401, 'message': 'token 无效'}), 401
