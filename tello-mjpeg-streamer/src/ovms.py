import ovmsclient
import cv2
from typing import Tuple, Dict
from ultralytics.utils import ops
import torch
import numpy as np
from ultralytics.utils.plotting import colors
import random
import logging
import load_env

# Loggerを初期化
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s",
                    level=logging.INFO)
log = logging.getLogger(__name__)

load_env.read_val_from_dotenv()


def plot_one_box(
    box: np.ndarray,
    img: np.ndarray,
    color: Tuple[int, int, int] = None,
    label: str = None,
    line_thickness: int = 5,
):
    """
    画像上に単一のバウンディングボックスを描画するヘルパー関数
    パラメータ
        x (np.ndarray): [x1, y1, x2, y2]形式のバウンディングボックス座標。
        img (no.ndarray): 入力画像
        color (Tuple[int, int, int], *optional*, None): 描画ボックスの BGR 形式の色。
        label (str, *optonal*, None): 描画ボックスのラベル文字列。
        line_thickness (int, *optional*, 5): 描画ボックスの線の太さ。
    """
    # Plots one bounding box on image img
    tl = line_thickness or round(0.002 * (img.shape[0] + img.shape[1]) / 2) + 1  # line/font thickness
    color = color or [random.randint(0, 255) for _ in range(3)]
    c1, c2 = (int(box[0]), int(box[1])), (int(box[2]), int(box[3]))
    cv2.rectangle(img, c1, c2, color, thickness=tl, lineType=cv2.LINE_AA)
    if label:
        tf = max(tl - 1, 1)  # font thickness
        t_size = cv2.getTextSize(label, 0, fontScale=tl / 3, thickness=tf)[0]
        c2 = c1[0] + t_size[0], c1[1] - t_size[1] - 3
        cv2.rectangle(img, c1, c2, color, -1, cv2.LINE_AA)  # filled
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
    """
    画像サイズと検出用パディングを変更する。画像を入力として受け取る、
    元のアスペクト比を保ったまま新しい形状に収まるように画像をリサイズし，ストライド多重制約を満たすようにパディングする。

    パラメータ
      img (np.ndarray): 前処理用の画像。
      new_shape (Tuple(int, int)): 前処理後の画像サイズ (フォーマット [height, width])
      color (Tuple(int, int, int)): パディングされた領域を塗りつぶす色。
      auto (bool): 動的な入力サイズを使用し、ストライド定数に対するパディングのみ適用
      scale_fill (bool): new_shape を埋めるように画像を拡大縮小します。
      scaleup (bool): 必要な入力サイズより小さい場合に画像の拡大縮小を許可する。
      stride (int): 入力パディングの長さ。
    戻り値
      img (np.ndarray): 前処理後の画像。

    """
    # Resize and pad image while meeting stride-multiple constraints
    shape = img.shape[:2]  # current shape [height, width]
    if isinstance(new_shape, int):
        new_shape = (new_shape, new_shape)

    # Scale ratio (new / old)
    r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
    if not scaleup:  # only scale down, do not scale up (for better test mAP)
        r = min(r, 1.0)

    # Compute padding
    ratio = r, r  # width, height ratios
    new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
    dw, dh = new_shape[1] - new_unpad[0], new_shape[0] - new_unpad[1]  # wh padding
    if auto:  # minimum rectangle
        dw, dh = np.mod(dw, stride), np.mod(dh, stride)  # wh padding
    elif scale_fill:  # stretch
        dw, dh = 0.0, 0.0
        new_unpad = (new_shape[1], new_shape[0])
        ratio = new_shape[1] / shape[1], new_shape[0] / shape[0]  # width, height ratios

    dw /= 2  # divide padding into 2 sides
    dh /= 2

    if shape[::-1] != new_unpad:  # resize
        img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(dh - 0.1)), int(round(dh + 0.1))
    left, right = int(round(dw - 0.1)), int(round(dw + 0.1))
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)  # add border
    return img, ratio, (dw, dh)


## 後処理
def postprocess(
    pred_boxes: np.ndarray,
    input_hw: Tuple[int, int],
    orig_img: np.ndarray,
    min_conf_threshold: float = 0.25,
    nms_iou_threshold: float = 0.7,
    agnosting_nms: bool = False,
    max_detections: int = 300,
):
    """
    YOLOv8モデルの後処理機能。検出された画像に非最大圧縮アルゴリズムを適用し、元の画像サイズにボックスを再スケールする。
    パラメータ
        pred_boxes (np.ndarray): モデル出力予測ボックス
        input_hw (np.ndarray): 前処理済み画像
        orig_image (np.ndarray): 前処理前の画像
        min_conf_threshold (float, *optional*, 0.25): オブジェクトフィルタリングのための最小許容信頼度
        nms_iou_threshold (float, *optional*, 0.45): NMS でオブジェクトの重複を除去するための最小重複スコア
        agnostic_nms (bool, *optiona*, False): クラスアグノスティックの NMS アプローチを適用するかどうか
        max_detections (int, *optional*, 300): NMS後の最大検出数。
    戻り値
       pred (List[Dict[str, np.ndarray]]): [x1, y1, x2, y2, score, label]のフォーマットで検出されたボックスを含む辞書のリスト
    """
    nms_kwargs = {"agnostic": agnosting_nms, "max_det": max_detections}
    preds = ops.non_max_suppression(torch.from_numpy(pred_boxes), min_conf_threshold, nms_iou_threshold, nc=80, **nms_kwargs)

    results = []
    for i, pred in enumerate(preds):
        shape = orig_img[i].shape if isinstance(orig_img, list) else orig_img.shape
        if not len(pred):
            results.append({"det": [], "segment": []})
            continue
        pred[:, :4] = ops.scale_boxes(input_hw, pred[:, :4], shape).round()
        results.append({"det": pred})

    return results

def detect(image:np.ndarray):
    """
    OpenVINO YOLOv8モデル推論機能。画像を前処理し、モデル推論を実行し、NMSを使って結果を後処理する。
    パラメータ
        image (np.ndarray): 入力画像
    戻り値
        detections (np.ndarray): [x1, y1, x2, y2, score, label]の形式で検出されたボックス
    """

    # OVMSサーバとgRPC接続
    client = ovmsclient.make_grpc_client(load_env.OVMS_ENDPOINT)

    # モデルのメタデータからモデルへの入力形式を取得
    model_metadata = client.get_model_metadata(model_name=load_env.MODEL_NAME, timeout=load_env.OVMS_CLIENT_TIMEOUT)

    # モデルに入力が1つしかない場合は、その名前を取得する。
    input_name = next(iter(model_metadata["inputs"]))

    preprocessed_image = letterbox(image)[0]
    input_tensor = np.expand_dims(preprocessed_image, 0)
    inputs = {input_name: input_tensor}
    input_hw = preprocessed_image.shape[:2]

    # OVMSと接続してYolov8による物体検知を実行
    boxes = client.predict(inputs=inputs, model_name=load_env.MODEL_NAME,timeout=load_env.OVMS_CLIENT_TIMEOUT)
    # Yolov8の出力テンソルへ後処理を行い、元の画像サイズへスケールする
    detections = postprocess(pred_boxes=boxes, input_hw=input_hw, orig_img=image)
    return detections


def draw_results(results:Dict, source_image:np.ndarray, label_map:Dict):
    """
    画像にバウンディングボックスを描画するヘルパー関数
    パラメータ
        image_res (np.ndarray): [x1, y1, x2, y2, score, label_id] 形式の検出予測値。
        source_image (np.ndarray): 描画用の入力画像
        label_map; (Dict[int, str]): label_id からクラス名へのマッピング
    戻り値
        ボックスを含む画像
    """
    boxes = results["det"]
    for idx, (*xyxy, conf, lbl) in enumerate(boxes):
        if conf < load_env.CONF:
            continue
        label = f'{label_map[int(lbl)]} {conf:.2f}'
        log.info(label)
        source_image = plot_one_box(xyxy, source_image, label=label, color=colors(int(lbl)), line_thickness=3)
    return source_image