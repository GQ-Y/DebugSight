import cv2
import time
import logging
import os

# 设置 OpenCV 的读取尝试次数
os.environ['OPENCV_FFMPEG_READ_ATTEMPTS'] = '50000'  # 增加到 50000 次尝试

def process_stream(url):
    retry_count = 0
    max_retries = 5
    while retry_count < max_retries:
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            logging.error(f"Cannot open video stream: {url}")
            retry_count += 1
            time.sleep(2)  # 等待2秒后重试
            continue

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    logging.warning(f"Failed to read frame from stream: {url}")
                    break
                yield frame
            
            # 如果正常退出循环，重置重试计数
            retry_count = 0
        except cv2.error as e:
            logging.error(f"OpenCV error: {str(e)}")
            retry_count += 1
        finally:
            cap.release()

        if retry_count < max_retries:
            logging.info(f"Attempting to reconnect to stream: {url}")
            time.sleep(2)  # 等待2秒后重试
        else:
            logging.error(f"Max retries reached for stream: {url}")
            break