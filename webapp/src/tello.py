import socket

class Tello(object):
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