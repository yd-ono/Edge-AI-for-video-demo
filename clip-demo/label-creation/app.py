import time
import requests
import os
from open_web_ui_helper import OpenWebUiHelper
from keys_openwebui import OPEN_WEB_UI_API_KEY, OPEN_WEB_UI_ASSISTANT_ID, OPEN_WEB_UI_BASE_URL
from io import BytesIO
import json
import re

# ==== 設定 ====
SNAPSHOT_URL = os.getenv("SNAPSHOT_URL", "http://localhost:8888/snapshot")
SET_LABELS_URL = os.getenv("SET_LABELS_URL", "http://localhost:8888/set_labels")
INTERVAL = int(os.getenv("INTERVAL", "1"))  # 秒ごとの間隔

# ==== 初期化 ====
open_web_ui_helper = OpenWebUiHelper(
    OPEN_WEB_UI_API_KEY,
    OPEN_WEB_UI_ASSISTANT_ID,
    'clip-assistant',
    OPEN_WEB_UI_BASE_URL
)

def get_snapshot_bytes():
    response = requests.get(SNAPSHOT_URL)
    if response.status_code == 200:
        return response.content  # バイト列として返す
    else:
        raise RuntimeError(f"Snapshot取得に失敗: {response.status_code}")

def post_labels_to_clip(labels):
    if not labels:
        print("[WARN] ラベルが空です。送信をスキップします。")
        return

    try:
        label_str = ",".join(labels)
        response = requests.post(SET_LABELS_URL, json={"labels": label_str})
        if response.status_code == 200:
            print("[OK] CLIPラベルを正常に更新しました。")
        else:
            print(f"[WARN] ラベル送信失敗: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[ERROR] ラベル送信中に例外発生: {e}")

def main_loop():
    while True:
        try:
            print("[INFO] Snapshot取得...")
            img_bytes = get_snapshot_bytes()

            print("[INFO] OpenWebUIへ画像アップロード & JSON応答取得...")
            collection_name = open_web_ui_helper.upload_bytes(img_bytes)
            if not collection_name:
                raise RuntimeError("画像アップロード失敗")

            prompt = (
                "Please return only a valid JSON block enclosed in triple backticks using json as the language label. "
                "Do not add any explanation or extra text before or after."
            )
            response_json = open_web_ui_helper.dialogue(prompt, collection_name)

            if not isinstance(response_json, dict):
                print("[ERROR] OpenWebUIから有効な応答がありません")
                continue

            content = response_json.get("choices", [{}])[0].get("message", {}).get("content", "")

            try:
                # ```json ... ``` の中身だけ抽出
                match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
                if match:
                    json_text = match.group(1)
                else:
                    # fallback: 最初の { から最後の } まで
                    start = content.find("{")
                    end = content.rfind("}")
                    json_text = content[start:end+1]

                parsed = json.loads(json_text)
                labels = parsed.get("labels", [])
                scene = parsed.get("scene", "")
                actions = parsed.get("actions", [])
                answer = parsed.get("answer", "")

                print(f"[INFO] シーン: {scene}")
                print(f"[INFO] ラベル: {labels}")
                print(f"[INFO] アンサー: {answer}")

                # ラベルをCLIPへ送信
                post_labels_to_clip(labels)

            except Exception as e:
                print(f"[ERROR] JSONパース失敗: {e}")
                print(f"[DEBUG] content: {content}")

        except Exception as e:
            print(f"[ERROR] 処理中にエラーが発生: {e}")

        print(f"[INFO] {INTERVAL}秒後に再試行します...\n")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main_loop()
