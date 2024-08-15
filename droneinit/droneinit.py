import socket
import threading
import time
import logging
import pings
import flask
import os

# Loggerを初期化
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s",
                    level=logging.INFO)
log = logging.getLogger(__name__)

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

def monitor(TELLO_IP):
    global connection_status

    while True:
        res = p.ping(TELLO_IP)
        if res.is_reached():
            connection_status = 'connected'
            log.info("connected")
        else:
            connection_status = 'disconnected'
            continue

# 変数
end_flag=False
tello_response=''
tello_status=''
tello_all_status=''
connection_status=''
flag=False

# TelloのIPアドレス、ポート(コマンド用)、ポート(機体ステータス用)
TELLO_IP      = '192.168.10.1'
TELLO_CM_PORT = 8889
TELLO_ST_PORT = 8890
TELLO_ADDRESS = (TELLO_IP, TELLO_CM_PORT)

p = pings.Ping()

# 監視用スレッドの作成
thread_cm = threading.Thread(target=monitor, args=(TELLO_IP,))
thread_cm.daemon = True
thread_cm.start()

while True:
    if connection_status == 'connected':

        if flag:
            # UDP通信用ソケットを作成してBIND
            sock_cm = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock_cm.bind(('', TELLO_CM_PORT))
            # コマンド送信結果　受信用スレッドの作成
            thread_cm = threading.Thread(target=udp_receiver_command, args=(sock_cm,))
            thread_cm.daemon = True
            thread_cm.start()

            sock_st = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock_st.bind(('', TELLO_ST_PORT))
            # 機体ステータス　　受信用スレッドの作成
            thread_st = threading.Thread(target=udp_receiver_status, args=(sock_st,))
            thread_st.daemon = True
            thread_st.start()

            tello_response = ''
            while True:
                # コマンドモード
                sock_cm.sendto('command'.encode('utf-8'), TELLO_ADDRESS)
                time.sleep(1)
                if tello_response == 'ok':
                    log.info("command response OK")
                    break
                if connection_status == 'disconnected':
                    break
                log.info("wait for command response...")

            # Telloのバッテリ取得
            sock_cm.sendto('battery?'.encode('utf-8'), TELLO_ADDRESS)
            time.sleep(1)
            log.info('Tello Battery: ' + tello_response.strip() + '%')

            # カメラ映像のストリーミング開始
            sock_cm.sendto('streamon'.encode('utf-8'), TELLO_ADDRESS)
            time.sleep(1)
            if tello_response == 'ok':
                log.info("streamon command response OK")


            sock_cm.close()
            sock_st.close()
            flag=False

        else:
            log.info("Tello has been already setup")

    else:
        log.warning("Tello is not unreachable")
        flag=True

    time.sleep(1)