import threading
import socket
import time
import cv2


# UDPソケットを作成
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# サーバのアドレスとポートを設定
server_address = ('192.168.10.1', 8889)

try:
    # 'command' コマンドを送信
    message = 'command'
    sock.sendto(message.encode(), server_address)

    message = 'streamon'
    sock.sendto(message.encode(), server_address)

finally:
    # ソケットを閉じる
    sock.close()

cap = cv2.VideoCapture("udp://%s:%s?overrun_nonfatal=1&fifo_size=50000000" % ("192.168.10.1", "11111"))

while True:
    try:
        ret, frame = cap.read()
        if ret:
            cv2.imshow("tello", cv2.resize(frame, (640, 480)))
            cv2.waitKey(1)
    except KeyboardInterrupt:
        cv2.destroyAllWindows()
        cap.release()
        print("Exit")
        break