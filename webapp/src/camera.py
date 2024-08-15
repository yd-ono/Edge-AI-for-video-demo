# camera.py

import cv2
import load_env
import time
import threading

load_env.read_val_from_dotenv()

class Camera(object):
    def __init__(self):
        self.video = cv2.VideoCapture(load_env.DEVICE)
        self.video.open(load_env.DEVICE)

    def __del__(self):
        self.video.release()

    def get_frame(self, wait=False):
        if wait:
            time.sleep(int(load_env.CAPTURE_WAIT_TIME))

        _, image = self.video.read()
        return image