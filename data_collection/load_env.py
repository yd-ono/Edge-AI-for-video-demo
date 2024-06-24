import os
from dotenv import load_dotenv

def read_val_from_dotenv():
    # Load environment variables from .env file
    load_dotenv()

    # Get the value of a specific environment variable
    global APP_SERVER

    APP_SERVER = os.getenv('APP_SERVER')