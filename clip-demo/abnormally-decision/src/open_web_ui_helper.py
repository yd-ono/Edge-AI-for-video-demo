import requests
import time
import shutil
import base64
import json
import re
from io import BytesIO


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

    def dialogue(self, msg):
        # chat_print("user", msg, self.verbose)
        try:
            headers = self.base_headers.copy()
            headers['Content-Type'] = 'application/json'
            payload = {
                "model": f"{self.assistant_id}",
                "messages": [{"role": "user", "content": f"{msg}"}]
            }
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                headers=headers, json=payload, timeout=self.TIMEOUT
            )
            response.raise_for_status()
            result = response.json()
            # print(f'[webui helper] dialogue API response:{result}')

            # chat_print(self.assistant_name, answer, self.verbose)
            return  result
        except Exception as e:
            print(f"Chat error: {e}")
            return ""
