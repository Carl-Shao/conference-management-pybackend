from flask import Flask, request, jsonify
from funasr import AutoModel

app = Flask("FunASR-Service")

print("正在加载FunASR模型...")
model = AutoModel(
    model = "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    vad_model = "fsmn-vad",
    device = "cuda",
    diable_update=True
)
print("FunASR模型加载完成")

@app.route("/v1/audio/transcriptions", methods=["POST"])
def transcribe():
    if "file" not in request.files:
        return jsonify({"error":"请求中是不包含文件"}), 400
    
    file = request.files["file"]
    audio_bytes = file.read()
    res = model.generate(input=audio_bytes)
    text_result = res[0].get("text","") if res else ""
    return jsonify({"text":text_result})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8899, threaded=True)