import PyInstaller.__main__
import sys
import os

# 获取当前脚本的目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 定义额外的数据文件
extra_datas = [
    ('icon.png', '.'),
    ('ai_config.json', '.'),
    ('prompt_templates.json', '.'),
    ('settings.json', '.'),
    ('src', 'src'),
    ('utils.py', '.'),
]

# 确保所有数据文件都存在
for src, _ in extra_datas:
    if not os.path.exists(os.path.join(current_dir, src)):
        print(f"警告: 文件 {src} 不存在")

# 为 macOS 准备 --add-data 参数
add_data_args = []
for src, dest in extra_datas:
    add_data_args.append(f'--add-data={os.path.join(current_dir, src)}:{dest}')

PyInstaller.__main__.run([
    'main.py',
    '--name=GAI Video',
    '--windowed',
    '--onedir',
    *add_data_args,  # 使用解包操作符来添加所有 --add-data 参数
    '--hidden-import=src.db_handler',
    '--hidden-import=src.stream_manager',
    '--hidden-import=PyQt5.QtCore',
    '--hidden-import=PyQt5.QtGui',
    '--hidden-import=PyQt5.QtWidgets',
    '--hidden-import=cv2',
    '--hidden-import=numpy',
    '--hidden-import=utils',  # 添加这一行
    '--add-data=utils.py:.',  # 确保 utils.py 被包含
    f'--icon={os.path.join(current_dir, "icon.png")}',
    '--clean',
    '--log-level=DEBUG',
])