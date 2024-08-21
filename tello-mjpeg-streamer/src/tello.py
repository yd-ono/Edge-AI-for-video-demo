import socket
import logging
import time
import cv2
import load_env

# Loggerを初期化
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s",
                    level=logging.INFO)
log = logging.getLogger(__name__)

TELLO_ADDRESS       = (load_env.TELLO_IP, load_env.TELLO_CM_PORT)
TELLO_VIDEO_ADDRESS = (load_env.TELLO_IP, load_env.TELLO_VIDEO_PORT)

load_env.read_val_from_dotenv()

class Tello(object):
    def __init__(self):

        global TELLO_ADDRESS
        global TELLO_VIDEO_ADDRESS

        # UDP通信用ソケットを作成してBIND
        self.sock_cm = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        time.sleep(load_env.TELLO_SLEEP)
        # Telloをコマンドモードへ移行
        self.sock_cm.sendto('command'.encode('utf-8'), TELLO_ADDRESS)

        # カメラ映像のストリーミング開始
        time.sleep(load_env.TELLO_SLEEP)
        self.sock_cm.sendto('streamon'.encode('utf-8'), TELLO_ADDRESS)

        time.sleep(load_env.TELLO_SLEEP)
        self.video = cv2.VideoCapture("udp://%s:%s?overrun_nonfatal=1&fifo_size=50000000" % TELLO_VIDEO_ADDRESS)

    def __del__(self):
        global TELLO_ADDRESS

        # 'streamoff' コマンドを送信
        message = 'streamoff'
        self.sock_cm.sendto(message.encode('utf-8'), TELLO_ADDRESS)
        self.sock_cm.close()

    def get_frame(self):
        _, image = self.video.read()
        return image