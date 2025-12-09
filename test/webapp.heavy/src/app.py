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
frame_lock = threading.Lock()

latest_detections = None         # 直近の推論結果（ovms.detect()[0]）
latest_det_ts = 0.0              # その推論が完了した時刻
detection_lock = threading.Lock()

shutdown_event = threading.Event()

_raw_fps = float(getattr(load_env, "FPS", 30))
TARGET_FPS = _raw_fps if _raw_fps > 0 else 30.0
INFER_INTERVAL = 1.0 / TARGET_FPS

# 🔥 推論スレッド数（デフォルト1）
INFER_THREADS = int(getattr(load_env, "OVMS_INFER_THREADS", 1))

# 推論結果を「新鮮」とみなす時間（秒）
DETECTION_TTL = float(getattr(load_env, "DETECTION_TTL", 0.7))


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
        time.sleep(0.001)
    log.info("Exit capture loop")


# ========= 推論ループ（複数スレッド対応） =========
def inference_loop(worker_id: int, label_map):
    global latest_detections, latest_det_ts
    log.info(f"Start inference loop (worker={worker_id})")

    while not shutdown_event.is_set():
        with frame_lock:
            frame = latest_raw_frame

        if frame is None:
            time.sleep(0.001)
            continue

        start = time.perf_counter()
        try:
            det0 = ovms.detect(frame)[0]
            with detection_lock:
                latest_detections = det0
                latest_det_ts = time.time()
        except Exception as e:
            log.error(f"[worker={worker_id}] Inference failed: {e}")

        elapsed = time.perf_counter() - start
        spare = max(INFER_INTERVAL - elapsed, 0)
        if spare > 0:
            time.sleep(spare * 0.3)

    log.info(f"Exit inference loop (worker={worker_id})")


# ========= ストリーミング生成 =========
def _generate_stream(annotated: bool = False):
    boundary = b"--frame\r\n"

    while not shutdown_event.is_set():
        with frame_lock:
            frame = latest_raw_frame

        if frame is None:
            time.sleep(0.005)
            continue

        img = frame

        if annotated:
            now = time.time()
            with detection_lock:
                det = latest_detections
                det_ts = latest_det_ts

            if det is not None and (now - det_ts) <= DETECTION_TTL:
                try:
                    img = ovms.draw_results(det, img.copy(), label_map)
                except Exception as e:
                    log.error(f"draw_results failed: {e}")
                    img = frame
            else:
                img = frame

        ok, buf = cv2.imencode(".jpg", img)
        if not ok:
            continue

        payload = buf.tobytes()
        yield (
            boundary +
            b"Content-Type: image/jpeg\r\n\r\n" +
            payload +
            b"\r\n"
        )

        time.sleep(0.01)


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


# ========= Graceful Shutdown =========
def _signal_handler(signum, frame):
    log.info(f"Received signal {signum}. Graceful shutdown.")
    shutdown_event.set()
    try:
        camera.release()
    except Exception as e:
        log.warning(f"Error while releasing camera: {e}")
    sys.exit(0)


signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ========= エントリポイント =========
if __name__ == "__main__":
    with open("coco.yaml", "r") as f:
        config = yaml.safe_load(f)
    label_map = config["names"]
    
    # カメラ
    t_cap = threading.Thread(target=capture_loop, daemon=True)
    t_cap.start()

    # 🔥 複数推論ワーカースレッド起動
    for i in range(INFER_THREADS):
        threading.Thread(
            target=inference_loop,
            args=(i, label_map),
            daemon=True,
        ).start()

    app.run(host="0.0.0.0", port=int(load_env.PORT), threaded=True, use_reloader=False)
