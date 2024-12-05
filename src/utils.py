import cv2
import numpy as np
import base64
from datetime import datetime

def extract_frame(frame):
    return cv2.cvtColor(np.array(frame.to_image()), cv2.COLOR_RGB2BGR)

def save_frame(frame, filename):
    cv2.imwrite(filename, frame)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def generate_filename():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"frame_{timestamp}.jpg"