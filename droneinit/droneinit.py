import socket
import threading
import time
import logging
import pings
import os

# Loggerを初期化
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s",
                    level=logging.INFO)
log = logging.getLogger(__name__)

## Telloへ送信したコマンドの応答を取得
def get_tello_response(sock):
    response, _ = sock.recvfrom(1024)
    # コマンドの応答結果をグローバル変数に格納
    tello_response = response.decode('utf-8')

    return tello_response

## Telloの死活監視用スレッド
def monitor(TELLO_IP):
    global connection_status

    while True:
        res = p.ping(TELLO_IP)
        if res.is_reached():
            connection_status = 'connected'
        else:
            connection_status = 'disconnected'
            continue
        time.sleep(1)

# 変数
connection_status=''
flag=False

# TelloのIPアドレス、ポート(コマンド用)、ポート(機体ステータス用)
TELLO_IP      = '192.168.10.1'
TELLO_CM_PORT = 8889
TELLO_ADDRESS = (TELLO_IP, TELLO_CM_PORT)

p = pings.Ping()

# 監視用スレッドの作成
thread_cm = threading.Thread(target=monitor, args=(TELLO_IP,))
thread_cm.daemon = True
thread_cm.start()

while True:
    if connection_status == 'connected':

        if flag:
            log.info("connected")

            # UDP通信用ソケットを作成してBIND
            sock_cm = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock_cm.bind(('', TELLO_CM_PORT))

            tello_response = ''
            while True:
                # コマンドモード
                sock_cm.sendto('command'.encode('utf-8'), TELLO_ADDRESS)
                time.sleep(1)
                # コマンドの応答結果をグローバル変数に格納
                tello_response = get_tello_response(sock_cm)

                if tello_response == 'ok':
                    log.info("command response OK")
                    break
                else:
                    log.info("wait for command response...")

                if connection_status == 'disconnected':
                    break

            # Telloのバッテリ取得
            sock_cm.sendto('battery?'.encode('utf-8'), TELLO_ADDRESS)
            time.sleep(1)
            tello_response = get_tello_response(sock_cm)
            log.info('Tello Battery: ' + tello_response.strip() + '%')

            # カメラ映像のストリーミング開始
            sock_cm.sendto('streamon'.encode('utf-8'), TELLO_ADDRESS)
            time.sleep(1)
            tello_response = get_tello_response(sock_cm)
            if tello_response == 'ok':
                log.info("streamon command response OK")

            flag=False
            sock_cm.close()

        else:
            log.info("Tello has been already setup")
    else:
        log.warning("Tello is not unreachable")
        flag=True

    time.sleep(1)