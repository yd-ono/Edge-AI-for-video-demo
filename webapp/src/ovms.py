import os
import cv2
import json
import logging
import numpy as np
import requests
import ovmsclient
import time
from typing import Dict

import load_env

# ========= LOG =========
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
log = logging.getLogger("OVMS-YOLOv8")

load_env.read_val_from_dotenv()
def _get_env(name, default):
    v = getattr(load_env, name, None)
    return str(v) if v is not None else os.getenv(name, default)

# ========= ENV =========
PROTOCOL  = _get_env("OVMS_PROTOCOL", "grpc").lower()
ENDPOINT  = _get_env("OVMS_ENDPOINT", "localhost:9000")
MODEL     = _get_env("MODEL_NAME", "yolov8")
REST_MODE = _get_env("OVMS_REST_MODE", "binary").lower()
CONF      = float(_get_env("CONF", "0.25"))
TIMEOUT   = float(_get_env("OVMS_CLIENT_TIMEOUT", "5"))
RETRY_SEC = float(_get_env("OVMS_CONNECT_RETRY", "3"))  # ★ retry間隔（追加）

# PORT autofix for REST
if PROTOCOL == "rest":
    if ENDPOINT.endswith("32290"):
        ENDPOINT = ENDPOINT[:-5] + "32299"
    if not ENDPOINT.startswith("http"):
        ENDPOINT = f"http://{ENDPOINT}"

# ========= Client cache =========
_g=None; _gin=None
_rs=None; _url=None


# ================== Letterbox ==================
def letterbox(img,new=(640,640)):
    h,w = img.shape[:2]
    r=min(new[0]/h,new[1]/w)
    nh,nw=int(h*r),int(w*r)
    im=cv2.resize(img,(nw,nh))
    top=(new[0]-nh)//2; bottom=new[0]-nh-top
    left=(new[1]-nw)//2; right=new[1]-nw-left
    return cv2.copyMakeBorder(im,top,bottom,left,right,cv2.BORDER_CONSTANT,(114,114,114))


# ================== NMS ==================
def nms(det,iou_thr=0.55,max_det=100):
    if det is None or len(det)==0: return det
    det=det[np.argsort(-det[:,4])]
    keep=[]
    while len(det)>0:
        m=det[0]; keep.append(m)
        if len(keep)>=max_det: break
        rest=det[1:]
        xx1=np.maximum(m[0],rest[:,0]); yy1=np.maximum(m[1],rest[:,1])
        xx2=np.minimum(m[2],rest[:,2]); yy2=np.minimum(m[3],rest[:,3])
        inter=np.maximum(0,xx2-xx1)*np.maximum(0,yy2-yy1)
        a1=(m[2]-m[0])*(m[3]-m[1]); a2=(rest[:,2]-rest[:,0])*(rest[:,3]-rest[:,1])
        iou=inter/(a1+a2-inter+1e-9)
        det=rest[iou<iou_thr]
    return np.array(keep,dtype=np.float32)


# ================== PostProcess ==================
def post(raw,img):
    p=np.array(raw,dtype=np.float32)
    if p.ndim==3: p=p.squeeze(0)
    if p.shape[0]<p.shape[1]: p=p.T
    xywh=p[:,:4]; xyxy=np.zeros_like(xywh)
    xyxy[:,0]=xywh[:,0]-xywh[:,2]/2; xyxy[:,1]=xywh[:,1]-xywh[:,3]/2
    xyxy[:,2]=xywh[:,0]+xywh[:,2]/2; xyxy[:,3]=xywh[:,1]+xywh[:,3]/2
    cls=np.argmax(p[:,4:],1); score=np.max(p[:,4:],1)
    det=np.column_stack((xyxy,score,cls))
    det=det[det[:,4]>CONF]
    if len(det): det=nms(det,0.55)
    h0,w0=img.shape[:2]; gain=min(640/h0,640/w0)
    padw=(640-w0*gain)/2; padh=(640-h0*gain)/2
    det[:,[0,2]]-=padw; det[:,[1,3]]-=padh; det[:,:4]/=gain
    det[:,0]=det[:,0].clip(0,w0);det[:,2]=det[:,2].clip(0,w0)
    det[:,1]=det[:,1].clip(0,h0);det[:,3]=det[:,3].clip(0,h0)
    return det.astype(np.float32)


# ==========================================================
# 🔥 gRPC + REST 自動再接続＆fail recover
# ==========================================================
def _grpc(img):
    global _g,_gin
    while True:
        try:
            if _g is None:
                tgt = ENDPOINT.replace("http://","").replace("https://","")
                log.info(f"[gRPC connect] {tgt}")
                _g=ovmsclient.make_grpc_client(tgt)
                meta=_g.get_model_metadata(model_name=MODEL,timeout=TIMEOUT)
                _gin = next(iter(meta["inputs"].keys()))
                log.info(f"[connected] input={_gin}")

            blob=letterbox(img); inp=np.expand_dims(blob,0)
            out=_g.predict({_gin:inp},model_name=MODEL,timeout=TIMEOUT)
            raw = list(out.values())[0] if isinstance(out,dict) else out
            return {"det":post(raw,img)}

        except Exception as e:
            log.error(f"[gRPC error] {e} → retrying in {RETRY_SEC}s")
            _g=None
            time.sleep(RETRY_SEC)


def _rest(img):
    global _rs,_url
    while True:
        try:
            if _rs is None:
                _rs=requests.Session()
                _url=f"{ENDPOINT}/v2/models/{MODEL}/infer"
                log.info(f"[REST connect] {_url}")

            blob=letterbox(img)
            inp=np.expand_dims(blob,0).astype("uint8")
            header={"inputs":[{"name":"images","shape":list(inp.shape),"datatype":"UINT8","parameters":{"binary_data_size":inp.nbytes}}]}
            body=json.dumps(header).encode()+inp.tobytes()

            r=_rs.post(_url,data=body,headers={"Content-Type":"application/octet-stream","Inference-Header-Content-Length":str(len(json.dumps(header)))},timeout=TIMEOUT)
            o=r.json()["outputs"][0]
            data=np.array(o["data"],dtype=np.float32).reshape(o["shape"])
            return {"det":post(data,img)}

        except Exception as e:
            log.error(f"[REST error] {e} → retry in {RETRY_SEC}s")
            _rs=None
            time.sleep(RETRY_SEC)


# ================== API ==================
def detect(img):  
    return _rest(img) if PROTOCOL=="rest" else _grpc(img)


# ================== Draw ==================
def draw_results(res, img, labels):
    det=res.get("det",None)
    if det is None or len(det)==0: return img
    for (x1,y1,x2,y2,s,c) in det:
        if s<CONF: continue
        cv2.rectangle(img,(int(x1),int(y1)),(int(x2),int(y2)),(0,255,0),3)
        text=f"{labels[int(c)]} {s:.2f}"
        ts=cv2.getTextSize(text,cv2.FONT_HERSHEY_SIMPLEX,0.7,2)[0]
        tx=int(x1); ty=max(int(y1)-5,ts[1]+5)
        cv2.rectangle(img,(tx,ty-ts[1]-6),(tx+ts[0]+6,ty+2),(0,255,0),-1)
        cv2.putText(img,text,(tx+3,ty-3),cv2.FONT_HERSHEY_SIMPLEX,0.7,(0,0,0),2)
    return img
