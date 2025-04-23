import time
import requests
import os
from open_web_ui_helper import OpenWebUiHelper
import json
import re

# ==== 設定 ====
SNAPSHOT_URL = os.getenv("SNAPSHOT_URL", "http://localhost:9000/snapshot")
SET_LABELS_URL = os.getenv("SET_LABELS_URL", "http://localhost:9000/set_labels")
INTERVAL = int(os.getenv("INTERVAL", "1"))  # 秒ごとの間隔
OPEN_WEB_UI_API_KEY = os.getenv("OPEN_WEB_UI_API_KEY", "sk-1124e6c512ef4175b9ea60f4c94a37b7")
OPEN_WEB_UI_ASSISTANT_ID = os.getenv("OPEN_WEB_UI_ASSISTANT_ID", "clip-assistant")
OPEN_WEB_UI_BASE_URL = os.getenv("OPEN_WEB_UI_BASE_URL", "http://localhost:3000/api")


# ==== 初期化 ====
open_web_ui_helper = OpenWebUiHelper(
    OPEN_WEB_UI_API_KEY,
    OPEN_WEB_UI_ASSISTANT_ID,
    'clip-assistant',
    OPEN_WEB_UI_BASE_URL
)

# ==== ヘルパー関数 ====
# スナップショットを取得する
# 取得したスナップショットはバイト列として返す
# 例: http://localhost:8888/snapshot
def get_snapshot_bytes():
    response = requests.get(SNAPSHOT_URL)
    if response.status_code == 200:
        return response.content  # バイト列として返す
    else:
        raise RuntimeError(f"Snapshot取得に失敗: {response.status_code}")

# CLIPへラベルを送信する
# 例: http://localhost:8888/set_labels
# 送信するラベルはリスト形式で渡す
# 例: ["label1", "label2"]
# 送信するラベルはカンマ区切りの文字列として渡す
# 例: "label1,label2"
# 送信するラベルが空の場合は、何もしない

def post_labels_to_clip(labels):
    if not labels:
        print("[WARN] ラベルが空です。送信をスキップします。")
        return

    try:
        # ラベルをカンマ区切りの文字列に変換
        # 例: ["label1", "label2"] -> "label1,label2"
        label_str = ",".join(labels)

        # CLIPへラベルを送信
        # 例: http://localhost:8888/set_labels
        # 送信するラベルはカンマ区切りの文字列として渡す
        # 例: "label1,label2"
        response = requests.post(SET_LABELS_URL, json={"labels": label_str})
        if response.status_code == 200:
            print("[OK] CLIPラベルを正常に更新しました。")
        else:
            print(f"[WARN] ラベル送信失敗: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"[ERROR] ラベル送信中に例外発生: {e}")

# メインループ
# スナップショットを取得し、OpenWebUIにアップロード
# 取得したスナップショットをOpenWebUIにアップロードし、JSON応答を取得
# JSON応答からラベルを抽出し、CLIPへ送信
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
                    # マッチした部分をJSONとしてパース
                    json_text = match.group(1)
                else:
                    # fallback: 最初の { から最後の } まで
                    start = content.find("{")
                    end = content.rfind("}")

                    # マッチしなかった場合は、最初の { から最後の } までを取得
                    json_text = content[start:end+1]

                # JSONパース
                # 例: {"labels": ["label1", "label2"], "scene": "scene description", "actions": ["action1", "action2"], "answer": "answer text"}
                parsed = json.loads(json_text)

                # 必要な情報を抽出
                # 例: {"labels": ["label1", "label2"], "scene": "scene description", "actions": ["action1", "action2"], "answer": "answer text"}
                labels = parsed.get("labels", [])

                # ラベルが空の場合は、何もしない
                scene = parsed.get("scene", "")

                # アクションを取得
                # 例: ["action1", "action2"]
                # アクションは使用しないので、無視する
                # 例: {"labels": ["label1", "label2"], "scene": "scene description", "actions": ["action1", "action2"], "answer": "answer text"}
                actions = parsed.get("actions", [])

                # アンサーを取得
                # 例: {"labels": ["label1", "label2"], "scene": "scene description", "actions": ["action1", "action2"], "answer": "answer text"}
                # アンサーは使用しないので、無視する
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
