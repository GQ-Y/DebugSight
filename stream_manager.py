import cv2
import logging

class StreamManager:
    def __init__(self):
        self.streams = {}
        self.captures = {}
        self.logger = logging.getLogger(__name__)

    def add_stream(self, stream_id, url, prompt_template='DEFAULT_PROMPT_TEMPLATE'):
        try:
            self.logger.info(f"尝试添加流 {stream_id}，URL: {url}")
            
            # 检查流是否已存在
            if stream_id in self.streams:
                self.logger.warning(f"流 {stream_id} 已存在，正在尝试重新初始化")
                if stream_id in self.captures:
                    self.captures[stream_id].release()
                    del self.captures[stream_id]
            
            self.streams[stream_id] = {'url': url, 'prompt_template': prompt_template}
            
            # 初始化视频捕获
            self.logger.info(f"正在初始化视频流，URL: {url}")
            cap = cv2.VideoCapture(url)
            
            if not cap.isOpened():
                raise Exception(f"无法打开流: {url}")
            
            # 尝试读取一帧以确保流是可用的
            ret, frame = cap.read()
            if not ret or frame is None or frame.size == 0:
                raise Exception(f"无法从流 {url} 读取有效帧")
            
            self.captures[stream_id] = cap
            self.logger.info(f"成功添加流 {stream_id}")
            return True
        except Exception as e:
            self.logger.error(f"添加流 {stream_id} 失败: {str(e)}")
            if stream_id in self.streams:
                del self.streams[stream_id]
            if stream_id in self.captures:
                self.captures[stream_id].release()
                del self.captures[stream_id]
            return False

    def get_latest_frame(self, stream_id):
        try:
            cap = self.captures.get(stream_id)
            if cap is None:
                raise Exception(f"未找到流 {stream_id} 的捕获对象")
            
            # 尝试多次读取帧
            for _ in range(3):
                ret, frame = cap.read()
                if ret and frame is not None and frame.size > 0:
                    return frame
            
            raise Exception(f"无法从流 {stream_id} 读取有效帧")
        except Exception as e:
            self.logger.error(f"获取流 {stream_id} 的最新帧失败: {str(e)}")
            return None

    # 移除 check_camera_status 方法

    # ... 其他方法 ...