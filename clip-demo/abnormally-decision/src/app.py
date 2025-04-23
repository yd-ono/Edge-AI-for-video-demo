import json
import paho.mqtt.client as mqtt
from open_web_ui_helper import OpenWebUiHelper
import os
import re

# ==== 設定 ====
OPEN_WEB_UI_API_KEY = os.getenv("OPEN_WEB_UI_API_KEY", "sk-1124e6c512ef4175b9ea60f4c94a37b7")
OPEN_WEB_UI_ASSISTANT_ID = os.getenv("OPEN_WEB_UI_ASSISTANT_ID", "abnormal-detection")
OPEN_WEB_UI_BASE_URL = os.getenv("OPEN_WEB_UI_BASE_URL", "http://localhost:3000/api")
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
TOPIC_SUB = "clip/result"
TOPIC_PUB = "abnormality/decision"

# ==== 初期化 ====
open_web_ui_helper = OpenWebUiHelper(
    OPEN_WEB_UI_API_KEY,
    OPEN_WEB_UI_ASSISTANT_ID,
    'clip-assistant',
    OPEN_WEB_UI_BASE_URL
)

# ========== MQTT コールバック ==========
def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT broker with result code " + str(rc))
    client.subscribe(TOPIC_SUB)

# =========== JSONでパブリッシュ ============
def publish_decision(result: int, reason: str):
    message = json.dumps({"result": result, "reason": reason}, ensure_ascii=False)
    try:
        client.publish(TOPIC_PUB, payload=message.encode('utf-8'))
        print(f"[MQTT] Published to {TOPIC_PUB}: {message}")
    except Exception as e:
        print(f"[ERROR] Failed to publish decision: {e}")

# = MQTT メッセージ受信時の処理 ==========
def on_message(client, userdata, msg):
    try:
        prompt = json.loads(msg.payload.decode())
        response = open_web_ui_helper.dialogue(prompt)
        if response:
            answer = response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

            # 明示的な JSONブロックの抽出（markdown形式も含む）
            json_block_match = re.search(r'({\s*"result"\s*:\s*\d+\s*,\s*"reason"\s*:\s*".*?"\s*})', answer, re.DOTALL)
            if json_block_match:
                cleaned_answer = json_block_match.group(1)
                try:
                    parsed = json.loads(cleaned_answer)
                    result = parsed.get("result")
                    reason = parsed.get("reason")
                    if isinstance(result, int) and isinstance(reason, str):
                        publish_decision(result, reason)
                        return
                except json.JSONDecodeError:
                    pass

            # fallback: 構文的にJSONとしては不明確な場合、rawをログ出し
            client.publish(TOPIC_PUB, json.dumps({
                "result": -1,
                "reason": "Failed to parse valid JSON from LLM response",
                "raw": answer
            }, ensure_ascii=False))
            print(f"[MQTT] Published fallback (raw text) to {TOPIC_PUB}: {answer}")
        else:
            print("[ERROR] No response from Open Web UI")

    except Exception as e:
        print(f"[ERROR] Exception in on_message: {e}")


# ========== MQTT クライアント設定 ==========
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_BROKER, MQTT_PORT, 60)

# ========== 実行 ==========
def main_loop():
    print("Starting PiDog Action Agent...")
    client.loop_forever()

if __name__ == "__main__":
    main_loop()