import socket
import logging
import time
import cv2

# Loggerを初期化
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s",
                    level=logging.INFO)
log = logging.getLogger(__name__)

TELLO_IP            = '192.168.10.1'
TELLO_CM_PORT       = 8889
TELLO_VIDEO_PORT    = 11111
TELLO_ADDRESS       = (TELLO_IP, TELLO_CM_PORT)
TELLO_VIDEO_ADDRESS = (TELLO_IP, TELLO_VIDEO_PORT)

class Tello(object):
    def __init__(self):

        global TELLO_ADDRESS
        global TELLO_VIDEO_ADDRESS

        # UDP通信用ソケットを作成してBIND
        self.sock_cm = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        time.sleep(2)
        # Telloをコマンドモードへ移行
        self.sock_cm.sendto('command'.encode('utf-8'), TELLO_ADDRESS)

        # カメラ映像のストリーミング開始
        time.sleep(2)
        self.sock_cm.sendto('streamon'.encode('utf-8'), TELLO_ADDRESS)

        time.sleep(5)
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