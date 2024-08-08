import socket
import threading
import logging
import time
import load_env


load_env.read_val_from_dotenv()

# Loggerを初期化
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s",
                    level=logging.INFO)
log = logging.getLogger(__name__)

class Tello(object):
    def __init__(self):

        # UDPソケットを作成
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # thread for receiving cmd ack
        self.receive_thread = threading.Thread(target=self._receive_thread)
        self.receive_thread.daemon = True
        self.receive_thread.start()

        # サーバのアドレスとポートを設定
        self.server_address = ('192.168.10.1', 8889)

        # 'command' コマンドを送信
        message = 'command'
        self.sock.sendto(message.encode(), self.server_address)
        time.sleep(load_env.TELLO_INIT_WAIT_TIME)

        # 'streamon' コマンドを送信
        message = 'streamon'
        self.sock.sendto(message.encode(), self.server_address)
        time.sleep(load_env.TELLO_STREAM_WAIT_TIME)

    def __del__(self):
        # 'streamoff' コマンドを送信
        message = 'streamoff'
        self.sock.sendto(message.encode(), self.server_address)
        self.sock.close()

    def _receive_thread(self):
        """Listen to responses from the Tello.
        Runs as a thread, sets self.response to whatever the Tello last returned.
        """
        while True:
            try:
                self.response, ip = self.sock.recvfrom(3000)
                log.debug(self.response)
            except socket.error as exc:
                log.error("Caught exception socket.error : %s" % exc)