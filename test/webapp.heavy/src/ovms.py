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
# REST 用
import requests
import json
import os
import time

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

load_env.read_val_from_dotenv()

# ========= 環境変数 =========
PROTOCOL = getattr(load_env, "OVMS_PROTOCOL", "grpc").lower()      # "grpc" or "rest"
ENDPOINT = getattr(load_env, "OVMS_ENDPOINT", "localhost:9000")
MODEL_NAME = getattr(load_env, "MODEL_NAME", "yolov8")
OVMS_TIMEOUT = float(getattr(load_env, "OVMS_CLIENT_TIMEOUT", 5))
INPUT_NAME_ENV = getattr(load_env, "OVMS_INPUT_NAME", None)

# REST モード: "binary" or "json"
REST_MODE = getattr(load_env, "OVMS_REST_MODE", "binary").lower()

# ========= クライアントキャッシュ =========
_grpc_client = None
_grpc_input_name = None

_rest_session = None
_rest_url = None
_rest_input_name = None


# ========= 前処理 & 描画ユーティリティ =========
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
            results.append({"det": []})
            continue
        pred[:, :4] = ops.scale_boxes(input_hw, pred[:, :4], shape).round()
        results.append({"det": pred})
    return results


# ========= gRPC クライアント =========
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

    log.info(f"OVMS model input name (gRPC): {_grpc_input_name}")


# ========= REST クライアント =========
def _init_rest_client():
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

    log.info(f"Create REST client to OVMS: {_rest_url}, input={_rest_input_name}")


# ========= gRPC 推論 =========
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
    if isinstance(boxes, dict):
        boxes = next(iter(boxes.values()))
    detections = postprocess(pred_boxes=boxes, input_hw=input_hw, orig_img=image)
    return detections


# ========= REST JSON 推論（従来形式） =========
def _rest_detect_json(image: np.ndarray):
    _init_rest_client()

    preprocessed = letterbox(image)[0]
    input_tensor = np.expand_dims(preprocessed, 0).astype("uint8")
    input_hw = preprocessed.shape[:2]

    payload = {
        "inputs": [
            {
                "name": _rest_input_name,
                "shape": list(input_tensor.shape),
                "datatype": "UINT8",
                "data": input_tensor.reshape(-1).tolist(),
            }
        ]
    }

    resp = _rest_session.post(_rest_url, json=payload, timeout=OVMS_TIMEOUT)
    resp.raise_for_status()
    out = resp.json()

    outputs = out.get("outputs", [])
    if not outputs:
        raise RuntimeError("No outputs from REST model")

    o0 = outputs[0]
    data = np.array(o0["data"], dtype=np.float32)
    shape = o0.get("shape", None)
    if shape:
        data = data.reshape(shape)

    detections = postprocess(pred_boxes=data, input_hw=input_hw, orig_img=image)
    return detections


# ========= REST Binary 推論（rawバイナリ） =========
def _rest_detect_binary(image: np.ndarray):
    """
    KServe REST v2 の raw binary 入力を使用した高速版。

    - JSON 部分: 入力メタデータ（shape, datatype など）
    - バイナリ部分: UINT8 の生データ（N,H,W,C）
    を 1つの HTTP ボディに連結して送る。

    参考: OVMS docs 'Predict on Binary Inputs via KServe API'
    """
    _init_rest_client()

    preprocessed = letterbox(image)[0]
    input_tensor = np.expand_dims(preprocessed, 0).astype("uint8")
    input_hw = preprocessed.shape[:2]

    tensor_bytes = input_tensor.tobytes()
    binary_size = len(tensor_bytes)

    # JSON header 部分
    header_obj = {
        "inputs": [
            {
                "name": _rest_input_name,
                "shape": list(input_tensor.shape),
                "datatype": "UINT8",
                "parameters": {
                    "binary_data_size": binary_size
                },
            }
        ]
    }

    header_bytes = json.dumps(header_obj).encode("utf-8")

    headers = {
        "Content-Type": "application/octet-stream",
        "Inference-Header-Content-Length": str(len(header_bytes)),
        "Content-Length": str(len(header_bytes) + binary_size),
    }

    body = header_bytes + tensor_bytes

    resp = _rest_session.post(
        _rest_url,
        headers=headers,
        data=body,
        timeout=OVMS_TIMEOUT,
    )
    resp.raise_for_status()
    out = resp.json()

    outputs = out.get("outputs", [])
    if not outputs:
        raise RuntimeError("No outputs from REST model")

    o0 = outputs[0]
    data = np.array(o0["data"], dtype=np.float32)
    shape = o0.get("shape", None)
    if shape:
        data = data.reshape(shape)

    detections = postprocess(pred_boxes=data, input_hw=input_hw, orig_img=image)
    return detections


# ========= 公開API: detect / draw_results =========
def detect(image: np.ndarray):
    """
    環境変数に応じて gRPC / REST(JSON) / REST(Binary) を切替。
    OVMS_PROTOCOL = grpc / rest
    OVMS_REST_MODE = binary / json
    """
    protocol = os.environ.get("OVMS_PROTOCOL", PROTOCOL).lower()
    rest_mode = os.environ.get("OVMS_REST_MODE", REST_MODE).lower()

    if protocol == "rest":
        log.info(f"DETECT MODE=rest({rest_mode}) ENDPOINT={ENDPOINT}")
        if rest_mode == "binary":
            return _rest_detect_binary(image)
        else:
            return _rest_detect_json(image)
    else:
        log.info(f"DETECT MODE=grpc ENDPOINT={ENDPOINT}")
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
