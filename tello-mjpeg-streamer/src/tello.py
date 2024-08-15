import socket
import threading
import logging
import time
import cv2

# Loggerを初期化
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s",
                    level=logging.INFO)
log = logging.getLogger(__name__)


# 変数
end_flag=False
tello_response=''
tello_status=''
tello_all_status=''
connection_status=''
flag=False

TELLO_IP      = '192.168.10.1'
TELLO_CM_PORT = 8889
TELLO_ST_PORT = 8890
TELLO_VIDEO_PORT = 11111
TELLO_ADDRESS = (TELLO_IP, TELLO_CM_PORT)
TELLO_VIDEO_ADDRESS = (TELLO_IP, TELLO_VIDEO_PORT)

# Tello機体ステータス 受け取り用の関数
def udp_receiver_status(sock):
    global end_flag
    global tello_status

    while end_flag==False:
        try:
            response, _ = sock.recvfrom(1024)
            # 機体ステータスをグローバル変数に格納
            tello_status = response.decode('utf-8')
        except Exception as e:
            print(e)
            break

# Telloコマンド結果 受け取り用の関数
def udp_receiver_command(sock):
    global end_flag
    global tello_response

    while end_flag==False:
        try:
            response, _ = sock.recvfrom(1024)
            # コマンドの応答結果をグローバル変数に格納
            tello_response = response.decode('utf-8')
        except Exception as e:
            print(e)
            break

class Tello(object):
    def __init__(self):

        global TELLO_IP
        global TELLO_CM_PORT
        global TELLO_ST_PORT
        global TELLO_VIDEO_PORT
        global TELLO_ADDRESS
        global TELLO_VIDEO_ADDRESS
        global tello_response

        # UDP通信用ソケットを作成してBIND
        self.sock_cm = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_cm.bind(('', TELLO_CM_PORT))
        # コマンド送信結果　受信用スレッドの作成
        thread_cm = threading.Thread(target=udp_receiver_command, args=(self.sock_cm,))
        thread_cm.daemon = True
        thread_cm.start()

        self.sock_st = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_st.bind(('', TELLO_ST_PORT))
        # 機体ステータス　　受信用スレッドの作成
        thread_st = threading.Thread(target=udp_receiver_status, args=(self.sock_st,))
        thread_st.daemon = True
        thread_st.start()

        while True:
            # コマンドモード
            self.sock_cm.sendto('command'.encode('utf-8'), TELLO_ADDRESS)
            time.sleep(1)
            if tello_response == 'ok':
                log.info("command response OK")
                break
            log.info("wait for command response...")

        # Telloのバッテリ取得
        self.sock_cm.sendto('battery?'.encode('utf-8'), TELLO_ADDRESS)
        time.sleep(1)
        log.info('Tello Battery: ' + tello_response.strip() + '%')

        # カメラ映像のストリーミング開始
        self.sock_cm.sendto('streamon'.encode('utf-8'), TELLO_ADDRESS)
        time.sleep(1)
        if tello_response == 'ok':
            log.info("streamon command response OK")

        time.sleep(5)
        self.video = cv2.VideoCapture("udp://%s:%s?overrun_nonfatal=1&fifo_size=50000000" % TELLO_VIDEO_ADDRESS)

    def __del__(self):
        # 'streamoff' コマンドを送信
        message = 'streamoff'
        self.sock_cm.sendto(message.encode(), self.server_address)
        self.sock_cm.close()

    def get_frame(self):
        _, image = self.video.read()
        return image