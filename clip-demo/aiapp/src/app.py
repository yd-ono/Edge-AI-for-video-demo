import logging
import cv2
import numpy as np
import os
import json
import glob
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from transformers import CLIPTokenizer
from ovmsclient import make_grpc_client
import concurrent.futures
import threading
import queue
from typing import List
import time
import paho.mqtt.client as mqtt
from PIL import Image, ImageDraw, ImageFont
import asyncio
import signal
import sys
from uvicorn import Config, Server
from prometheus_client import Gauge, Summary, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST

# ==== 環境変数設定 ====
MODEL_NAME = os.getenv("MODEL_NAME", "demo")
OVMS_HOST = os.getenv("OVMS_HOST", "192.168.3.130:32290")
LABELS = os.getenv("LABELS", "human,soldier").split(",")
CAMERA_SOURCE = 0 if os.getenv("CAMERA_SOURCE", "0") == "0" else os.getenv("CAMERA_SOURCE")
INFERENCE_BATCH_SIZE = int(os.getenv("INFERENCE_BATCH_SIZE", "4"))
FRAME_BUFFER_SIZE = int(os.getenv("FRAME_BUFFER_SIZE", "2"))
INFERENCE_INTERVAL = float(os.getenv("INFERENCE_INTERVAL", "0.1"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "clip/result")
MQTT_QOS = int(os.getenv("MQTT_QOS", "1"))
MQTT_RETAIN = True

logging.basicConfig(level=getattr(logging, LOG_LEVEL))
log = logging.getLogger("clip-app")

app = FastAPI(title="CLIP分類アプリ")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

registry = CollectorRegistry()
inference_fps = Gauge("inference_fps", "Current inference FPS", registry=registry)
mqtt_connected_metric = Gauge("mqtt_connected", "MQTT connected (1) or not (0)", registry=registry)
ovms_ready_metric = Gauge("ovms_ready", "OVMS client initialized (1) or not (0)", registry=registry)
inference_duration = Summary("inference_duration_seconds", "Time spent on inference", registry=registry)
frame_interval = Summary("frame_interval_seconds", "Interval between frame processing", registry=registry)

current_labels = LABELS.copy()
client = None
tokenizer = None
executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)
score_lock = threading.Lock()
latest_scores = np.zeros(len(current_labels))
frame_queue = queue.Queue(maxsize=FRAME_BUFFER_SIZE)
is_processing = False
mqtt_client = None
mqtt_connected = False
shutdown_event = threading.Event()

class Camera:
    def __init__(self, source):
        self.cap = cv2.VideoCapture(source)
        if not self.cap.isOpened():
            raise RuntimeError(f"カメラソース({source})を開けません")

    def read(self):
        ret, frame = self.cap.read()
        if not ret:
            raise RuntimeError("カメラからフレームを取得できません")
        return frame

    def release(self):
        if self.cap:
            self.cap.release()

# MQTT処理

def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    mqtt_connected = rc == 0
    log.info("MQTT接続" + ("成功" if mqtt_connected else f"失敗 rc={rc}"))

def on_disconnect(client, userdata, rc):
    global mqtt_connected
    mqtt_connected = False
    log.warning(f"MQTT切断（rc={rc}）")

def setup_mqtt():
    global mqtt_client
    try:
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()
        mqtt_client = client
    except Exception as e:
        log.warning(f"MQTT初期化失敗: {e}")

class LabelUpdate(BaseModel):
    labels: str

def initialize_model():
    global client, tokenizer
    for _ in range(5):
        try:
            log.info("OVMS接続中...")
            client = make_grpc_client(OVMS_HOST)
            tokenizer = CLIPTokenizer.from_pretrained("openai/clip-vit-base-patch32")
            return True
        except Exception as e:
            log.error(f"初期化失敗: {e}")
            time.sleep(2)
    return False

def tokenize_texts(texts: List[str]):
    try:
        encoded = tokenizer(texts, return_tensors="np", padding=True, truncation=True)
        return encoded["input_ids"], encoded["attention_mask"]
    except Exception as e:
        log.warning(f"トークナイズ失敗: {e}")
        fallback = tokenizer([""], return_tensors="np", padding=True, truncation=True)
        return fallback["input_ids"], fallback["attention_mask"]

def preprocess_image(frame):
    resized = cv2.resize(frame, (224, 224), interpolation=cv2.INTER_AREA)
    img = np.transpose(resized, (2, 0, 1))
    return np.expand_dims(img, axis=0).astype(np.float32) / 255.0

def infer_batch(frames, labels):
    if not client or not tokenizer or not labels:
        return [np.zeros(len(labels)) for _ in frames]
    try:
        imgs = np.vstack([preprocess_image(f) for f in frames])
        input_ids, attention_mask = tokenize_texts(labels)
        inputs = {"87": imgs, "input_ids": input_ids, "900": attention_mask}
        results = client.predict(inputs=inputs, model_name=MODEL_NAME)
        logits = np.array(results.get("logits_per_text", []))
        if logits.shape[0] == len(labels):
            logits = logits.T
        return [np.exp(l - np.max(l)) / np.sum(np.exp(l - np.max(l))) for l in logits]
    except Exception as e:
        log.error(f"推論エラー: {e}")
        return [np.zeros(len(labels)) for _ in frames]

def process_frames():
    global latest_scores, is_processing
    if is_processing:
        return
    is_processing = True
    try:
        frames = []
        while not frame_queue.empty() and len(frames) < INFERENCE_BATCH_SIZE:
            frames.append(frame_queue.get())
        if frames:
            scores_batch = infer_batch(frames, current_labels)
            if scores_batch:
                with score_lock:
                    latest_scores = scores_batch[0]
                    message = json.dumps({"labels": [
                        {"name": label, "score": round(float(score), 4)}
                        for label, score in zip(current_labels, latest_scores)
                    ]}, ensure_ascii=False)
                    if mqtt_client and mqtt_connected:
                        try:
                            mqtt_client.publish(MQTT_TOPIC, payload=message.encode('utf-8'), qos=MQTT_QOS, retain=MQTT_RETAIN)
                        except Exception as e:
                            log.warning(f"MQTT Publish失敗: {e}")
    finally:
        is_processing = False

def find_japanese_font():
    # 本語フォントの候補パス
    font_candidates = [
        "/Users/yono/Documents/work/Edge-AI-for-video-demo/clip-demo/aiapp/fonts/ipaexg.ttf"
    ]
    # 候補パスを順にチェック
    for path in font_candidates:
        if os.path.exists(path):
            return path
    # 最終手段：システム内のttfから日本語らしいものを探す
    fonts = glob.glob("/usr/share/fonts/**/*.[ot]tf", recursive=True)
    for f in fonts:
        if "noto" in f.lower() and ("cjk" in f.lower() or "jp" in f.lower()):
            return f
        if "ipa" in f.lower():
            return f
    return None

# スコアバー描画
def draw_score_bar(frame, scores, labels):
    h, w, _ = frame.shape
    # スコアバーの設定
    bar_height, spacing, margin, bar_width = 30, 10, 20, min(w // 2, 300)

    # OpenCV → Pillow 変換
    image_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(image_pil)

    font_path = find_japanese_font()
    if font_path:
        try:
            font = ImageFont.truetype(font_path, 24)
        except Exception as e:
            log.warning(f"フォント読み込み失敗: {e}")
            font = ImageFont.load_default()
    else:
        log.warning("日本語フォントが見つかりません。英語フォントで代用します。")
        font = ImageFont.load_default()

    # スコアバーの描画
    for i, (label, score) in enumerate(zip(labels, scores)):
        # スコアバーのY座標
        y = margin + i * (bar_height + spacing)
        # スコアバーの描画
        bar_len = int(min(score, 1.0) * bar_width)
        draw.rectangle([10, y, 10 + bar_len, y + bar_height], fill=(50, int(255 * score), int(255 * (1 - score))))
        draw.text((15, y + 5), f"{label}: {score:.2f}", font=font, fill=(255, 255, 255))

    # Pillow → OpenCV 戻し
    return cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)

# def draw_score_bar(frame, scores, labels):
#     image_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
#     draw = ImageDraw.Draw(image_pil)
#     font = ImageFont.load_default()
#     for i, (label, score) in enumerate(zip(labels, scores)):
#         y = 20 + i * 40
#         bar_len = int(min(score, 1.0) * 300)
#         draw.rectangle([10, y, 10 + bar_len, y + 30], fill=(50, int(255 * score), int(255 * (1 - score))))
#         draw.text((15, y + 5), f"{label}: {score:.2f}", font=font, fill=(255, 255, 255))
#     return cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)

def ensure_scores(scores, labels):
    with score_lock:
        return scores.copy() if scores is not None and len(scores) == len(labels) else np.zeros(len(labels))

def frame_generator():
    global latest_scores
    last_infer_time = 0
    fps_counter, fps_timer, current_fps = 0, time.time(), 0
    try:
        while not shutdown_event.is_set():
            start_time = time.time()
            frame = camera.read()
            fps_counter += 1
            if time.time() - fps_timer > 1.0:
                current_fps = fps_counter
                fps_counter, fps_timer = 0, time.time()
                inference_fps.set(current_fps)
            if not frame_queue.full():
                frame_queue.put_nowait(frame)
            if time.time() - last_infer_time > INFERENCE_INTERVAL:
                with inference_duration.time():
                    executor.submit(process_frames)
                last_infer_time = time.time()
            scores = ensure_scores(latest_scores, current_labels)
            annotated = draw_score_bar(frame.copy(), scores, current_labels)
            _, buffer = cv2.imencode(".jpg", annotated)
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
            frame_interval.observe(time.time() - start_time)
            time.sleep(0.01)
    except Exception as e:
        log.warning(f"frame_generator: {e}")

@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/video_feed")
def video_feed():
    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/get_labels")
def get_labels():
    return {"labels": current_labels}

@app.post("/set_labels")
def set_labels(label_update: LabelUpdate):
    global current_labels, latest_scores
    new_labels = [label.strip() for label in label_update.labels.split(",") if label.strip()]
    with score_lock:
        current_labels = new_labels
        latest_scores = np.zeros(len(current_labels))
    if current_labels:
        executor.submit(process_frames)
    return {"status": "ok", "labels": current_labels}

@app.get("/snapshot")
def snapshot():
    try:
        frame = camera.read()
        scores = ensure_scores(latest_scores, current_labels)
        annotated = draw_score_bar(frame.copy(), scores, current_labels)
        _, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        return Response(content=buffer.tobytes(), media_type="image/jpeg")
    except Exception as e:
        log.error(f"/snapshot 取得失敗: {e}")
        return Response(content=str(e), status_code=500)

@app.get("/metrics")
def metrics():
    mqtt_connected_metric.set(1 if mqtt_connected else 0)
    ovms_ready_metric.set(1 if client and tokenizer else 0)
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

@app.get("/healthz")
def healthz():
    return {"status": "alive"}

@app.get("/readyz")
def readyz():
    if client and tokenizer:
        return {"status": "ready"}
    return Response(content="not_ready", status_code=503)

@app.on_event("startup")
async def startup():
    global camera
    print("[Startup] Initializing camera...")

    try:
        camera = Camera(CAMERA_SOURCE)
        print("[Startup] Camera initialized.")
    except RuntimeError as e:
        log.error(f"カメラ初期化失敗: {e}")
        sys.exit(1)
    
    initialize_model()
    setup_mqtt()

@app.on_event("shutdown")
async def shutdown():
    shutdown_event.set()
    if executor:
        executor.shutdown(wait=True)
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
    if camera:
        camera.release()

def _graceful_shutdown(server=None):
    log.info("Graceful shutdown initiated")
    shutdown_event.set()
    if executor:
        executor.shutdown(wait=True)
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
    if camera:
        camera.release()
    if server:
        server.should_exit = True

async def run():
    config = Config("app:app", host="0.0.0.0", port=9000, log_level="info")
    server = Server(config)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: _graceful_shutdown(server))
    await server.serve()

if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        _graceful_shutdown()
        time.sleep(1)