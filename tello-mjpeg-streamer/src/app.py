import logging
import cv2
from flask import Flask, Response
from tello import Tello

# Loggerを初期化
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s",
                    level=logging.INFO)
log = logging.getLogger(__name__)


app = Flask(__name__, static_folder='./templates/images')

def normal_stream(tello):
    while True:
        frame = tello.get_frame()
        _, frame = cv2.imencode('.jpg', frame)
        if frame is not None:
            yield (b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame.tobytes() + b"\r\n")
        else:
            log.error("frame is none")

@app.route("/mjpg")
def video_feed():
    return Response(normal_stream(Tello()),
            mimetype="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    app.debug = True
    app.run(host="0.0.0.0", port=5000, threaded=True)