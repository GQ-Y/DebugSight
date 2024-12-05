import sqlite3
import os
from datetime import datetime
import json
import time

DB_PATH = 'video_streams.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS streams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            added_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analysis_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stream_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            result JSON,
            FOREIGN KEY (stream_id) REFERENCES streams(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS person_features (
            id TEXT PRIMARY KEY,
            features TEXT,
            position TEXT,
            action TEXT,
            last_seen TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def update_db_structure():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 检查 added_time 列是否存在
    cursor.execute("PRAGMA table_info(streams)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'added_time' not in columns:
        print("正在更新数据库结构...")
        cursor.execute("ALTER TABLE streams ADD COLUMN added_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        # 为现有记录设置 added_time
        cursor.execute("UPDATE streams SET added_time = CURRENT_TIMESTAMP WHERE added_time IS NULL")
        print("streams 表结构更新完成")
    
    # 检查 prompt_template 列是否存在
    if 'prompt_template' not in columns:
        print("正在添加 prompt_template 列...")
        cursor.execute("ALTER TABLE streams ADD COLUMN prompt_template TEXT DEFAULT 'DEFAULT_PROMPT_TEMPLATE'")
        print("prompt_template 列添加完成")
    
    # 确保 person_features 表存在并有正确的结构
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS person_features (
            id TEXT PRIMARY KEY,
            features TEXT,
            position TEXT,
            action TEXT,
            last_seen TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    
    print("数据库结构更新完成")

def update_person_features_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 检查 position, action 和 created_at 列是否存在
    cursor.execute("PRAGMA table_info(person_features)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'position' not in columns:
        cursor.execute("ALTER TABLE person_features ADD COLUMN position TEXT")
    
    if 'action' not in columns:
        cursor.execute("ALTER TABLE person_features ADD COLUMN action TEXT")
    
    if 'created_at' not in columns:
        cursor.execute("ALTER TABLE person_features ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    
    conn.commit()
    conn.close()
    print("person_features 表结构已更新")

def add_stream(url, prompt_template='DEFAULT_PROMPT_TEMPLATE'):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO streams (url, added_time, prompt_template) VALUES (?, ?, ?)", 
                   (url, datetime.now(), prompt_template))
    conn.commit()
    stream_id = cursor.lastrowid
    conn.close()
    return stream_id

def remove_stream(id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM streams WHERE id = ?", (id,))
    if cursor.rowcount > 0:
        print(f"成功删除视频流 ID: {id}")
    else:
        print(f"未找到视频流 ID: {id}")
    conn.commit()
    conn.close()

def get_all_streams():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, url, added_time, prompt_template FROM streams")
    except sqlite3.OperationalError:
        # 如果 prompt_template 列不存在，就不包含它
        cursor.execute("SELECT id, url, added_time FROM streams")
    
    streams = []
    for row in cursor.fetchall():
        stream = {'id': row[0], 'url': row[1], 'added_time': row[2]}
        if len(row) > 3:
            stream['prompt_template'] = row[3]
        else:
            stream['prompt_template'] = 'DEFAULT_PROMPT_TEMPLATE'
        streams.append(stream)
    
    conn.close()
    return streams

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def save_analysis_result(stream_id, analysis_result):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO analysis_results (stream_id, result, timestamp)
        VALUES (?, ?, datetime('now'))
    """, (stream_id, json.dumps(analysis_result)))
    conn.commit()
    conn.close()

def save_person_features(person_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    current_time = time.time()
    cursor.execute("""
        INSERT OR REPLACE INTO person_features (id, features, position, action, last_seen, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (person_data['id'], json.dumps(person_data['features']), 
          person_data['position'], person_data['action'], person_data['last_seen'],
          current_time))
    conn.commit()
    conn.close()

def get_person_features():
    conn = get_db_connection()
    cursor = conn.cursor()
    current_time = time.time()
    two_hours_ago = current_time - (2 * 60 * 60)  # 2小时前的时间戳
    
    # 删除超过2小时的Reid数据
    cursor.execute("DELETE FROM person_features WHERE created_at < ?", (two_hours_ago,))
    
    cursor.execute("SELECT id, features, position, action, last_seen, created_at FROM person_features")
    features = [{
        "id": row['id'],
        "features": json.loads(row['features']),
        "position": row['position'],
        "action": row['action'],
        "last_seen": row['last_seen'],
        "created_at": row['created_at']
    } for row in cursor.fetchall()]
    conn.commit()
    conn.close()
    return features