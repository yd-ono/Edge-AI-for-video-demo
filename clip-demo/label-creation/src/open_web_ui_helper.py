import requests
import base64

class OpenWebUiHelper():
    TIMEOUT = 30

    def __init__(self, api_key, assistant_id, assistant_name, base_url, timeout=TIMEOUT, verbose=True):
        self.api_key = api_key
        self.assistant_id = assistant_id
        self.assistant_name = assistant_name
        self.base_url = base_url
        self.verbose = verbose
        self.session = requests.Session()
        self.base_headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Accept': 'application/json'
        }    

    # 画像をアップロードした状態で、会話を行う
    def dialogue(self, msg, collection_name):
        # chat_print("user", msg, self.verbose)
        try:
            headers = self.base_headers.copy()
            headers['Content-Type'] = 'application/json'
            payload = {
                "model": f"{self.assistant_id}",
                "messages": [{"role": "user", "content": f"{msg}"}],
                "files": [{"type": "file", "id": f"{collection_name}"}]
            }

            print(f"[DEBUG] Payload: {payload}")

            response = self.session.post(
                f"{self.base_url}/chat/completions",
                headers=headers, json=payload, timeout=self.TIMEOUT
            )
            response.raise_for_status()
            result = response.json()
            print(f'[webui helper] dialogue_with_collection API response:{result}')

            # chat_print(self.assistant_name, answer, self.verbose)
            return  result
        except Exception as e:
            print(f"Chat with collection error: {e}")
            return ""

    # 画像をアップロードして、コレクション名を取得する
    def upload_bytes(self, img_bytes):
        try:
            image_data = base64.b64encode(img_bytes)
            files = {'file': image_data}
            headers = self.base_headers.copy()

            response = self.session.post(
                f"{self.base_url}/v1/files/",
                headers=headers, files=files
            )
            result = response.json()
            collection_name = result.get('meta', {}).get('collection_name', None)
            return collection_name
        except Exception as e:
            print(f"Image Upload error: {e}")
            return ""