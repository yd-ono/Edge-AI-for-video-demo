import cv2
import logging
from typing import Tuple, Dict

import numpy as np
import torch
from ultralytics.utils import ops
from ultralytics.utils.plotting import colors

import load_env

# gRPC 用
import ovmsclient
# REST(KServe/OVMS HTTP) 用
import requests

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

load_env.read_val_from_dotenv()

# ========= 環境変数 =========
PROTOCOL = getattr(load_env, "OVMS_PROTOCOL", "grpc").lower()   # "grpc" or "rest"
ENDPOINT = getattr(load_env, "OVMS_ENDPOINT", "localhost:9000")
MODEL_NAME = getattr(load_env, "MODEL_NAME", "yolov8")
OVMS_TIMEOUT = float(getattr(load_env, "OVMS_CLIENT_TIMEOUT", 5))

INPUT_NAME_ENV = getattr(load_env, "OVMS_INPUT_NAME", None)

# ========= クライアントキャッシュ =========
_grpc_client = None
_grpc_input_name = None

_rest_session = None
_rest_url = None
_rest_input_name = None


def _init_grpc_client():
    global _grpc_client, _grpc_input_name
    if _grpc_client is not None:
        return

    log.info(f"Create gRPC client to OVMS: {ENDPOINT}")
    _grpc_client = ovmsclient.make_grpc_client(ENDPOINT)

    meta = _grpc_client.get_model_metadata(
        model_name=MODEL_NAME,
        timeout=OVMS_TIMEOUT
    )
    if INPUT_NAME_ENV:
        _grpc_input_name = INPUT_NAME_ENV
    else:
        _grpc_input_name = next(iter(meta["inputs"]))

    log.info(f"OVMS model input name: {_grpc_input_name}")


def _init_rest_client():
    """
    KServe / OVMS REST v2 想定。
    ENDPOINT は例: http://ovms:8001  のようなURLベース。
    """
    global _rest_session, _rest_url, _rest_input_name
    if _rest_session is not None:
        return

    if not ENDPOINT.startswith("http"):
        base = "http://" + ENDPOINT
    else:
        base = ENDPOINT

    _rest_session = requests.Session()
    _rest_url = base.rstrip("/") + f"/v2/models/{MODEL_NAME}/infer"
    _rest_input_name = INPUT_NAME_ENV or "images"

    log.info(f"Create REST client to KServe/OVMS: {_rest_url}, input={_rest_input_name}")


# ========= 描画系ユーティリティ =========
def plot_one_box(
    box: np.ndarray,
    img: np.ndarray,
    color: Tuple[int, int, int] = None,
    label: str = None,
    line_thickness: int = 5,
):
    tl = line_thickness or round(0.002 * (img.shape[0] + img.shape[1]) / 2) + 1
    color = color or [int(x) for x in np.random.randint(0, 255, 3)]
    c1, c2 = (int(box[0]), int(box[1])), (int(box[2]), int(box[3]))
    cv2.rectangle(img, c1, c2, color, thickness=tl, lineType=cv2.LINE_AA)
    if label:
        tf = max(tl - 1, 1)
        t_size = cv2.getTextSize(label, 0, fontScale=tl / 3, thickness=tf)[0]
        c2 = c1[0] + t_size[0], c1[1] - t_size[1] - 3
        cv2.rectangle(img, c1, c2, color, -1, cv2.LINE_AA)
        cv2.putText(
            img,
            label,
            (c1[0], c1[1] - 2),
            0,
            tl / 3,
            [225, 255, 255],
            thickness=tf,
            lineType=cv2.LINE_AA,
        )
    return img


def letterbox(
    img: np.ndarray,
    new_shape: Tuple[int, int] = (640, 640),
    color: Tuple[int, int, int] = (114, 114, 114),
    auto: bool = False,
    scale_fill: bool = False,
    scaleup: bool = False,
    stride: int = 32,
):
    shape = img.shape[:2]  # h, w
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    if not scaleup:
        r = min(r, 1.0)

    ratio = r, r
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]
    if auto:
        dw, dh = np.mod(dw, stride), np.mod(dh, stride)
    elif scale_fill:
        dw, dh = 0.0, 0.0
        new_unpad = (new_shape[1], new_shape[0])
        ratio = new_shape[1] / shape[1], new_shape[0] / shape[0]

    dw /= 2
    dh /= 2

    if shape[::-1] != new_unpad:
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(
        img, top, bottom, left, right,
        cv2.BORDER_CONSTANT, value=color
    )
    return img, ratio, (dw, dh)


def postprocess(
    pred_boxes: np.ndarray,
    input_hw: Tuple[int, int],
    orig_img: np.ndarray,
    min_conf_threshold: float = 0.25,
    nms_iou_threshold: float = 0.7,
    agnosting_nms: bool = False,
    max_detections: int = 300,
):
    nms_kwargs = {"agnostic": agnosting_nms, "max_det": max_detections}
    preds = ops.non_max_suppression(
        torch.from_numpy(pred_boxes),
        min_conf_threshold,
        nms_iou_threshold,
        nc=80,
        **nms_kwargs,
    )

    results = []
    for i, pred in enumerate(preds):
        shape = orig_img[i].shape if isinstance(orig_img, list) else orig_img.shape
        if not len(pred):
            results.append({"det": [], "segment": []})
            continue
        pred[:, :4] = ops.scale_boxes(input_hw, pred[:, :4], shape).round()
        results.append({"det": pred})
    return results


# ========= 推論本体 =========
def _grpc_detect(image: np.ndarray):
    _init_grpc_client()

    preprocessed = letterbox(image)[0]
    input_tensor = np.expand_dims(preprocessed, 0)
    input_hw = preprocessed.shape[:2]

    inputs = {_grpc_input_name: input_tensor}
    boxes = _grpc_client.predict(
        inputs=inputs,
        model_name=MODEL_NAME,
        timeout=OVMS_TIMEOUT,
    )
    # ovmsclient は dict を返すので最初の value を取得
    if isinstance(boxes, dict):
        boxes = next(iter(boxes.values()))
    detections = postprocess(pred_boxes=boxes, input_hw=input_hw, orig_img=image)
    return detections


def _rest_detect(image: np.ndarray):
    """
    KServe/OVMS REST v2用の参考実装。
    モデルの input_name / 出力shape に応じて調整してください。
    """
    _init_rest_client()

    preprocessed = letterbox(image)[0]
    input_tensor = np.expand_dims(preprocessed, 0).astype("float32")
    input_hw = preprocessed.shape[:2]

    payload = {
        "inputs": [
            {
                "name": _rest_input_name,
                "shape": list(input_tensor.shape),
                "datatype": "FP32",
                "data": input_tensor.reshape(-1).tolist(),
            }
        ]
    }

    resp = _rest_session.post(_rest_url, json=payload, timeout=OVMS_TIMEOUT)
    resp.raise_for_status()
    out = resp.json()

    # v2: outputs[0].data / .shape を前提（YOLO形式に合わせる必要あり）
    outputs = out.get("outputs", [])
    if not outputs:
        raise RuntimeError("No outputs from REST model")

    o0 = outputs[0]
    data = np.array(o0["data"], dtype=np.float32)
    shape = o0.get("shape", None)
    if shape:
        data = data.reshape(shape)
    # ここでは [N, anchors, 85] のような YOLO 出力を想定
    boxes = data
    detections = postprocess(pred_boxes=boxes, input_hw=input_hw, orig_img=image)
    return detections


def detect(image: np.ndarray):
    """
    プロトコルに応じて gRPC or REST を呼び分ける。
    """
    if PROTOCOL == "rest":
        return _rest_detect(image)
    # デフォルト gRPC
    return _grpc_detect(image)


def draw_results(results: Dict, source_image: np.ndarray, label_map: Dict):
    """
    検出結果を画像に描画する。
    results["det"] は [x1,y1,x2,y2,score,label] の Tensor を想定。
    """
    boxes = results["det"]
    conf_thr = float(getattr(load_env, "CONF", 0.25))

    for idx, (*xyxy, conf, lbl) in enumerate(boxes):
        if conf < conf_thr:
            continue
        label = f'{label_map[int(lbl)]} {conf:.2f}'
        log.info(label)
        source_image = plot_one_box(
            xyxy, source_image,
            label=label,
            color=colors(int(lbl)),
            line_thickness=3,
        )
    return source_image
