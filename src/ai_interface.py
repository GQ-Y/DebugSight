import requests
import json
import base64
import logging
import time
import uuid
from ratelimit import limits, sleep_and_retry

class AIInterface:
    def __init__(self, api_key, api_base, model):
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.logger = logging.getLogger(__name__)
        self.conversation_history = []
        self.user_id = str(uuid.uuid4())  # 生成唯一的用户ID

    @sleep_and_retry
    @limits(calls=1, period=10)  # 限制为每10秒1次调用
    def send_request(self, prompt, image_base64=None):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 添加系统角色消息
        system_message = {
            "role": "system",
            "content": "你是一个专业的工地安全分析AI助手，能够分析图片并提供安全建议。"
        }
        
        # 创建用户消息
        user_message = {
            "role": "user",
            "content": [{"type": "text", "text": prompt}]
        }
        if image_base64:
            user_message["content"].append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
            })
        
        # 更新对话历史
        self.conversation_history.append(system_message)
        self.conversation_history.append(user_message)
        
        payload = {
            "model": self.model,
            "messages": self.conversation_history,
            "request_id": str(uuid.uuid4()),  # 生成唯一的请求ID
            "user_id": self.user_id
        }
        
        try:
            response = requests.post(f"{self.api_base}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            ai_response = response.json()['choices'][0]['message']['content']
            
            # 将AI的回复添加到对话历史
            self.conversation_history.append({
                "role": "assistant",
                "content": ai_response
            })
            
            # 保持对话历史在合理的长度内
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]
            
            return ai_response
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Error sending request to AI service: {str(e)}")
            self.logger.error(f"Response content: {response.text}")
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                self.logger.info(f"Rate limit exceeded. Retrying after {retry_after} seconds.")
                time.sleep(retry_after)
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error in send_request: {str(e)}")
            return None

    def analyze_frame(self, frame_description, prompt_template, image_base64=None):
        prompt = prompt_template.format(frame_description=frame_description)
        return self.send_request(prompt, image_base64)

    def clear_history(self):
        self.conversation_history = []
        self.logger.info("Conversation history cleared.")

def load_ai_config():
    try:
        with open('ai_config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError("ai_config.json file not found. Please ensure it exists in the root directory.")

def send_image_to_ai(base64_image, prompt_type, reid_data, ai_model=None, api_key=None, api_base=None):
    config = load_ai_config()
    ai_model = ai_model or config['ai_model']
    api_key = api_key or config['api_key']
    api_base = api_base or config['api_base']

    ai_interface = AIInterface(api_key, api_base, ai_model)

    # 加载提示词模板
    templates = load_prompt_templates()
    prompt = templates.get(prompt_type, templates.get('GENERAL_ANALYSIS_PROMPT'))

    if reid_data:
        prompt += f"\n\n以下是之前识别到的人员特征数据，请在分析时考虑这些信息：\n{json.dumps(reid_data, ensure_ascii=False)}"

    max_retries = 3
    for attempt in range(max_retries):
        result = ai_interface.analyze_frame(prompt, "{frame_description}", base64_image)
        if result is not None:
            return result
        if attempt < max_retries - 1:
            logging.warning(f"重试分析 (尝试 {attempt + 2}/{max_retries})")
            time.sleep(5)  # 等待5秒后重试

    logging.error(f"在 {max_retries} 次尝试后未能获取分析结果")
    return None

# 添加这个函数来加载提示词模板
def load_prompt_templates():
    try:
        with open('prompt_templates.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error("prompt_templates.json 文件未找到。请确保它存在于根目录中。")
        return {"GENERAL_ANALYSIS_PROMPT": "请分析这张图片的内容，描述你看到的主要物体、场景和活动。"}

# 如果需要，你可以在这里添加其他函数
