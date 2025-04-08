import logging
import cv2
import numpy as np
import os
import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from transformers import CLIPTokenizer
from ovmsclient import make_grpc_client
import uvicorn
import concurrent.futures
import threading
import queue
from typing import List
import time
import paho.mqtt.client as mqtt
from PIL import Image, ImageDraw, ImageFont
import glob

# ==== 環境変数設定 ====
MODEL_NAME = os.getenv("MODEL_NAME", "demo")
OVMS_HOST = os.getenv("OVMS_HOST", "192.168.3.102:32290")
LABELS = os.getenv("LABELS", "person,dog,cat").split(",")
CAMERA_SOURCE = int(os.getenv("CAMERA_SOURCE", "0"))
INFERENCE_BATCH_SIZE = int(os.getenv("INFERENCE_BATCH_SIZE", "4"))
FRAME_BUFFER_SIZE = int(os.getenv("FRAME_BUFFER_SIZE", "2"))
INFERENCE_INTERVAL = float(os.getenv("INFERENCE_INTERVAL", "0.1"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ==== MQTT設定 ====
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "clip/result")
MQTT_QOS = int(os.getenv("MQTT_QOS", "1"))
MQTT_RETAIN = True

# ==== ログ設定 ====
logging.basicConfig(level=getattr(logging, LOG_LEVEL))
log = logging.getLogger("clip-app")

# ==== FastAPI初期化 ====
app = FastAPI(title="CLIP分類アプリ")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==== グローバル変数 ====
current_labels = LABELS.copy()
client = None
tokenizer = None
executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
score_lock = threading.Lock()
latest_scores = np.zeros(len(current_labels))
frame_queue = queue.Queue(maxsize=FRAME_BUFFER_SIZE)
is_processing = False

mqtt_client = None
mqtt_connected = False

# ==== MQTT処理 ====
# MQTT接続時のコールバック
def on_connect(client, userdata, flags, rc):
    global mqtt_connected
    if rc == 0:
        log.info("MQTT接続成功")
        mqtt_connected = True
    else:
        log.warning(f"MQTT接続失敗 rc={rc}")
        mqtt_connected = False

# MQTT切断時のコールバック
def on_disconnect(client, userdata, rc):
    global mqtt_connected
    mqtt_connected = False
    log.warning(f"MQTT切断（rc={rc}）")

# MQTTメッセージ受信時のコールバック
def setup_mqtt():
    global mqtt_client, mqtt_connected
    try:
        client = mqtt.Client()
        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()
        mqtt_client = client
    except Exception as e:
        log.warning(f"MQTT初期化失敗（無効化されます）: {e}")
        mqtt_client = None
        mqtt_connected = False

# ==== ラベル更新モデル ====
class LabelUpdate(BaseModel):
    labels: str

# ==== モデル初期化 ====
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

# ==== 推論処理 ====
def tokenize_texts(texts: List[str]):
    try:
        # トークン化
        encoded = tokenizer(texts, return_tensors="np", padding=True, truncation=True)
        return encoded["input_ids"], encoded["attention_mask"]
    except Exception as e:
        log.error(f"トークン化エラー: {e}")
        return tokenizer([""], return_tensors="np", padding=True, truncation=True)["input_ids"], tokenizer([""])["attention_mask"]

# 画像前処理
def preprocess_image(frame):
    resized = cv2.resize(frame, (224, 224))
    img = np.transpose(resized, (2, 0, 1))
    return np.expand_dims(img, axis=0).astype(np.float32) / 255.0

# 推論バッチ処理
def infer_batch(frames, labels):
    if not client or not tokenizer or not labels:
        return [np.zeros(len(labels)) for _ in frames]
    try:
        # 画像前処理
        imgs = np.vstack([preprocess_image(f) for f in frames])
        # テキストトークン化
        input_ids, attention_mask = tokenize_texts(labels)
        # 推論実行
        inputs = {"87": imgs, "input_ids": input_ids, "900": attention_mask}
        results = client.predict(inputs=inputs, model_name=MODEL_NAME)

        # 結果取得
        logits = np.array(results.get("logits_per_text", []))
        if logits.shape[0] == len(labels):
            logits = logits.T
        return [np.exp(l - np.max(l)) / np.sum(np.exp(l - np.max(l))) for l in logits]
    except Exception as e:
        log.error(f"推論エラー: {e}")
        return [np.zeros(len(labels)) for _ in frames]

# フレーム処理
def process_frames():
    global latest_scores, is_processing
    if is_processing:
        return
    is_processing = True
    try:
        frames = []
        # フレームをキューから取得
        while not frame_queue.empty() and len(frames) < INFERENCE_BATCH_SIZE:
            frames.append(frame_queue.get())
        if frames:
            # 推論実行
            scores_batch = infer_batch(frames, current_labels)
            if scores_batch:
                with score_lock:
                    # スコアを最新のものに更新
                    latest_scores = scores_batch[0]

                    # スコアを正規化
                    max_index = int(np.argmax(latest_scores))
                    # スコアが0.5以上のものを取得
                    max_label = current_labels[max_index]
                    max_score = float(latest_scores[max_index])
                    message = json.dumps({"label": max_label, "score": round(max_score, 4)})
                    # 推論結果をMQTTで送信
                    if mqtt_client and mqtt_connected:
                        try:
                            message = json.dumps({"label": max_label, "score": round(max_score, 4)}, ensure_ascii=False)
                            mqtt_client.publish(MQTT_TOPIC, payload=message.encode('utf-8'), qos=MQTT_QOS, retain=MQTT_RETAIN)
                            log.debug(f"MQTT Publish: {message}")
                        except Exception as e:
                            log.warning(f"MQTT Publish失敗（継続）: {e}")

    finally:
        is_processing = False

def find_japanese_font():
    # よく使われる日本語フォントの候補パス
    font_candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKJP-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
        "/usr/share/fonts/truetype/ipa/ipag.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc"
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

# スコアの整合性確認
def ensure_scores(scores, labels):
    with score_lock:
        if scores is None or len(scores) != len(labels):
            return np.zeros(len(labels))
        return scores.copy()

# フレーム生成器
def frame_generator():
    global latest_scores
    cap = cv2.VideoCapture(CAMERA_SOURCE)
    if not cap.isOpened():
        raise RuntimeError("カメラを開けません")

    last_infer_time = 0
    fps_counter, fps_timer, current_fps = 0, time.time(), 0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            # フレームのリサイズ
            fps_counter += 1
            if time.time() - fps_timer > 1.0:
                current_fps = fps_counter
                fps_counter, fps_timer = 0, time.time()

            # フレームの色空間変換
            if not frame_queue.full():
                frame_queue.put_nowait(frame.copy())

            # 推論処理のトリガー
            if time.time() - last_infer_time > INFERENCE_INTERVAL:
                executor.submit(process_frames)
                last_infer_time = time.time()

            # スコアの取得
            scores = ensure_scores(latest_scores, current_labels)
            annotated = draw_score_bar(frame.copy(), scores, current_labels)
            cv2.putText(annotated, f"FPS: {current_fps}", (10, annotated.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            _, buffer = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")

            time.sleep(0.01)
    finally:
        log.info("シャットダウン中: カメラを解放します")
        cap.release()

# ==== APIエンドポイント ====
# トップページ
@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "labels": ",".join(current_labels), "camera_source": CAMERA_SOURCE})

#  ==== ラベル更新 ====
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

# ==== カメラソース取得 ====
@app.get("/video_feed")
def video_feed():
    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")

# ヘルスチェック
@app.get("/health")
def health():
    return {
        "ovms_status": "ready" if client and tokenizer else "not_ready",
        "mqtt_status": "connected" if mqtt_connected else "disconnected"
    }

@app.on_event("startup")
async def startup():
    initialize_model()
    setup_mqtt()

@app.on_event("shutdown")
async def shutdown():
    global executor
    log.info("アプリケーションシャットダウン: スレッドプール停止中")
    if executor:
        executor.shutdown(wait=False)
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8888)