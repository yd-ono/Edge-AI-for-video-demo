import socket
import time

def main():
    # UDPソケットを作成
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # サーバのアドレスとポートを設定
    server_address = ('192.168.10.1', 8889)

    try:
        # 'command' コマンドを送信
        message = 'command'
        sock.sendto(message.encode(), server_address)

        # 'takeoff' コマンドを送信
        message = 'takeoff'
        sock.sendto(message.encode(), server_address)

        # 3秒間待機
        time.sleep(3)

        # 'land' コマンドを送信
        message = 'land'
        sock.sendto(message.encode(), server_address)

    finally:
        # ソケットを閉じる
        sock.close()

if __name__ == "__main__":
    main()