import load_env
import logging
import cv2
from flask import Flask, render_template, Response
import ovms
import yaml
import time
from tello import Tello

# Loggerを初期化
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s",
                    level=logging.INFO)
log = logging.getLogger(__name__)

load_env.read_val_from_dotenv()

app = Flask(__name__, static_folder='./templates/images')

@app.route("/")
def index():
    return render_template("stream.html")

@app.route("/predict")
def predict():
    return render_template("predict.html")

def normal_stream(tello):
    while True:
        frame = tello.get_frame()
        _, frame = cv2.imencode('.jpg', frame)
        if frame is not None:
            yield (b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame.tobytes() + b"\r\n")
        else:
            log.error("frame is none")

def predict_stream(tello):
    # ラベルマップを取得
    with open('coco.yaml', 'r') as yml:
        config = yaml.safe_load(yml)
    label_map = config['names']
    detected_frame = ""

    while True:
        frame = tello.get_frame()

        try:
            detections = ovms.detect(frame)[0]
            # バウンディングボックスを画像へ埋め込み
            detected_frame = ovms.draw_results(detections, frame, label_map)
        except Exception as e:
            detected_frame = frame
            log.error(e)

        # jpg形式へエンコード
        _, annotated_frame = cv2.imencode('.jpg', detected_frame)
        if annotated_frame is not None:
            yield (b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + annotated_frame.tobytes() + b"\r\n")
        else:
            log.error("frame is none")

        time.sleep(load_env.FPS)

@app.route("/video_feed")
def video_feed():
    return Response(normal_stream(Tello()),
            mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/predict_feed")
def predict_feed():
    return Response(predict_stream(Tello()),
            mimetype="multipart/x-mixed-replace; boundary=frame")

## デモ用のコード
# @app.route("/save_image")
# def save_image():
#     frame = Camera().get_frame(wait=True)
#     _, buffer = cv2.imencode('.jpg', frame)

#     return Response(buffer.tobytes(), mimetype='image/jpeg')

if __name__ == "__main__":
    app.debug = True
    app.run(host="0.0.0.0", port=int(load_env.PORT), threaded=True)