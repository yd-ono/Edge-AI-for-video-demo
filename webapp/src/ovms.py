import os
import cv2
import json
import logging
import numpy as np
import requests
import ovmsclient
from typing import Dict

import load_env

# ========= ログ =========
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("OVMS-YOLOv8")

# ========= .env 読み込み =========
load_env.read_val_from_dotenv()

def _get_env(name: str, default: str):
    # load_env 経由を優先しつつ、なければ OS 環境変数を使う
    val = getattr(load_env, name, None)
    if val is not None:
        return str(val)
    return os.getenv(name, default)

# ========= ENV =========
PROTOCOL  = _get_env("OVMS_PROTOCOL", "grpc").lower()       # grpc / rest
ENDPOINT  = _get_env("OVMS_ENDPOINT", "localhost:9000")
MODEL     = _get_env("MODEL_NAME", "yolov8")
REST_MODE = _get_env("OVMS_REST_MODE", "binary").lower()    # json / binary
CONF      = float(_get_env("CONF", "0.25"))
TIMEOUT   = float(_get_env("OVMS_CLIENT_TIMEOUT", "5"))

# ========= PORT AutoFix for OVMS/NodePort (REST 用) =========
# ovms Service: 9000(gRPC)→NodePort:32290 / 9090(REST)→NodePort:32299
if PROTOCOL == "rest":
    if ENDPOINT.endswith("32290"):
        # gRPCポートを誤って指定していた場合、REST用に修正
        ENDPOINT = ENDPOINT[:-5] + "32299"
    if not ENDPOINT.startswith("http"):
        ENDPOINT = f"http://{ENDPOINT}"

# ========= Client cache =========
_g = None      # gRPC client
_gin = None    # gRPC input name
_rs = None     # REST session
_url = None    # REST infer URL


# ================== Letterbox ==================
def letterbox(img, new=(640, 640)):
    """YOLOv8 互換の簡易版 letterbox"""
    h, w = img.shape[:2]
    r = min(new[0] / h, new[1] / w)
    nh, nw = int(h * r), int(w * r)
    im = cv2.resize(img, (nw, nh))

    top = (new[0] - nh) // 2
    bottom = new[0] - nh - top
    left = (new[1] - nw) // 2
    right = new[1] - nw - left

    return cv2.copyMakeBorder(
        im, top, bottom, left, right,
        cv2.BORDER_CONSTANT, (114, 114, 114)
    )


# ================== NMS（重複BBox削除） ==================
def nms(det: np.ndarray, iou_thr: float = 0.55, max_det: int = 100) -> np.ndarray:
    """
    det: (N,6) [x1,y1,x2,y2,score,cls]
    """
    if det is None or len(det) == 0:
        return det

    det = det[np.argsort(-det[:, 4])]   # score 降順
    keep = []

    while len(det) > 0:
        m = det[0]
        keep.append(m)
        if len(keep) >= max_det:
            break

        rest = det[1:]

        # IoU計算
        xx1 = np.maximum(m[0], rest[:, 0])
        yy1 = np.maximum(m[1], rest[:, 1])
        xx2 = np.minimum(m[2], rest[:, 2])
        yy2 = np.minimum(m[3], rest[:, 3])

        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        a1 = (m[2] - m[0]) * (m[3] - m[1])
        a2 = (rest[:, 2] - rest[:, 0]) * (rest[:, 3] - rest[:, 1])
        iou = inter / (a1 + a2 - inter + 1e-9)

        det = rest[iou < iou_thr]   # IoU が閾値以上の枠を削除

    return np.array(keep, dtype=np.float32)


# ================== PostProcess（YOLOv8 + NMS） ==================
def post(raw, img: np.ndarray) -> np.ndarray:
    """
    OVMS output raw: (1,84,8400) or (84,8400) or (8400,84)
    戻り値: det (N,6) [x1,y1,x2,y2,score,cls] （元画像座標系）
    """
    p = np.array(raw, dtype=np.float32)
    if p.ndim == 3:
        p = p.squeeze(0)          # (1,84,8400) → (84,8400)
    if p.shape[0] < p.shape[1]:
        p = p.T                   # (84,8400) → (8400,84)

    # [cx,cy,w,h] → [x1,y1,x2,y2]
    xywh = p[:, :4]
    xyxy = np.zeros_like(xywh)
    xyxy[:, 0] = xywh[:, 0] - xywh[:, 2] / 2
    xyxy[:, 1] = xywh[:, 1] - xywh[:, 3] / 2
    xyxy[:, 2] = xywh[:, 0] + xywh[:, 2] / 2
    xyxy[:, 3] = xywh[:, 1] + xywh[:, 3] / 2

    # クラススコア
    cls_scores = p[:, 4:]
    cls = np.argmax(cls_scores, axis=1)
    score = np.max(cls_scores, axis=1)

    det = np.column_stack((xyxy, score, cls))

    # スコア閾値
    det = det[det[:, 4] > CONF]
    if len(det) == 0:
        return det

    # NMS
    det = nms(det, iou_thr=0.55, max_det=100)
    if len(det) == 0:
        return det

    # 元画像解像度にスケール戻し
    h0, w0 = img.shape[:2]
    gain = min(640 / h0, 640 / w0)
    padw = (640 - w0 * gain) / 2
    padh = (640 - h0 * gain) / 2

    det[:, [0, 2]] -= padw
    det[:, [1, 3]] -= padh
    det[:, :4] /= gain

    det[:, 0] = det[:, 0].clip(0, w0)
    det[:, 2] = det[:, 2].clip(0, w0)
    det[:, 1] = det[:, 1].clip(0, h0)
    det[:, 3] = det[:, 3].clip(0, h0)

    return det.astype(np.float32)


# ================== gRPC ==================
def _grpc(img: np.ndarray) -> Dict[str, np.ndarray]:
    global _g, _gin
    if _g is None:
        # ENDPOINT は "host:port" を期待（もし http:// がついてたら除去）
        target = ENDPOINT.replace("http://", "").replace("https://", "")
        log.info(f"[gRPC connect] {target}")
        _g = ovmsclient.make_grpc_client(target)

        meta = _g.get_model_metadata(model_name=MODEL, timeout=TIMEOUT)
        _gin = next(iter(meta["inputs"].keys()))
        log.info(f"[gRPC input] {_gin}")

    blob = letterbox(img)
    inp = np.expand_dims(blob, 0)

    out = _g.predict({_gin: inp}, model_name=MODEL, timeout=TIMEOUT)

    # ★ out が dict の場合と ndarray の場合の両対応
    if isinstance(out, dict):
        raw = list(out.values())[0]
    else:
        raw = out

    det = post(raw, img)
    return {"det": det}


# ================== REST ==================
def _rest(img: np.ndarray) -> Dict[str, np.ndarray]:
    global _rs, _url
    if _rs is None:
        _rs = requests.Session()
        _url = f"{ENDPOINT}/v2/models/{MODEL}/infer"
        log.info(f"[REST connect] {_url}")

    blob = letterbox(img)
    inp = np.expand_dims(blob, 0).astype("uint8")

    if REST_MODE == "json":
        payload = {
            "inputs": [
                {
                    "name": "images",
                    "shape": list(inp.shape),
                    "datatype": "UINT8",
                    "data": inp.reshape(-1).tolist(),
                }
            ]
        }
        r = _rs.post(_url, json=payload, timeout=TIMEOUT)
    else:
        header = {
            "inputs": [
                {
                    "name": "images",
                    "shape": list(inp.shape),
                    "datatype": "UINT8",
                    "parameters": {
                        "binary_data_size": int(inp.nbytes),
                    },
                }
            ]
        }
        header_bytes = json.dumps(header).encode()
        body = header_bytes + inp.tobytes()

        r = _rs.post(
            _url,
            data=body,
            headers={
                "Content-Type": "application/octet-stream",
                "Inference-Header-Content-Length": str(len(header_bytes)),
            },
            timeout=TIMEOUT,
        )

    r.raise_for_status()
    out = r.json()
    o0 = out["outputs"][0]
    data = np.array(o0["data"], dtype=np.float32).reshape(o0["shape"])

    det = post(data, img)
    return {"det": det}


# ================== API ==================
def detect(img: np.ndarray) -> Dict[str, np.ndarray]:
    """
    app.py から呼ばれる公開API。
    戻り値: {"det": ndarray(N,6)}
    """
    if PROTOCOL == "rest":
        return _rest(img)
    else:
        return _grpc(img)


def draw_results(res: Dict, img: np.ndarray, labels: Dict) -> np.ndarray:
    """
    検出結果を画像に描画する。
    res["det"] は [x1,y1,x2,y2,score,class] の ndarray を想定。
    """
    det = res.get("det", None)
    if det is None or len(det) == 0:
        return img

    for (x1, y1, x2, y2, s, c) in det:
        if s < CONF:
            continue

        color = (0, 255, 0)
        cv2.rectangle(
            img,
            (int(x1), int(y1)),
            (int(x2), int(y2)),
            color,
            3,
        )

        text = f"{labels[int(c)]} {s:.2f}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        thickness = 2
        t_size = cv2.getTextSize(text, font, font_scale, thickness)[0]

        # テキスト背景が bbox と潰れにくいように、少し上に出す
        text_x = int(x1)
        text_y = max(int(y1) - 5, t_size[1] + 5)

        cv2.rectangle(
            img,
            (text_x, text_y - t_size[1] - 6),
            (text_x + t_size[0] + 6, text_y + 2),
            color,
            -1,
        )
        cv2.putText(
            img,
            text,
            (text_x + 3, text_y - 3),
            font,
            font_scale,
            (0, 0, 0),
            thickness,
        )
    return img
