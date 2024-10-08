import requests
from PIL import Image
from io import BytesIO
import logging
import datetime
import load_env
from flask import Flask, render_template, Response

# Loggerを初期化
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s",
                    level=logging.INFO)
log = logging.getLogger(__name__)

load_env.read_val_from_dotenv()

def save_image_from_response(url, save_path):
    try:
        response = requests.get(url)
        if response.status_code == 200:
            image = Image.open(BytesIO(response.content))
            image.save(save_path)
            log.info("Image saved successfully!")
        else:
            log.error("Failed to retrieve image. Status code:", response.status_code)
    except Exception as e:
        log.error("An error occurred:", str(e))

if __name__ == "__main__":
    url = load_env.APP_SERVER + "/save_image"
    save_path = "images/" + datetime.datetime.now().strftime('%Y%m%d%H%M%S')+ "-image.jpg"
    save_image_from_response(url, save_path)