import logging
import os
import sys
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QObject, Qt, QTimer
from PyQt5.QtGui import QIcon
from src.db_handler import init_db, update_db_structure
import multiprocessing
import signal
import traceback
from utils import resource_path

# 创建logs目录（如果不存在）
os.makedirs('logs', exist_ok=True)

# 设置日志
logging.basicConfig(filename='logs/gai_video.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

class AppDelegate(QObject):
    def __init__(self):
        super().__init__()
    def applicationSupportsSecureRestorableState_(self, app):
        return True

def signal_handler(signum, frame):
    QApplication.quit()
    

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def exception_hook(exctype, value, tb):
    logging.error("Uncaught exception", exc_info=(exctype, value, tb))
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = exception_hook

logging.basicConfig(filename='error.log', level=logging.ERROR,
                    format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    try:
        print("GAI Video 启动")
        logging.info("GAI Video 启动")
        init_db()
        update_db_structure()  # 确保这行在这里
        
        # 在创建 QApplication 之前设置高DPI缩放属性
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
        
        app = QApplication(sys.argv)
        app.setApplicationName("GAI Video")
        app.setApplicationDisplayName("GAI Video")
        app.setOrganizationName("Your Company Name")
        app.setOrganizationDomain("yourcompany.com")
        
        # 设置应用程序图标
        app_icon = QIcon(resource_path("icon.png"))
        app.setWindowIcon(app_icon)
        
        delegate = AppDelegate()
        app.setProperty("NSApplicationDelegate", delegate)
        
        # 在这里导入 MainWindow
        from gui import MainWindow
        window = MainWindow()
        window.show()
        
        # 设置一个定时器来处理 Python 信号
        timer = QTimer()
        timer.start(500)
        timer.timeout.connect(lambda: None)  # 让 Python 有机会处理信号
        
        sys.exit(app.exec_())
    except Exception as e:
        error_msg = f"发生未处理的异常: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        logging.error(error_msg)
        with open(resource_path('error.log'), 'w') as f:
            f.write(error_msg)
        
        # 显示错误消息框
        error_box = QMessageBox()
        error_box.setIcon(QMessageBox.Critical)
        error_box.setText("应用程序遇到了一个错误")
        error_box.setInformativeText(str(e))
        error_box.setDetailedText(error_msg)
        error_box.setStandardButtons(QMessageBox.Ok)
        error_box.exec_()
        
        sys.exit(1)

if __name__ == "__main__":
    multiprocessing.freeze_support()  # 为了支持冻结的可执行文件
    main()

if getattr(sys, 'frozen', False):
    # 如果应用程序被冻结（例如，使用 py2app）
    bundle_dir = sys._MEIPASS
else:
    # 如果应用程序正常运行
    bundle_dir = os.path.dirname(os.path.abspath(__file__))

# 将 bundle_dir 添加到 Python 路径
sys.path.append(bundle_dir)