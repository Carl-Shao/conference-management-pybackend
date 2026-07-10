"""
ai_api_service.py
==================
统一对外的AI服务HTTP接口层，供Java(RuoYi)通过HTTP调用。
 
整合了：
- audio_service.py  录制音频（含MQ通知ASR）
- video_service.py  录制视频
- asr_service.py    本地语音识别（RabbitMQ消费者）
- minutes_service.py 会议纪要生成（本地Ollama）
 
设计原则：
- 离线内网环境，不依赖外部服务，只依赖内网的RabbitMQ和本地Ollama
- 返回格式统一采用 {"code":200,"msg":"...","data":...}，贴近RuoYi前端AjaxResult习惯
- 所有耗时操作（ASR识别、纪要生成）都是同步阻塞调用，Java侧请设置足够的HTTP超时时间，
  或者改为轮询 /api/meeting/{room_id}/minutes 接口获取结果（见下方"异步生成纪要"说明）
"""

from flask import Flask, request, jsonify
import traceback
from services.audio_service import audio_service
from services.video_service import video_service
from services.asr_service import asr_service
from services.minutes_service import minutes_service
from config import Config

app = Flask(__name__)


# ==================== 统一响应格式 ====================
 
def ok(data=None, msg="操作成功"):
    return jsonify({"code": 200, "msg": msg, "data": data})
 
 
def fail(msg="操作失败", code=500, data=None):
    return jsonify({"code": code, "msg": msg, "data": data})

# ==================== 会议录制：开始 ====================
 
@app.route("/api/meeting/start", methods=["POST"])
def start_meeting():
    """
    开始会议录制（同时启动音频+视频录制）
    请求体: {"roomId": "xxx", "rtspUrl": "rtsp://..."}
    """
    body = request.get_json(force=True, silent=True) or {}
    room_id = body.get("roomId")
    rtsp_url = body.get("rtspUrl")
 
    if not room_id or not rtsp_url:
        return fail("roomId 和 rtspUrl 不能为空", code=400)
 
    try:
        audio_ok, audio_path = audio_service.start_audio_recording(room_id, rtsp_url)
        video_ok, video_path = video_service.start_video_recording(room_id, rtsp_url)
 
        if not audio_ok or not video_ok:
            return fail(
                f"录制启动部分失败：audio={audio_ok}, video={video_ok}",
                code=500,
                data={"audioPath": audio_path, "videoPath": video_path},
            )
 
        return ok({
            "roomId": room_id,
            "audioPath": audio_path,
            "videoPath": video_path,
        }, msg="会议录制已开始")
 
    except Exception as e:
        traceback.print_exc()
        return fail(f"启动会议录制异常：{e}")
 
 
# ==================== 会议录制：结束 ====================
 
@app.route("/api/meeting/stop", methods=["POST"])
def stop_meeting():
    """
    结束会议录制（同时停止音频+视频录制）
    音频停止后会自动发布MQ消息，触发ASR异步识别，接口本身不等待识别完成
    请求体: {"roomId": "xxx"}
    """
    body = request.get_json(force=True, silent=True) or {}
    room_id = body.get("roomId")
 
    if not room_id:
        return fail("roomId 不能为空", code=400)
 
    try:
        # 停止前先拿到路径（此时文件仍在写入中，但路径是确定的）
        audio_path = audio_service.get_audio_recording_path(room_id)
        video_path = video_service.get_video_recording_path(room_id)
 
        audio_stopped = audio_service.stop_audio_recording(room_id, audio_path)
        video_stopped = video_service.stop_video_recording(room_id)
 
        return ok({
            "roomId": room_id,
            "audioPath": audio_path,
            "videoPath": video_path,
            "audioStopped": audio_stopped,
            "videoStopped": video_stopped,
        }, msg="会议录制已结束，语音识别正在后台异步处理")
 
    except Exception as e:
        traceback.print_exc()
        return fail(f"停止会议录制异常：{e}")
 
 
# ==================== 获取转录文本 ====================
 
@app.route("/api/meeting/<room_id>/transcript", methods=["GET"])
def get_transcript(room_id):
    """
    获取会议转录文本（ASR是异步的，可能还没处理完，建议轮询此接口）
    """
    try:
        transcript = asr_service.get_transcript(room_id)
        return ok({"roomId": room_id, "transcript": transcript})
    except Exception as e:
        traceback.print_exc()
        return fail(f"获取转录文本异常：{e}")
 
 
# ==================== 生成会议纪要 ====================
 
@app.route("/api/meeting/<room_id>/minutes/generate", methods=["POST"])
def generate_minutes(room_id):
    """
    提交会议纪要生成任务（异步，立即返回，不等待Ollama处理完成）
    真正的生成结果通过 GET /api/meeting/{room_id}/minutes/status 轮询获取状态，
    状态变为 completed 后再调 GET /api/meeting/{room_id}/minutes 拿最终内容
    """
    try:
        submitted = minutes_service.request_minutes_generation(room_id)
        if not submitted:
            return fail("提交纪要生成任务失败，请检查转录文件是否存在", code=400)
        return ok({"roomId": room_id, "status": "pending"}, msg="纪要生成任务已提交，正在后台处理")
    except Exception as e:
        traceback.print_exc()
        return fail(f"提交纪要生成任务异常：{e}")
 
 
@app.route("/api/meeting/<room_id>/minutes/status", methods=["GET"])
def get_minutes_status(room_id):
    """
    查询会议纪要生成状态：pending / processing / completed / failed / not_found
    """
    try:
        status = minutes_service.get_minutes_status(room_id)
        return ok({"roomId": room_id, **status})
    except Exception as e:
        traceback.print_exc()
        return fail(f"获取纪要生成状态异常：{e}")
 
 
# ==================== 获取会议纪要 ====================
 
@app.route("/api/meeting/<room_id>/minutes", methods=["GET"])
def get_minutes(room_id):
    """
    获取已生成的会议纪要（如果还没生成过，返回空字符串）
    """
    try:
        minutes = minutes_service.get_meeting_minutes(room_id)
        return ok({"roomId": room_id, "minutes": minutes})
    except Exception as e:
        traceback.print_exc()
        return fail(f"获取会议纪要异常：{e}")
 
 
# ==================== 健康检查 ====================
 
@app.route("/api/health", methods=["GET"])
def health():
    alive_asr_workers = [p.name for p in asr_service._worker_processes if p.is_alive()]
    alive_minutes_workers = [t.name for t in minutes_service._worker_threads if t.is_alive()]
    return ok({
        "asrWorkerCount": len(alive_asr_workers),
        "asrWorkers": alive_asr_workers,
        "minutesWorkerCount": len(alive_minutes_workers),
        "minutesWorkers": alive_minutes_workers,
        "recordingRooms": {
            "audio": list(audio_service.audio_recording_processes.keys()),
            "video": list(video_service.video_recording_processes.keys()),
        },
    }, msg="service is up")
 
 
# ==================== 服务启动 ====================
 
def create_app():
    """
    应用初始化：
    - 启动ASR服务的多进程worker池（每个worker独立进程、独立模型实例）
    - 启动会议纪要生成的多线程worker池（共用Ollama服务端，线程级并发即可）
    """
    asr_service.start_asr_service()
    minutes_service.start_minutes_service()
    return app
 
 
if __name__ == "__main__":
    application = create_app()
    # 离线内网环境下，建议生产部署时换成 waitress 或 gunicorn，而不是Flask自带的开发服务器
    application.run(
        host=getattr(Config, "API_HOST", "0.0.0.0"),
        port=getattr(Config, "API_PORT", 5000),
        threaded=True,
    )
 