import os
from dotenv import load_dotenv

def read_val_from_dotenv():
    # Load environment variables from .env file
    load_dotenv()

    # Get the value of a specific environment variable
    global OVMS_ENDPOINT
    global MODEL_NAME
    global DEVICE
    global PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION
    global FPS
    global OVMS_CLIENT_TIMEOUT
    global PORT
    global CAPTURE_WAIT_TIME
    global CONF
    global TELLO_IP
    global TELLO_CM_PORT
    global TELLO_VIDEO_PORT
    global TELLO_SLEEP

    OVMS_ENDPOINT = os.getenv('OVMS_ENDPOINT')
    MODEL_NAME = os.getenv('MODEL_NAME')
    DEVICE = os.getenv('DEVICE')
    if DEVICE == '0':
        DEVICE = 0

    FPS = float(os.getenv('FPS'))
    OVMS_CLIENT_TIMEOUT = float(os.getenv('OVMS_CLIENT_TIMEOUT'))
    PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION = os.getenv('PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION')
    PORT = os.getenv('PORT')
    CAPTURE_WAIT_TIME = os.getenv('CAPTURE_WAIT_TIME')
    CONF = float(os.getenv('CONF'))
    TELLO_IP = os.getenv('TELLO_IP')
    TELLO_CM_PORT = int(os.getenv('TELLO_CM_PORT'))
    TELLO_VIDEO_PORT = int(os.getenv('TELLO_VIDEO_PORT'))
    TELLO_SLEEP = int(os.getenv('TELLO_SLEEP'))