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
    global DRONE_VIDEO
    global TELLO_INIT_WAIT_TIME
    global TELLO_STREAM_WAIT_TIME

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
    DRONE_VIDEO = int(os.getenv('DRONE_VIDEO'))
    TELLO_INIT_WAIT_TIME = int(os.getenv('TELLO_INIT_WAIT_TIME'))
    TELLO_STREAM_WAIT_TIME = int(os.getenv('TELLO_STREAM_WAIT_TIME'))