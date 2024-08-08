# camera.py

import cv2
import load_env
import time
import socket

load_env.read_val_from_dotenv()

class Camera(object):
    def __init__(self):

        # UDPソケットを作成
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # サーバのアドレスとポートを設定
        server_address = ('192.168.10.1', 8889)

        try:
            # 'command' コマンドを送信
            message = 'command'
            sock.sendto(message.encode(), server_address)

            # 'takeoff' コマンドを送信
            message = 'streamon'
            sock.sendto(message.encode(), server_address)

        finally:
            # ソケットを閉じる
            sock.close()

        self.video = cv2.VideoCapture("udp://%s:%s?overrun_nonfatal=1&fifo_size=50000000" % ("192.168.10.1", "11111"))

    def __del__(self):
        self.video.release()

    def __del__(self):
        self.video.release()

    def get_frame(self, wait=False):
        if wait:
            time.sleep(int(load_env.CAPTURE_WAIT_TIME))

        _, image = self.video.read()
        return image