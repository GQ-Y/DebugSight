from PyQt5.QtCore import QObject

class AppDelegate(QObject):
    def __init__(self):
        super().__init__()

    def applicationSupportsSecureRestorableState_(self, app):
        return True

import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, 
                             QComboBox, QLabel, QTextEdit, QTableWidget, QTableWidgetItem, QDialog, QDialogButtonBox, 
                             QMessageBox, QCheckBox, QFormLayout, QSpinBox, QStyleFactory, QGridLayout, QSystemTrayIcon, 
                             QMenu, QAction, QDesktopWidget, QGroupBox, QInputDialog, QTabWidget)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import QPalette, QColor, QImage, QPixmap, QIcon
from src.db_handler import init_db, add_stream, remove_stream, get_all_streams, update_db_structure
from src.stream_manager import StreamManager
import logging
import json
import time
import threading
import subprocess
import psutil
import os
import cv2
from utils import resource_path
from PIL import Image
import io
import base64
from datetime import datetime
from src.ai_interface import send_image_to_ai, AIInterface

def update_ai_config_from_default():
    try:
        with open(resource_path('ai_config.json'), 'r') as f:
            ai_config = json.load(f)
    except FileNotFoundError:
        ai_config = {
            "ai_model": "your_default_model",
            "api_key": "your_default_api_key",
            "api_base": "your_default_api_base"
        }
        with open(resource_path('ai_config.json'), 'w') as f:
            json.dump(ai_config, f, indent=2)
    
    return ai_config

# 添加这个函数来加载提示词模板
def load_prompt_templates():
    try:
        with open(resource_path('prompt_templates.json'), 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"DEFAULT_PROMPT_TEMPLATE": "默认提示词模板"}

# 添加以下函数来加载 AI 配置
def load_ai_config():
    try:
        with open(resource_path('ai_config.json'), 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"ai_model": "", "api_key": "", "api_base": ""}

class LogHandler(logging.Handler):
    def __init__(self, run_signal, error_signal):
        super().__init__()
        self.run_signal = run_signal
        self.error_signal = error_signal

    def emit(self, record):
        msg = self.format(record)
        if record.levelno >= logging.CRITICAL:
            self.error_signal.emit(msg)
        else:
            self.run_signal.emit(msg)

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setGeometry(200, 200, 400, 400)
        
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        # 创建标签页
        self.tab_widget = QTabWidget()
        self.layout.addWidget(self.tab_widget)
        
        # 常规设置标签页
        general_tab = QWidget()
        general_layout = QFormLayout()
        general_tab.setLayout(general_layout)
        
        # 移除摄像头相关设置
        self.analysis_interval = QSpinBox()
        self.analysis_interval.setMinimum(1)
        self.analysis_interval.setMaximum(60)
        general_layout.addRow("分析间隔 (秒):", self.analysis_interval)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["跟随系统", "深色", "浅色"])
        general_layout.addRow("主题:", self.theme_combo)
        
        self.tab_widget.addTab(general_tab, "常规设置")
        
        # AI模型设置标签页
        ai_tab = QWidget()
        ai_layout = QFormLayout()
        ai_tab.setLayout(ai_layout)
        
        self.ai_model = QLineEdit()
        ai_layout.addRow("AI模型:", self.ai_model)
        
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        ai_layout.addRow("API密钥:", self.api_key)
        
        self.api_base = QLineEdit()
        ai_layout.addRow("API基础URL:", self.api_base)
        
        self.tab_widget.addTab(ai_tab, "AI模型设置")
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.layout.addWidget(button_box)
        
        self.load_settings()
    
    def load_settings(self):
        try:
            with open(resource_path('settings.json'), 'r') as f:
                settings = json.load(f)
            self.analysis_interval.setValue(settings.get('analysis_interval', 3))
            self.theme_combo.setCurrentText(settings.get('theme', '跟随系统'))
            
            # 加载 AI 模型设置
            ai_config = update_ai_config_from_default()
            self.ai_model.setText(ai_config.get('ai_model', ''))
            self.api_key.setText(ai_config.get('api_key', ''))
            self.api_base.setText(ai_config.get('api_base', ''))
        except FileNotFoundError:
            pass
    
    def save_settings(self):
        settings = {
            'analysis_interval': self.analysis_interval.value(),
            'theme': self.theme_combo.currentText(),
        }
        with open(resource_path('settings.json'), 'w') as f:
            json.dump(settings, f)

        # 保存 AI 模型设置
        ai_config = {
            'ai_model': self.ai_model.text(),
            'api_key': self.api_key.text(),
            'api_base': self.api_base.text()
        }
        with open(resource_path('ai_config.json'), 'w') as f:
            json.dump(ai_config, f, indent=2)

    def accept(self):
        self.save_settings()
        super().accept()

class VideoThread(QThread):
    change_pixmap_signal = pyqtSignal(QImage)
    error_signal = pyqtSignal(str)

    def __init__(self, stream_manager, source, is_camera=False):
        super().__init__()
        self.stream_manager = stream_manager
        self.source = source
        self.is_camera = is_camera
        self._run_flag = True
        self.logger = logging.getLogger(__name__)
        self.last_frame_time = time.time()
        self.retry_count = 0
        self.max_retries = 20
        self.retry_interval = 0.5  # 减少重试间隔

    def run(self):
        self.logger.info(f"VideoThread started for source: {self.source}")
        while self._run_flag:
            try:
                frame = self.stream_manager.get_latest_frame(self.source)
                if frame is not None:
                    rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = rgb_image.shape
                    bytes_per_line = ch * w
                    convert_to_Qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
                    p = convert_to_Qt_format.scaled(320, 240, Qt.KeepAspectRatio)
                    self.change_pixmap_signal.emit(p)
                    self.retry_count = 0  # 重置重试计数
                else:
                    self.retry_count += 1
                    if self.retry_count > self.max_retries:
                        self.error_signal.emit(f"无法获取源 {self.source} 的帧，已重试 {self.max_retries} 次")
                        break
                    time.sleep(self.retry_interval)  # 等待后重试
            except Exception as e:
                self.logger.error(f"Error in VideoThread for source {self.source}: {str(e)}")
                self.error_signal.emit(f"视频线程错误 (源 {self.source}): {str(e)}")
                self.retry_count += 1
                if self.retry_count > self.max_retries:
                    break
                time.sleep(self.retry_interval)  # 等待后重试

            time.sleep(0.01)  # 减少睡眠时间，提高帧率

        self.logger.info(f"VideoThread stopped for source: {self.source}")

    def stop(self):
        self._run_flag = False
        self.wait()

class StopProcessingThread(QThread):
    finished = pyqtSignal()

    def __init__(self, stream_manager):
        super().__init__()
        self.stream_manager = stream_manager

    def run(self):
        stop_thread = self.stream_manager.stop_all_streams()
        stop_thread.join()
        self.finished.emit()

class CameraTestWindow(QWidget):
    def __init__(self, camera_index):
        super().__init__()
        self.camera_index = camera_index
        self.setWindowTitle("摄像头测试")
        self.setGeometry(100, 100, 640, 480)
        
        layout = QVBoxLayout()
        self.label = QLabel()
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.capture = cv2.VideoCapture(self.camera_index)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)  # 更新频率约33FPS

    def update_frame(self):
        ret, frame = self.capture.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qt_image)
            self.label.setPixmap(pixmap)

    def closeEvent(self, event):
        self.capture.release()
        event.accept()

class FullScreenImageViewer(QWidget):
    def __init__(self, pixmap):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.showFullScreen()
        
        layout = QVBoxLayout()
        self.setLayout(layout)
        
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label)
        
        self.set_image(pixmap)
    
    def set_image(self, pixmap):
        screen_size = QApplication.desktop().screenGeometry()
        scaled_pixmap = pixmap.scaled(screen_size.width(), screen_size.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled_pixmap)
    
    def mouseReleaseEvent(self, event):
        self.close()

class MainWindow(QMainWindow):
    run_log_signal = pyqtSignal(str)
    error_log_signal = pyqtSignal(str)
    update_analysis_count_signal = pyqtSignal(int)
    update_image_signal = pyqtSignal(str)
    update_analysis_result_signal = pyqtSignal(str)
    log_signal = pyqtSignal(str, int)
    update_detailed_info_signal = pyqtSignal(str, str, str, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("GAI Video")
        self.setGeometry(100, 100, 800, 600)

        # 设置应用程序的工具提示
        self.setToolTip("GAI Video")

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QGridLayout(self.central_widget)

        # 初始化设置相关的属性
        self.analysis_interval = 3
        self.theme = '跟随系统'

        self.init_ui()
        self.stream_manager = StreamManager()
        self.stream_manager.initialize()
        self.load_existing_streams()
        self.load_settings()  # 加载设置
        self.log(f"初始设置加载完成。")

        self.run_log_signal.connect(self.append_run_log)
        self.error_log_signal.connect(self.append_error_log)

        # 设置日志处理
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        handler = LogHandler(self.run_log_signal, self.error_log_signal)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        self.stream_thread = None
        self.is_processing = False

        # 应用当前系统主题
        self.apply_theme('跟随系统')

        # 创建系统托盘图标
        self.create_tray_icon()

        self.center()  # 在初始化结束时调用 center 方法

        self.ai_config = update_ai_config_from_default()
        self.ai_model = self.ai_config['ai_model']
        self.api_key = self.ai_config['api_key']
        self.api_base = self.ai_config['api_base']

        self.ensure_image_directory()

        self.is_analyzing_images = False
        self.image_analysis_stop_event = threading.Event()

        # 在 MainWindow 类的 __init__ 方法中添加：
        self.total_analysis_count = 0

        self.ai_interface = AIInterface(self.api_key, self.api_base, self.ai_model)

        # 连接信号到相应的槽
        self.update_analysis_count_signal.connect(self.update_analysis_count_slot)
        self.update_image_signal.connect(self.display_analysis_image)
        self.update_analysis_result_signal.connect(self.display_analysis_result)
        self.log_signal.connect(self.log_slot)
        self.update_detailed_info_signal.connect(self.update_detailed_info_slot)

    def center(self):
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def init_ui(self):
        # 侧布局
        left_layout = QVBoxLayout()

        # 添加视频流部分
        add_stream_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("输入RTSP/RTMP流地址")
        
        self.prompt_template_combo = QComboBox()
        self.update_prompt_template_combo()
        
        add_button = QPushButton("添加视频流")
        add_button.clicked.connect(self.add_stream)
        
        add_stream_layout.addWidget(self.url_input)
        add_stream_layout.addWidget(self.prompt_template_combo)
        add_stream_layout.addWidget(add_button)
        left_layout.addLayout(add_stream_layout)

        # 视频流列表
        self.streams_table = QTableWidget()
        self.streams_table.setColumnCount(4)
        self.streams_table.setHorizontalHeaderLabels(["ID", "URL", "添加间", "操作"])
        left_layout.addWidget(self.streams_table)
        self.update_streams_table()

        # 功能按钮
        buttons_layout = QHBoxLayout()
        self.start_stop_button = QPushButton("开始处理视频流")
        self.start_stop_button.clicked.connect(self.toggle_stream_processing)
        buttons_layout.addWidget(self.start_stop_button)
        
        settings_button = QPushButton("设置")
        settings_button.clicked.connect(self.show_settings_dialog)
        buttons_layout.addWidget(settings_button)
        
        # 添加摄像头测试按钮
        test_camera_button = QPushButton("测试摄像")
        test_camera_button.clicked.connect(self.test_camera)
        buttons_layout.addWidget(test_camera_button)
        
        # 修改图集分析按钮
        self.analyze_images_button = QPushButton("启动图集分析")
        self.analyze_images_button.clicked.connect(self.toggle_image_analysis)
        buttons_layout.addWidget(self.analyze_images_button)
        
        # 在功能按钮布局中添加清除记忆按钮
        clear_memory_button = QPushButton("清除AI记忆")
        clear_memory_button.clicked.connect(self.clear_ai_memory)
        buttons_layout.addWidget(clear_memory_button)
        
        left_layout.addLayout(buttons_layout)

        # 添加统计区块
        stats_group = QGroupBox("统计信息")
        stats_layout = QVBoxLayout()
        self.analysis_count_label = QLabel("累计分析次数: 0")
        stats_layout.addWidget(self.analysis_count_label)
        stats_group.setLayout(stats_layout)
        
        # 将统计区块添加到左侧布局中
        left_layout.addWidget(stats_group)

        # 创建一个水局来纳两个日志
        log_layout = QHBoxLayout()

        # 运行日志窗口
        run_log_group = QGroupBox("运行日志")
        run_log_layout = QVBoxLayout()
        self.run_log_text = QTextEdit()
        self.run_log_text.setReadOnly(True)
        self.run_log_text.setContextMenuPolicy(Qt.CustomContextMenu)
        self.run_log_text.customContextMenuRequested.connect(lambda pos: self.show_log_context_menu(pos, self.run_log_text))
        run_log_layout.addWidget(self.run_log_text)
        run_log_group.setLayout(run_log_layout)
        log_layout.addWidget(run_log_group)

        # 错误日志口
        error_log_group = QGroupBox("错误日志")
        error_log_layout = QVBoxLayout()
        self.error_log_text = QTextEdit()
        self.error_log_text.setReadOnly(True)
        self.error_log_text.setContextMenuPolicy(Qt.CustomContextMenu)
        self.error_log_text.customContextMenuRequested.connect(lambda pos: self.show_log_context_menu(pos, self.error_log_text))
        error_log_layout.addWidget(self.error_log_text)
        error_log_group.setLayout(error_log_layout)
        log_layout.addWidget(error_log_group)

        left_layout.addLayout(log_layout)

        # 将左侧布局添加到主布局
        self.layout.addLayout(left_layout, 0, 0, 2, 1)

        # 右侧视显
        self.right_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_widget)
        
        # 视频流标签
        self.stream_label = QLabel()
        self.stream_label.setFixedSize(320, 240)
        self.stream_label.hide()  # 初始时隐藏
        self.right_layout.addWidget(self.stream_label)

        # 图集分析图片显示
        self.image_analysis_label = ClickableLabel()
        self.image_analysis_label.setFixedSize(320, 240)
        self.image_analysis_label.hide()  # 初始时隐藏
        self.image_analysis_label.clicked.connect(self.show_full_screen_image)
        self.right_layout.addWidget(self.image_analysis_label)

        # 分析结果显示
        self.analysis_result_text = QTextEdit()
        self.analysis_result_text.setReadOnly(True)
        self.analysis_result_text.hide()  # 初始时隐藏
        self.right_layout.addWidget(self.analysis_result_text)

        # 添加预览按钮
        self.preview_button = QPushButton("预览详细信息")
        self.preview_button.clicked.connect(self.show_detailed_info)
        self.right_layout.addWidget(self.preview_button)

        self.layout.addWidget(self.right_widget, 0, 1, Qt.AlignRight | Qt.AlignTop)

        # 初始化详细信息窗口
        self.detailed_info_window = None

    def load_existing_streams(self):
        streams = get_all_streams()
        for stream in streams:
            self.stream_manager.add_stream(stream['id'], stream['url'])
        self.log(f"从数据库加载了 {len(streams)} 个现有视频流")
        self.update_streams_table()  # 更新UI中的视频流列表

    def add_stream(self):
        url = self.url_input.text()
        prompt_template = self.prompt_template_combo.currentText()
        if url:
            # 简单的 URL 验证
            if not url.startswith(('rtsp://', 'rtmp://', 'http://', 'https://')):
                self.log("无效的流地址。请使用 rtsp://, rtmp://, http:// 或 https:// 开头的地址。", level=logging.ERROR)
                return
            
            stream_id = add_stream(url)
            if stream_id:
                self.log(f"视频流已添加，ID为: {stream_id}")
                self.stream_manager.add_stream(stream_id, url, prompt_template)
                self.update_streams_table()
                self.url_input.clear()
        else:
            self.log("请输入有效的视频流地址", level=logging.WARNING)

    def update_streams_table(self):
        streams = get_all_streams()
        self.streams_table.setRowCount(len(streams))
        self.streams_table.setColumnCount(5)  # 增加一列用于显示提示词模板
        self.streams_table.setHorizontalHeaderLabels(["ID", "URL", "添加时间", "调优参数", "操作"])
        for row, stream in enumerate(streams):
            self.streams_table.setItem(row, 0, QTableWidgetItem(str(stream['id'])))
            self.streams_table.setItem(row, 1, QTableWidgetItem(stream['url']))
            self.streams_table.setItem(row, 2, QTableWidgetItem(str(stream['added_time'])))
            self.streams_table.setItem(row, 3, QTableWidgetItem(stream.get('prompt_template', 'DEFAULT_PROMPT_TEMPLATE')))
            delete_button = QPushButton("删除")
            delete_button.clicked.connect(lambda _, s_id=stream['id']: self.delete_stream(s_id))
            self.streams_table.setCellWidget(row, 4, delete_button)

    def delete_stream(self, stream_id):
        self.stream_manager.remove_stream(stream_id)
        remove_stream(stream_id)  # 从数据库中删除
        self.update_streams_table()  # 更新UI
        self.log(f"已删除视流 ID: {stream_id}")

    def toggle_stream_processing(self):
        if not self.is_processing:
            self.start_processing()
        else:
            self.stop_processing()

    def start_processing(self):
        try:
            has_streams = bool(self.stream_manager.streams)

            if not has_streams:
                self.log("没有可用视频流。请先添加视频流。")
                return
            
            self.log(f"开始处理 {len(self.stream_manager.streams)} 个视频流")
            for stream_id, stream_info in self.stream_manager.streams.items():
                self.log(f"正在启动流 ID: {stream_id}, URL: {stream_info['url']}")
            
            self.stream_manager.start_all_streams()
            self.start_stream()

            self.start_stop_button.setText("停止处理")
            self.is_processing = True
            self.show_video_labels()
            self.log("视频标签已显示")

            self.start_analysis_thread()
        
        except Exception as e:
            self.log(f"开始处理时发生错误: {str(e)}", level=logging.ERROR)
            import traceback
            self.log(traceback.format_exc(), level=logging.ERROR)
            self.is_processing = False

    def start_analysis_thread(self):
        self.analysis_thread = threading.Thread(target=self.run_analysis, daemon=True)
        self.analysis_thread.start()

    def run_analysis(self):
        while self.is_processing:
            for stream_id in self.stream_manager.streams:
                frame = self.stream_manager.get_latest_frame(stream_id)
                if frame is not None:
                    source_info = f"Stream: {self.stream_manager.streams[stream_id]['url']}"
                    prompt_template = self.stream_manager.streams[stream_id]['prompt_template']
                    self.analyze_frame_thread(frame, source_info, stream_id, prompt_template)
                else:
                    self.log(f"无法获取视频帧 (源: {stream_id})", level=logging.WARNING)
            time.sleep(10)  # 每次分析后等待10秒

    def stop_processing(self):
        try:
            self.log("正在停止处理...")
            self.start_stop_button.setEnabled(False)
            self.stop_thread = StopProcessingThread(self.stream_manager)
            self.stop_thread.finished.connect(self.on_stop_processing_finished)
            self.stop_thread.start()
            self.is_processing = False  # 停止分析线程
        except Exception as e:
            self.log(f"停止处理时发生错误: {str(e)}")
            import traceback
            self.log(traceback.format_exc())

    def on_stop_processing_finished(self):
        try:
            self.log("已停止处理")
            self.start_stop_button.setText("开始处理")
            self.start_stop_button.setEnabled(True)
            self.is_processing = False
            self.stop_stream()
            self.hide_video_labels()  # 隐藏视频标签
        except Exception as e:
            self.log(f"停止处理时发生错误: {str(e)}", level=logging.ERROR)
            import traceback
            self.log(traceback.format_exc(), level=logging.ERROR)

    def log(self, message, level=logging.INFO):
        if "未收到" not in message and "帧已更新" not in message and "Got frame for stream" not in message:
            self.log_signal.emit(message, level)

    def append_run_log(self, message):
        self.run_log_text.append(message)

    def append_error_log(self, message):
        self.error_log_text.append(message)

    def show_settings_dialog(self):
        dialog = SettingsDialog(self)
        if dialog.exec_():
            self.log("设置已更新")
            self.load_settings()  # 加载新的设置
            self.apply_settings()  # 立应用新的设置
        
    def load_settings(self):
        try:
            with open(resource_path('settings.json'), 'r') as f:
                settings = json.load(f)
            
            self.analysis_interval = settings.get('analysis_interval', 3)
            self.theme = settings.get('theme', '跟随系统')
            
            templates = load_prompt_templates()
            self.prompt_template = settings.get('prompt_template', templates.get('DEFAULT_PROMPT_TEMPLATE', ''))
            
            # 加载 AI 模型设置
            self.ai_config = update_ai_config_from_default()
            self.ai_model = self.ai_config['ai_model']
            self.api_key = self.ai_config['api_key']
            self.api_base = self.ai_config['api_base']
            
            # 更新主题
            self.apply_theme(self.theme)
            
            # 更新分析间隔
            self.stream_manager.set_analysis_interval(self.analysis_interval)
            self.log(f"分析间隔设置为 {self.analysis_interval} 秒")
            
            self.log("提示词模板已更新")
            self.log("AI模型设置已更新")
            
        except FileNotFoundError:
            self.log("找到设置文件，使用默认设置")
            templates = load_prompt_templates()
            self.prompt_template = templates.get('DEFAULT_PROMPT_TEMPLATE', '')
        except json.JSONDecodeError:
            self.log("设置文件格式错误，使用默认设置")
        except Exception as e:
            self.log(f"加载设置时发生错误: {str(e)}")

    def apply_settings(self):
        self.log(f"设置已应用。")
        self.stream_manager.set_prompt_template(self.prompt_template)
        self.stream_manager.set_ai_config(self.ai_model, self.api_key, self.api_base)
        self.save_ai_config()
        self.log("提示词模板已更新")
        self.log("AI模型设置已新")

    # 添加新方法来存 AI 配置
    def save_ai_config(self):
        ai_config = {
            "ai_model": self.ai_model,
            "api_key": self.api_key,
            "api_base": self.api_base
        }
        with open(resource_path('ai_config.json'), 'w') as f:
            json.dump(ai_config, f, indent=2)

    def apply_theme(self, theme):
        if theme == '跟随系统':
            QApplication.setStyle(QStyleFactory.create(QApplication.style().objectName()))
            QApplication.setPalette(QApplication.style().standardPalette())
            self.setStyleSheet("")
        elif theme == '深色':
            self.set_dark_theme()
        else:  # 浅色
            self.set_light_theme()
        
        # 所有子窗和的样式
        self.update_styles_recursively(self)
        
        # 果设置对话框是打开的，也更它的样
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, SettingsDialog):
                self.update_styles_recursively(widget)

    def update_styles_recursively(self, widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

        for child in widget.children():
            if isinstance(child, QWidget):
                self.update_styles_recursively(child)

    def show_video_labels(self):
        self.stream_label.show()

    def hide_video_labels(self):
        self.stream_label.hide()

    def show_log_context_menu(self, position, log_widget):
        context_menu = QMenu()
        clear_action = context_menu.addAction("清空日志")
        copy_action = context_menu.addAction("复制")
        select_all_action = context_menu.addAction("选择全部")
        
        action = context_menu.exec_(log_widget.mapToGlobal(position))
        
        if action == clear_action:
            log_widget.clear()
        elif action == copy_action:
            log_widget.copy()
        elif action == select_all_action:
            log_widget.selectAll()

    def update_error_log(self, message):
        self.log(message, level=logging.INFO)  # 将级别改为 INFO

    def show_prompt_settings(self):
        dialog = PromptSettingsDialog(self)
        if dialog.exec_():
            self.log("提示词设置已更新")
            self.load_settings()
            self.apply_settings()
            self.update_prompt_template_combo()  # 更新提示词模板下拉框

    def update_prompt_template_combo(self):
        self.prompt_template_combo.clear()
        templates = load_prompt_templates()
        self.prompt_template_combo.addItems(templates.keys())

    def test_camera(self):
        camera_index, ok = QInputDialog.getInt(self, "选择摄像头", "请输入摄像头索引:", 0, 0, 10)
        if ok:
            self.camera_test_window = CameraTestWindow(camera_index)
            self.camera_test_window.show()

    def create_tray_icon(self):
        # 创建 QIcon 对象，使用您的应用图标
        self.app_icon = QIcon(resource_path("icon.png"))  # 请确保这个路径是正确的

        # 创建系统托盘图标
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.app_icon)
        self.tray_icon.setToolTip("GAI Video")  # 设置托盘图标的工提示

        # 创托盘菜单
        tray_menu = QMenu()

        # 添加菜单项
        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self.show_settings_dialog)
        tray_menu.addAction(settings_action)

        start_action = QAction("开始处理", self)
        start_action.triggered.connect(self.start_processing)
        tray_menu.addAction(start_action)

        stop_action = QAction("停止处理", self)
        stop_action.triggered.connect(self.stop_processing)
        tray_menu.addAction(stop_action)

        about_action = QAction("关于软件", self)
        about_action.triggered.connect(self.show_about_dialog)
        tray_menu.addAction(about_action)

        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        tray_menu.addAction(exit_action)

        # 设置托盘图标的菜单
        self.tray_icon.setContextMenu(tray_menu)

        # 显示托盘图标
        self.tray_icon.show()

        # 连接托盘标的激活信号
        self.tray_icon.activated.connect(self.tray_icon_activated)

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()  # 双击托盘图标时显示主窗口

    def show_about_dialog(self):
        QMessageBox.about(self, "关于 GAI Video", "GAI Video v1.0\n\n© 2023 Your Company Name")

    def start_stream(self):
        if self.stream_thread is None and self.stream_manager.streams:
            stream_id = next(iter(self.stream_manager.streams))
            self.stream_thread = VideoThread(self.stream_manager, stream_id, is_camera=False)
            self.stream_thread.change_pixmap_signal.connect(self.update_stream_image)
            self.stream_thread.error_signal.connect(self.handle_stream_error)
            self.stream_thread.start()
            self.log(f"成功开始视频流 (ID: {stream_id})")
            self.stream_label.show()
            self.log("视频流标签示")
        else:
            self.log("没有可用的频流或视频流已在运行", level=logging.WARNING)

    def update_stream_image(self, image):
        self.stream_label.setPixmap(QPixmap.fromImage(image))

    def handle_stream_error(self, error_message):
        self.log(f"视频流错误: {error_message}", level=logging.ERROR)
        self.stop_stream()
        QMessageBox.warning(self, "视频流错误", error_message)

    def stop_stream(self):
        if self.stream_thread is not None:
            self.stream_thread.stop()
            self.stream_thread = None
            self.stream_label.clear()
            self.stream_label.hide()
            self.log("视频流已停止")

    def toggle_image_analysis(self):
        if not self.is_analyzing_images:
            self.start_image_analysis()
        else:
            self.stop_image_analysis()

    def start_image_analysis(self):
        self.log("开始图集分析...")
        self.is_analyzing_images = True
        self.image_analysis_stop_event.clear()
        self.analyze_images_button.setText("停止图集分析")
        self.image_analysis_label.show()
        self.analysis_result_text.show()
        threading.Thread(target=self.analyze_image_directory, daemon=True).start()

    def stop_image_analysis(self):
        self.log("正在停止图集分析...")
        self.image_analysis_stop_event.set()
        self.is_analyzing_images = False
        self.analyze_images_button.setText("启动图集分析")
        # 移除以下两行，以保持分析结果的显示
        # self.image_analysis_label.hide()
        # self.analysis_result_text.hide()

    def analyze_image_directory(self):
        image_dir = os.path.join(os.getcwd(), 'images')
        if not os.path.exists(image_dir):
            self.log_signal.emit(f"图片目录不存在: {image_dir}", logging.ERROR)
            self.stop_image_analysis()
            return

        image_files = [f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))]
        
        if not image_files:
            self.log_signal.emit("图片目录中没有找到图片文件", logging.WARNING)
            self.stop_image_analysis()
            return

        for image_file in image_files:
            if self.image_analysis_stop_event.is_set():
                self.log_signal.emit("图集分析已停止", logging.INFO)
                break

            image_path = os.path.join(image_dir, image_file)
            self.log_signal.emit(f"正在分析图片: {image_file}", logging.INFO)
            
            # 显示当前分析的图片
            self.update_image_signal.emit(image_path)
            
            try:
                with Image.open(image_path) as img:
                    img = img.convert('RGB')
                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='JPEG')
                    base64_image = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
                
                analysis_result = send_image_to_ai(base64_image, 'SAFETY_ANALYSIS_PROMPT', None, 
                                                   self.ai_model, self.api_key, self.api_base)
                
                if analysis_result:
                    self.log_image_analysis_result(image_file, analysis_result)
                    self.update_analysis_count_signal.emit(self.total_analysis_count + 1)
                    self.update_analysis_result_signal.emit(analysis_result)
                    
                    # 更新详细信息窗口
                    self.update_detailed_info_signal.emit(image_path, analysis_result, "False", "image")
                else:
                    self.log_signal.emit(f"无法获取图片 {image_file} 的分析结果", logging.ERROR)
            
            except Exception as e:
                self.log_signal.emit(f"分析图片 {image_file} 时发生错误: {str(e)}", logging.ERROR)

            # 更新当前分析中的图片和结果
            self.update_detailed_info_signal.emit(image_path, "正在分析...", "True", "image")

            if not self.image_analysis_stop_event.is_set():
                time.sleep(30)  # 将等待时间改为30秒

        if not self.image_analysis_stop_event.is_set():
            self.log_signal.emit("图集分析完成", logging.INFO)
        self.stop_image_analysis()

    def log_image_analysis_result(self, image_file, result):
        log_file = os.path.join(os.getcwd(), 'logs', 'image_analysis.log')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"--- 图片: {image_file} ---\n")
            f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"分析结果: {result}\n\n")
        self.log(f"图片 {image_file} 的分析结果已保存")

    def ensure_image_directory(self):
        image_dir = os.path.join(os.getcwd(), 'images')
        if not os.path.exists(image_dir):
            os.makedirs(image_dir)
            self.log(f"创建图片目录: {image_dir}")

    # 添加更新统计信息的方法
    def update_analysis_count(self):
        self.total_analysis_count += 1
        self.analysis_count_label.setText(f"累计分析次数: {self.total_analysis_count}")

    # 在 analyze_frame 方法中调用更新统计信息的方法
    def analyze_frame(self, stream_id):
        frame = self.stream_manager.get_latest_frame(stream_id)
        if frame is not None:
            source_info = f"Stream: {self.stream_manager.streams[stream_id]['url']}"
            prompt_template = self.stream_manager.streams[stream_id]['prompt_template']
            threading.Thread(target=self.analyze_frame_thread, args=(frame, source_info, stream_id, prompt_template)).start()
        else:
            self.logger.error(f"Failed to get frame for analysis from stream {stream_id}")

    def analyze_frame_thread(self, frame, source_info, stream_id, prompt_template):
        try:
            # 将帧转换为base64编码
            _, buffer = cv2.imencode('.jpg', frame)
            base64_image = base64.b64encode(buffer).decode('utf-8')

            # 发送图像到AI进行分析
            analysis_result = send_image_to_ai(base64_image, prompt_template, None, 
                                               self.ai_model, self.api_key, self.api_base)
            
            if analysis_result:
                # 更新统计信息
                self.update_analysis_count_signal.emit(self.total_analysis_count + 1)
                
                # 显示分析结果
                self.update_analysis_result_signal.emit(analysis_result)
                
                # 记录分析结果
                self.log(f"Analysis result for {source_info}: {analysis_result}")

                # 保存帧为图片文件
                frame_filename = f"frame_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                frame_path = os.path.join(os.getcwd(), 'frames', frame_filename)
                cv2.imwrite(frame_path, frame)

                # 更新详细信息窗口
                self.update_detailed_info_signal.emit(frame_path, analysis_result, "False", "video")
            else:
                self.log(f"无法获取视频帧分析结果 (源: {source_info})", level=logging.ERROR)
        except Exception as e:
            self.log(f"分析视频帧时发生错误 (源: {source_info}): {str(e)}", level=logging.ERROR)

        # 更新当前分析中的图片和结果
        self.update_detailed_info_signal.emit(frame_path, "正在分析...", "True", "video")

    def clear_ai_memory(self):
        try:
            self.ai_interface.clear_history()
            self.log("AI记忆已清除")
            QMessageBox.information(self, "操作成功", "AI记忆已成功清除")
        except Exception as e:
            self.log(f"清除AI记忆时发生错误: {str(e)}", level=logging.ERROR)
            QMessageBox.warning(self, "操作失败", f"除AI记忆失败: {str(e)}")

    def display_analysis_image(self, image_path):
        pixmap = QPixmap(image_path)
        scaled_pixmap = pixmap.scaled(320, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_analysis_label.setPixmap(scaled_pixmap)
        self.image_analysis_label.show()
        # 保存原始图片路径，以便全屏显示时使用
        self.image_analysis_label.original_image_path = image_path

    def display_analysis_result(self, result):
        try:
            result_dict = json.loads(result)
            formatted_result = json.dumps(result_dict, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            formatted_result = result

        current_text = self.analysis_result_text.toPlainText()
        new_text = f"--- 新分析结果 ---\n{formatted_result}\n\n{current_text}"
        self.analysis_result_text.setText(new_text)
        self.analysis_result_text.show()

    def update_analysis_count_slot(self, count):
        self.total_analysis_count = count
        self.analysis_count_label.setText(f"累计分析次数: {self.total_analysis_count}")

    def log_slot(self, message, level):
        logger = logging.getLogger()
        logger.log(level, message)

    def show_full_screen_image(self):
        if self.image_analysis_label.pixmap():
            self.full_screen_viewer = FullScreenImageViewer(self.image_analysis_label.pixmap())
            self.full_screen_viewer.show()

    def show_detailed_info(self):
        if self.detailed_info_window is None:
            self.detailed_info_window = DetailedInfoWindow()
        self.detailed_info_window.show()

    def update_detailed_info(self, image_path, result, is_current, source_type):
        if is_current == "True":
            self.detailed_info_window.set_current_analysis(image_path, result)
        else:
            self.detailed_info_window.add_analyzed_result(image_path, result)

    @pyqtSlot(str, str, str, str)
    def update_detailed_info_slot(self, image_path, result, is_current, analysis_type):
        if self.detailed_info_window:
            if is_current == "True":
                self.detailed_info_window.set_current_analysis(image_path, result)
            else:
                self.detailed_info_window.add_analyzed_result(image_path, result)

class PromptSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("提示词设置")
        self.setGeometry(200, 200, 600, 400)
        
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        # 提示词模板选择
        self.template_combo = QComboBox()
        self.layout.addWidget(QLabel("选择提示模板:"))
        self.layout.addWidget(self.template_combo)
        
        # 提示词模板编辑
        self.prompt_template = QTextEdit()
        self.layout.addWidget(QLabel("编辑提示词模板:"))
        self.layout.addWidget(self.prompt_template)
        
        # 添加新模板按钮
        add_button = QPushButton("添加新模板")
        add_button.clicked.connect(self.add_new_template)
        self.layout.addWidget(add_button)
        
        # 删除当前模板按钮
        delete_button = QPushButton("删除前模板")
        delete_button.clicked.connect(self.delete_current_template)
        self.layout.addWidget(delete_button)
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.layout.addWidget(button_box)
        
        self.load_templates()
        self.template_combo.currentTextChanged.connect(self.on_template_changed)
    
    def load_templates(self):
        self.templates = load_prompt_templates()
        self.template_combo.clear()
        self.template_combo.addItems(self.templates.keys())
        if self.template_combo.count() > 0:
            self.template_combo.setCurrentIndex(0)
            self.on_template_changed(self.template_combo.currentText())
    
    def on_template_changed(self, template_name):
        self.prompt_template.setPlainText(self.templates.get(template_name, ""))
    
    def add_new_template(self):
        name, ok = QInputDialog.getText(self, "新模板", "输入新模板名称:")
        if ok and name:
            if name not in self.templates:
                self.templates[name] = ""
                self.template_combo.addItem(name)
                self.template_combo.setCurrentText(name)
            else:
                QMessageBox.warning(self, "错误", "模板名称已存在")
    
    def delete_current_template(self):
        current = self.template_combo.currentText()
        if current != "DEFAULT_PROMPT_TEMPLATE":
            del self.templates[current]
            self.template_combo.removeItem(self.template_combo.currentIndex())
        else:
            QMessageBox.warning(self, "错误", "不能删除默认模板")
    
    def accept(self):
        # 保存当前编辑的模板
        current = self.template_combo.currentText()
        self.templates[current] = self.prompt_template.toPlainText()
        
        # 保存所有模板到文件
        with open(resource_path('prompt_templates.json'), 'w', encoding='utf-8') as f:
            json.dump(self.templates, f, ensure_ascii=False, indent=2)
        
        super().accept()

class ClickableLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

class DetailedInfoWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("详细信息")
        self.setGeometry(100, 100, 1000, 600)

        layout = QHBoxLayout()
        self.setLayout(layout)

        # 左侧：正在分析
        left_group = QGroupBox("正在分析")
        left_layout = QVBoxLayout()
        self.current_image_label = QLabel()
        self.current_image_label.setFixedSize(400, 300)
        self.current_result_text = QTextEdit()
        self.current_result_text.setReadOnly(True)
        left_layout.addWidget(self.current_image_label)
        left_layout.addWidget(self.current_result_text)
        left_group.setLayout(left_layout)

        # 右侧：已分析结果
        right_group = QGroupBox("已分析结果")
        right_layout = QVBoxLayout()
        self.analyzed_image_label = QLabel()
        self.analyzed_image_label.setFixedSize(400, 300)
        self.analyzed_result_text = QTextEdit()
        self.analyzed_result_text.setReadOnly(True)
        right_layout.addWidget(self.analyzed_image_label)
        right_layout.addWidget(self.analyzed_result_text)
        
        # 添加切换按钮
        button_layout = QHBoxLayout()
        self.prev_button = QPushButton("上一张")
        self.next_button = QPushButton("下一张")
        button_layout.addWidget(self.prev_button)
        button_layout.addWidget(self.next_button)
        right_layout.addLayout(button_layout)
        
        right_group.setLayout(right_layout)

        layout.addWidget(left_group)
        layout.addWidget(right_group)

        self.analyzed_results = []
        self.current_index = 0

        self.prev_button.clicked.connect(self.show_previous)
        self.next_button.clicked.connect(self.show_next)

    def set_current_analysis(self, image_path, result):
        pixmap = QPixmap(image_path)
        self.current_image_label.setPixmap(pixmap.scaled(400, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.current_result_text.setText(result)

    def add_analyzed_result(self, image_path, result):
        self.analyzed_results.append((image_path, result))
        if len(self.analyzed_results) == 1:
            self.show_analyzed_result(0)
        else:
            self.show_analyzed_result(len(self.analyzed_results) - 1)  # 显示最新的结果

    def show_analyzed_result(self, index):
        if 0 <= index < len(self.analyzed_results):
            image_path, result = self.analyzed_results[index]
            pixmap = QPixmap(image_path)
            self.analyzed_image_label.setPixmap(pixmap.scaled(400, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.analyzed_result_text.setText(result)
            self.current_index = index

    def show_previous(self):
        if self.current_index > 0:
            self.show_analyzed_result(self.current_index - 1)

    def show_next(self):
        if self.current_index < len(self.analyzed_results) - 1:
            self.show_analyzed_result(self.current_index + 1)

if __name__ == "__main__":
    init_db()
    update_db_structure()
    app = QApplication(sys.argv)
    app.setApplicationName("GAI Video")
    
    # 添加 AppDelegate
    delegate = AppDelegate()
    app.setProperty("NSApplicationDelegate", delegate)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
