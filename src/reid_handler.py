import time

# 定义一个全局变量来存储ReID数据
reid_data = []

def get_reid_data(frame=None):
    global reid_data
    # 移除超过 5 分钟未更新的数据
    current_time = time.time()
    reid_data = [data for data in reid_data if current_time - data['last_seen'] < 300]
    return reid_data

def update_reid_data(new_data):
    global reid_data
    for new_person in new_data:
        existing_person = next((p for p in reid_data if p['id'] == new_person['id']), None)
        if existing_person:
            existing_person.update(new_person)
        else:
            reid_data.append(new_person)

# 确保在启动视频流处理之前调用update_reid_data至少一次，即使是用空数据初始化
update_reid_data([])