import multiprocessing
import time
import logging
import json
from src.stream_receiver import process_stream
from src.ai_interface import send_image_to_ai
from src.utils import save_frame, generate_filename, encode_image
import requests
from src.db_handler import save_analysis_result, save_person_features, get_person_features
from datetime import datetime
import threading
import queue
import cv2

def stream_worker(stream_id, url, status_dict, stop_event, frame_queue, prompt_type='safety'):
    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        status_dict[stream_id] = 'error'
        logging.error(f"Failed to open stream {url}")
        return

    while not stop_event.is_set():
        try:
            status_dict[stream_id] = 'streaming'
            ret, frame = cap.read()
            if not ret:
                status_dict[stream_id] = 'error'
                logging.warning(f"Failed to read frame from stream {url}")
                time.sleep(1)  # 等待1秒后重试
                continue
            
            # 更新最新帧
            try:
                frame_queue.put(frame, block=False)
            except queue.Full:
                try:
                    frame_queue.get_nowait()
                    frame_queue.put(frame, block=False)
                except queue.Empty:
                    pass
            
            time.sleep(0.01)  # 减少睡眠时间，提高帧率
        
        except Exception as e:
            status_dict[stream_id] = 'error'
            logging.error(f"Error in stream worker for {url}: {str(e)}")
            time.sleep(1)  # 出错后等待1秒再重试
        
        if stop_event.is_set():
            break

    cap.release()
    status_dict[stream_id] = 'stopped'

def analyze_frame(frame, source_info, stream_id, prompt_type='safety'):
    try:
        filename = generate_filename()
        save_frame(frame, f"logs/{filename}")
        base64_image = encode_image(f"logs/{filename}")
        
        # 获取数据库中的人员特征数据
        reid_data = get_person_features()
        
        max_retries = 3
        for attempt in range(max_retries):
            analysis_result = send_image_to_ai(base64_image, prompt_type, reid_data, 
                                               stream_manager.ai_model, 
                                               stream_manager.api_key, 
                                               stream_manager.api_base)
            
            if analysis_result is not None:
                break
            
            if attempt < max_retries - 1:
                logging.warning(f"Retrying analysis for {filename} (Attempt {attempt + 2}/{max_retries})")
                time.sleep(5)  # 等待5秒后重试
        
        if analysis_result is None:
            logging.error(f"Failed to get analysis result for {filename} from {source_info} after {max_retries} attempts")
            return

        # 更新 ReID 数据
        if isinstance(analysis_result, dict) and 'people' in analysis_result:
            for person in analysis_result['people']:
                if 'id' in person:
                    person_data = {
                        'id': person['id'],
                        'features': person.get('features', ''),
                        'position': person.get('position', ''),
                        'action': person.get('action', ''),
                        'last_seen': datetime.now().isoformat()
                    }
                    save_person_features(person_data)
        
        # 处理车辆数据（如果需要保存到数据库，可以添加相应的函数）
        if isinstance(analysis_result, dict) and 'vehicles' in analysis_result:
            for vehicle in analysis_result['vehicles']:
                # 这里可以添加保存车辆信息到数据库的逻辑
                pass
        
        logging.info(f"Analysis result for {filename} from {source_info}: {json.dumps(analysis_result, ensure_ascii=False)}")
        
        if prompt_type == 'safety':
            if isinstance(analysis_result, dict):
                if analysis_result.get('violation_detected'):
                    violation_message = f"安全违规警告：在 {filename} 中检测到违规行，来自 {source_info}。描述：{analysis_result.get('description', '无描述')}"
                    logging.info(violation_message)
                else:
                    logging.info(f"No safety violation detected in {filename} from {source_info}")
                
                # 保存分析结果到数据库
                save_analysis_result(stream_id, analysis_result)
        else:
            logging.info(f"Analysis result for {filename} from {source_info}: {analysis_result}")
    
    except Exception as e:
        logging.error(f"Error analyzing frame from {source_info}: {str(e)}")

class StreamManager:
    def __init__(self):
        self.streams = {}  # 存储 stream_id: {'url': url, 'prompt_template': prompt_template}
        self.processes = {}  # 存储 stream_id: Process
        self.manager = None
        self.stream_statuses = None
        self.stop_event = None
        self.analysis_interval = 10  # 将默认分析间隔改为10秒
        self.frame_queues = {}  # 存储 stream_id: Queue
        self.ai_model = None
        self.api_key = None
        self.api_base = None
        self.logger = logging.getLogger(__name__)

    def initialize(self):
        self.manager = multiprocessing.Manager()
        self.stream_statuses = self.manager.dict()
        self.stop_event = multiprocessing.Event()

    def add_stream(self, stream_id, url, prompt_template='DEFAULT_PROMPT_TEMPLATE'):
        self.streams[stream_id] = {
            'url': url, 
            'prompt_template': prompt_template
        }
        self.frame_queues[stream_id] = self.manager.Queue(maxsize=5)  # 增加队列大小
        self.logger.info(f"Added stream: ID: {stream_id}, URL: {url}")
        return True

    def remove_stream(self, stream_id):
        if stream_id in self.streams:
            if stream_id in self.processes:
                process = self.processes[stream_id]
                if isinstance(process, multiprocessing.Process):
                    process.terminate()
                    process.join(timeout=5)  # 给予5秒的时间让进程正常退出
                    if process.is_alive():
                        process.kill()  # 如果进程仍然存活，强制终止
                del self.processes[stream_id]
            del self.streams[stream_id]
            if stream_id in self.stream_statuses:
                del self.stream_statuses[stream_id]
            if stream_id in self.frame_queues:
                del self.frame_queues[stream_id]
            logging.info(f"Removed stream for ID: {stream_id}")
        else:
            logging.warning(f"Stream {stream_id} not found in manager")

    def start_all_streams(self):
        self.stop_event.clear()  # 确保stop_event被清除
        for stream_id, stream_info in self.streams.items():
            if stream_id not in self.processes or not self.processes[stream_id].is_alive():
                self.frame_queues[stream_id] = self.manager.Queue(maxsize=1)
                process = multiprocessing.Process(target=stream_worker, 
                                                  args=(stream_id, stream_info['url'], self.stream_statuses, 
                                                        self.stop_event, self.frame_queues[stream_id]))
                process.start()
                self.processes[stream_id] = process
                logging.info(f"Started stream process for ID: {stream_id}, URL: {stream_info['url']}")
        logging.info(f"Started all streams: {len(self.streams)} streams")

    def stop_all_streams(self):
        self.stop_event.set()
        stop_thread = threading.Thread(target=self._stop_all_streams_thread)
        stop_thread.start()
        return stop_thread

    def _stop_all_streams_thread(self):
        for stream_id, process in self.processes.items():
            if isinstance(process, multiprocessing.Process):
                process.join(10)  # 给予10秒的时间让进程正常退出
                if process.is_alive():
                    logging.warning(f"Stream {stream_id} did not stop gracefully, terminating...")
                    process.terminate()
                    process.join(5)
                    if process.is_alive():
                        logging.error(f"Failed to terminate stream {stream_id}, killing...")
                        process.kill()
        self.processes.clear()
        for queue in self.frame_queues.values():
            while not queue.empty():
                try:
                    queue.get_nowait()
                except queue.Empty:
                    pass
        self.stop_event.clear()
        logging.info("Stopped all streams")

    def get_stream_statuses(self):
        return dict(self.stream_statuses) if self.stream_statuses else {}

    def _analyze_frame(self, frame, source_info):
        analyze_frame(frame, source_info, source_info.split(": ")[1])

    def set_analysis_interval(self, interval):
        self.analysis_interval = interval
        logging.info(f"Analysis interval set to {interval} seconds")

    def analyze_camera_frame(self, frame):
        analyze_frame(frame, "Local Camera", "local_camera")

    def get_latest_frame(self, stream_id):
        if stream_id not in self.streams:
            self.logger.error(f"Stream ID {stream_id} not found")
            return None

        if stream_id not in self.frame_queues:
            self.logger.error(f"Frame queue for stream ID {stream_id} not found")
            return None

        try:
            return self.frame_queues[stream_id].get(block=False)
        except queue.Empty:
            return None

    def analyze_frame(self, stream_id):
        frame = self.get_latest_frame(stream_id)
        if frame is not None:
            source_info = f"Stream: {self.streams[stream_id]['url']}"
            prompt_template = self.streams[stream_id]['prompt_template']
            threading.Thread(target=analyze_frame, args=(frame, source_info, stream_id, prompt_template)).start()
        else:
            self.logger.error(f"Failed to get frame for analysis from stream {stream_id}")

    def set_prompt_template(self, template):
        self.prompt_template = template
        logging.info("Prompt template updated")

    def set_ai_config(self, model, api_key, api_base):
        self.ai_model = model
        self.api_key = api_key
        self.api_base = api_base
        logging.info("AI model configuration updated")

stream_manager = StreamManager()
