import json
import paho.mqtt.client as mqtt
from open_web_ui_helper import OpenWebUiHelper
from keys_openwebui import OPEN_WEB_UI_API_KEY, OPEN_WEB_UI_ASSISTANT_ID, OPEN_WEB_UI_BASE_URL

# ==== 初期化 ====
open_web_ui_helper = OpenWebUiHelper(
    OPEN_WEB_UI_API_KEY,
    OPEN_WEB_UI_ASSISTANT_ID,
    'clip-assistant',
    OPEN_WEB_UI_BASE_URL
)

# ========== MQTT 設定 ==========
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
TOPIC_SUB = "clip/inference"
TOPIC_PUB = "pidog/action"

# ========== MQTT コールバック ==========
def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT broker with result code " + str(rc))
    client.subscribe(TOPIC_SUB)

# = MQTT メッセージ受信時の処理 ==========
def on_message(client, userdata, msg):
    try:
        print(f"[MQTT] Received on {msg.topic}: {msg.payload.decode()}")

        # MQTTメッセージをデコード
        payload = json.loads(msg.payload.decode())

        # 推論結果を取得  
        label_scores = payload.get("results", [])
        if not label_scores:
            print("[WARNING] Empty results.")
            return

        # 推論結果をプロンプトに変換
        prompt = "以下の推論結果から、PiDogが取るべき行動を教えてください。DSLで答えてください：\n"
        for item in label_scores:
            prompt += f"- {item['label']}（スコア: {item['score']}）\n"

        print(f"[PROMPT] {prompt}")

        # Open Web UI に問い合わせ
        response = open_web_ui_helper.dialogue(prompt)
        if response:
            answer = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"[OpenWebUI] Answer: {answer}")

            # MQTTでPiDogへ行動指示
            client.publish(TOPIC_PUB, json.dumps({"action": answer}))
            print(f"[MQTT] Published to {TOPIC_PUB}: {answer}")
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
print("Starting PiDog Action Agent...")
client.loop_forever()