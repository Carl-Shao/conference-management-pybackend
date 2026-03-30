from flask import Flask, request, jsonify, send_from_directory
from config import Config
import os

app = Flask(__name__)
app.config.from_object(Config)

# 手动添加CORS头
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

# 注册路由
from routes import auth, meeting, user, room, transcript
app.register_blueprint(auth.bp, url_prefix='/api/auth')
app.register_blueprint(meeting.bp, url_prefix='/api/meetings')
app.register_blueprint(user.bp, url_prefix='/api/users')
app.register_blueprint(room.bp, url_prefix='/api/rooms')
app.register_blueprint(transcript.bp, url_prefix='/api/transcripts')

# 静态文件服务
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

# 录音文件服务
@app.route('/api/recordings/<room_id>/<filename>')
def send_recording(room_id, filename):
    recording_dir = os.path.join(Config.BASE_AUDIO_DIR, room_id)
    return send_from_directory(recording_dir, filename)

# 健康检查
@app.route('/api/health')
def health_check():
    return jsonify({'status': 'ok'})

# 404处理
@app.errorhandler(404)
def not_found(error):
    return jsonify({'code': 404, 'message': 'Not Found'}), 404

# 500处理
@app.errorhandler(500)
def internal_error(error):
    return jsonify({'code': 500, 'message': 'Internal Server Error'}), 500

if __name__ == '__main__':
    # 确保静态文件夹存在
    os.makedirs('static/audio', exist_ok=True)
    os.makedirs('static/transcripts', exist_ok=True)
    
    app.run(host='0.0.0.0', port=app.config['PORT'], debug=app.config['DEBUG'])
