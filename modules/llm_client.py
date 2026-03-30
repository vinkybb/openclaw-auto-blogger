#!/usr/bin/env python3
"""
Simple LLM Client - 直接调用 API，不依赖 Gateway
"""

import os
import json
import requests
from typing import Dict, Optional, List


class SimpleLLMClient:
    """简单的 LLM API 客户端"""
    
    def __init__(self, model: str = 'openclaw', api_key: Optional[str] = None, base_url: Optional[str] = None):
        # 从 config.yaml 读取默认配置
        import yaml
        config_file = os.path.expanduser('/root/home/blog-pipeline/config.yaml')
        if os.path.exists(config_file) and not api_key:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            ai_config = config.get('ai', {})
            self.model = ai_config.get('model', model)
            self.api_key = ai_config.get('api_key', '')
            self.base_url = ai_config.get('base_url', '')
        else:
            self.model = model
            if not api_key:
                api_key, base_url = self._get_credentials()
            self.api_key = api_key
            self.base_url = base_url or 'https://dashscope.aliyuncs.com/compatible-mode/v1'
    
    def _get_credentials(self) -> tuple:
        """从 config.yaml / providers.json / 环境变量获取 API credentials"""
        import yaml
        
        # 优先读取 blog-pipeline config.yaml
        config_file = os.path.expanduser('/root/home/blog-pipeline/config.yaml')
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            ai_config = config.get('ai', {})
            if ai_config.get('api_key') and ai_config.get('base_url'):
                return (ai_config['api_key'], ai_config['base_url'])
        
        # providers.json 备选
        providers_file = os.path.expanduser('~/.openclaw/providers.json')
        if os.path.exists(providers_file):
            with open(providers_file, 'r') as f:
                providers = json.load(f)
            
            for name, provider in providers.items():
                if 'dashscope' in name.lower():
                    return (
                        provider.get('apiKey', ''),
                        provider.get('baseUrl', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
                    )
                if 'openai' in name.lower():
                    return (
                        provider.get('apiKey', ''),
                        provider.get('baseUrl', 'https://api.openai.com/v1')
                    )
        
        # 环境变量备选
        if os.environ.get('DASHSCOPE_API_KEY'):
            return (
                os.environ['DASHSCOPE_API_KEY'],
                'https://dashscope.aliyuncs.com/compatible-mode/v1'
            )
        if os.environ.get('OPENAI_API_KEY'):
            return (
                os.environ['OPENAI_API_KEY'],
                'https://api.openai.com/v1'
            )
        
        return ('', '')
    
    def chat(self, messages: List[Dict], model: Optional[str] = None) -> str:
        """调用 Chat API"""
        if not self.api_key:
            raise Exception('No API key available. Please configure ~/.openclaw/providers.json or set DASHSCOPE_API_KEY/OPENAI_API_KEY')
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        actual_model = model or self.model
        # 处理模型名称（去掉 provider 前缀）
        if '/' in actual_model:
            actual_model = actual_model.split('/')[-1]
        
        payload = {
            'model': actual_model,
            'messages': messages,
            'temperature': 0.7,
            'max_tokens': 1024
        }
        
        try:
            response = requests.post(
                f'{self.base_url}/chat/completions',
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
            else:
                raise Exception(f'API error: {response.status_code} - {response.text}')
        except requests.Timeout:
            raise Exception('API timeout (60s)')
        except Exception as e:
            raise Exception(f'API call failed: {str(e)}')
    
    def summarize(self, title: str, content: str) -> str:
        """生成文章摘要"""
        messages = [
            {'role': 'system', 'content': '你是一个专业的文章摘要助手，擅长生成简洁、准确、有价值的摘要。'},
            {'role': 'user', 'content': f"""请为以下文章生成一个简洁的摘要（150-200字）：

标题：{title}

内容：
{content[:2000]}

摘要应包含：
1. 文章的核心观点
2. 重要结论或发现
3. 对读者的价值

请直接输出摘要内容，不需要其他格式。"""}
        ]
        return self.chat(messages)
    
    def rewrite(self, title: str, content: str, style: str = 'tech_blog') -> str:
        """改写文章"""
        style_descs = {
            'tech_blog': '技术博客风格：简洁、专业、有深度，适合开发者阅读',
            'news': '新闻风格：客观、简洁、突出事实',
            'social': '社交媒体风格：轻松、有趣、易于分享'
        }
        
        messages = [
            {'role': 'system', 'content': f'你是一个专业的文章改写助手，擅长将文章改写为{style_descs.get(style, style_descs["tech_blog"])}。'},
            {'role': 'user', 'content': f"""请将以下文章改写为指定风格：

标题：{title}

原文内容：
{content[:3000]}

改写要求：
1. 保持原文的核心信息和观点
2. 调整语言风格以匹配目标受众
3. 添加适当的过渡和结构
4. 保持文章的可读性和流畅性

请直接输出改写后的文章内容。"""}
        ]
        return self.chat(messages)


# 便捷函数
def summarize_article(title: str, content: str, model: str = 'glm-5') -> str:
    """生成文章摘要"""
    client = SimpleLLMClient(model)
    return client.summarize(title, content)


def rewrite_article(title: str, content: str, style: str = 'tech_blog', model: str = 'glm-5') -> str:
    """改写文章"""
    client = SimpleLLMClient(model)
    return client.rewrite(title, content, style)