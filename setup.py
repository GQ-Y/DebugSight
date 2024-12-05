import sys
import os
from setuptools import setup

# 获取当前 Python 解释器的路径
python_path = sys.executable

# 确定架构
if sys.platform == 'darwin':
    from sysconfig import get_config_var
    arch = get_config_var('MACOSX_DEPLOYMENT_TARGET')
else:
    arch = 'x86_64' if sys.maxsize > 2**32 else 'i386'

APP = ['main.py']
DATA_FILES = [
    'icon.png',
    'ai_config.json',
    'prompt_templates.json',
    'settings.json',
    ('', ['src/db_handler.py', 'src/stream_manager.py'])
]
OPTIONS = {
    'argv_emulation': False,
    'packages': ['PyQt5', 'cv2', 'numpy', 'logging', 'json', 'time', 'threading', 'subprocess', 'psutil', 'os'],
    'includes': ['src.db_handler', 'src.stream_manager'],
    'excludes': ['tkinter'],
    'plist': {
        'CFBundleName': 'GAI Video',
        'CFBundleDisplayName': 'GAI Video',
        'CFBundleGetInfoString': "GAI Video Application",
        'CFBundleIdentifier': "com.yourcompany.gaivideo",
        'CFBundleVersion': "1.0.0",
        'CFBundleShortVersionString': "1.0.0",
        'NSHumanReadableCopyright': u"Copyright © 2023, Your Company, All Rights Reserved"
    },
    'frameworks': [python_path],
    'arch': arch,
    'site_packages': True,
    'resources': ['icon.png', 'ai_config.json', 'prompt_templates.json', 'settings.json'],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)