import load_env
import logging
import cv2
import yaml
import time
import threading
import signal
import sys

from flask import Flask, Response, abort, render_template

from camera import Camera
import ovms

# ========= ログ/環境 =========
load_env.read_val_from_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("edge-app")

app = Flask(__name__, static_folder="./templates/images")

# ========= グローバル状態 =========
camera = Camera()

latest_raw_frame = None          # 生フレーム
latest_encoded_frame = None      # 推論+描画済み JPEG バイト列
frame_lock = threading.Lock()

shutdown_event = threading.Event()

# 目標推論FPS（デフォルト30）
_raw_fps = float(getattr(load_env, "FPS", 30))
TARGET_FPS = _raw_fps if _raw_fps > 0 else 30.0
INFER_INTERVAL = 1.0 / TARGET_FPS


# ========= UI =========
@app.route("/")
def index():
    return render_template("stream.html")


@app.route("/predict")
def predict_page():
    return render_template("predict.html")


# ========= カメラループ =========
def capture_loop():
    global latest_raw_frame
    log.info("Start capture loop")
    while not shutdown_event.is_set():
        frame = camera.get_frame()
        if frame is not None:
            with frame_lock:
                latest_raw_frame = frame
        # カメラFPSに任せるが、イベントチェック用に僅かにsleep
        time.sleep(0.001)
    log.info("Exit capture loop")


# ========= 推論ループ =========
def inference_loop(label_map):
    global latest_encoded_frame
    log.info(f"Start inference loop (target {TARGET_FPS} FPS)")
    while not shutdown_event.is_set():
        with frame_lock:
            frame_ref = latest_raw_frame

        if frame_ref is None:
            time.sleep(0.005)
            continue

        try:
            detections = ovms.detect(frame_ref)[0]
            annotated = ovms.draw_results(detections, frame_ref.copy(), label_map)
        except Exception as e:
            log.error(f"Inference failed: {e}")
            annotated = frame_ref

        ok, buf = cv2.imencode(".jpg", annotated)
        if ok:
            latest_encoded_frame = buf.tobytes()

        time.sleep(INFER_INTERVAL)
    log.info("Exit inference loop")


# ========= ストリーミング生成 =========
def _generate_stream(annotated: bool = False):
    boundary = b"--frame\r\n"
    while not shutdown_event.is_set():
        if annotated:
            payload = latest_encoded_frame
            if payload is None:
                time.sleep(0.01)
                continue
        else:
            with frame_lock:
                frame = latest_raw_frame
            if frame is None:
                time.sleep(0.01)
                continue
            ok, buf = cv2.imencode(".jpg", frame)
            if not ok:
                continue
            payload = buf.tobytes()

        yield boundary + b"Content-Type: image/jpeg\r\n\r\n" + payload + b"\r\n"
        time.sleep(0.001)  # ストリームのレート（描画側負荷調整用）


@app.route("/video_feed")
def video_feed():
    return Response(
        _generate_stream(annotated=False),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/predict_feed")
def predict_feed():
    return Response(
        _generate_stream(annotated=True),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# ========= スナップショット =========
@app.route("/save_image")
def save_image():
    with frame_lock:
        frame = latest_raw_frame

    if frame is None:
        log.error("No frame available for snapshot")
        abort(500, description="no frame")

    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        log.error("Failed to encode snapshot frame")
        abort(500, description="encode error")

    return Response(buf.tobytes(), mimetype="image/jpeg")


# ========= Graceful Shutdown (Ctrl+C / SIGTERM) =========
def _signal_handler(signum, frame):
    log.info(f"Received signal {signum}. Graceful shutdown.")
    shutdown_event.set()
    try:
        camera.release()
    except Exception as e:
        log.warning(f"Error while releasing camera: {e}")
    # Flask dev server がブロックしていてもここでプロセス終了
    sys.exit(0)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ========= エントリポイント =========
if __name__ == "__main__":
    # ラベルマップは起動時に1回だけロード
    with open("coco.yaml", "r") as f:
        config = yaml.safe_load(f)
    label_map = config["names"]

    t_cap = threading.Thread(target=capture_loop, daemon=True)
    t_inf = threading.Thread(target=inference_loop, args=(label_map,), daemon=True)
    t_cap.start()
    t_inf.start()

    # Flask dev server / Ctrl+C で元コードと同じ感覚で終了できるように reloader OFF
    app.run(host="0.0.0.0", port=int(load_env.PORT), threaded=True, use_reloader=False)
