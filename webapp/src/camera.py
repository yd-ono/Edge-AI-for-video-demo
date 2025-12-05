import cv2
import load_env
import logging
import threading

load_env.read_val_from_dotenv()

log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )

class Camera:
    """
    単一の VideoCapture を共有するシンプルトンカメラ。
    load_env.DEVICE で指定されたデバイスのみを使用する。
      - 数値なら index（0 など）
      - 文字列ならパス（/dev/video0 など）
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._init_capture()
                    cls._instance = obj
        return cls._instance

    def _init_capture(self):
        device = getattr(load_env, "DEVICE", None)
        if device is None:
            # 明示されていなければ 0 にフォールバック
            log.warning("load_env.DEVICE が未設定のため 0 を使用します")
            device = 0

        # 数値に変換できれば index として扱う
        try:
            device_parsed = int(device)
        except (TypeError, ValueError):
            device_parsed = device

        self._device = device_parsed

        # V4L2 を明示（USBカメラ向け）
        self._cap = cv2.VideoCapture(self._device, cv2.CAP_V4L2)

        # レイテンシ削減用のチューニング
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # バッファを最小に
        # 必要なら解像度を固定
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        # 目標30fps（カメラ側設定）
        self._cap.set(cv2.CAP_PROP_FPS, 30)

        if not self._cap.isOpened():
            raise RuntimeError(f"Failed to open camera device: {self._device}")

        log.info(f"Camera initialized on device: {self._device}")

    def get_frame(self, wait: bool = False):
        """
        1フレーム取得して返す。
        wait=True の場合は CAPTURE_WAIT_TIME 秒だけ待機してから取得。
        """
        if wait:
            import time
            time.sleep(float(getattr(load_env, "CAPTURE_WAIT_TIME", 0)))

        if self._cap is None or not self._cap.isOpened():
            log.warning("Capture is closed. Reinitializing camera.")
            self._init_capture()

        ok, frame = self._cap.read()
        if not ok:
            log.warning("Failed to read frame from camera.")
            return None
        return frame

    def release(self):
        with Camera._lock:
            if getattr(self, "_cap", None) is not None:
                log.info("Releasing camera capture.")
                self._cap.release()
                self._cap = None
                Camera._instance = None
