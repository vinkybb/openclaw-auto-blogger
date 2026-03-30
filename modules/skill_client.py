#!/usr/bin/env python3
"""
OpenClaw Skill Client - 通过 OpenClaw sessions_spawn API 调用 skill
"""

import requests
import json
import os
import time
from typing import Dict, Optional, Tuple

# OpenClaw Gateway URL
OPENCLAW_GATEWAY_URL = os.getenv('OPENCLAW_GATEWAY_URL', 'http://localhost:8080')


class OpenClawSkillClient:
    """OpenClaw Skill 调用客户端 - 通过 sessions_spawn API"""
    
    def __init__(self, skill_name: str):
        """
        初始化 Skill 客户端
        
        Args:
            skill_name: skill 名称（如 technical-blog-writing, blog-post）
        """
        self.skill_name = skill_name
        
    def call(self, input_data: Dict, timeout: int = 120) -> Tuple[bool, str]:
        """
        调用 Skill - 通过 OpenClaw sessions_spawn API
        
        Args:
            input_data: 输入数据
            timeout: 超时时间（秒）
            
        Returns:
            (success, output): 成功与否，输出内容
        """
        # 显性标注正在调用 OpenClaw
        print(f"[CALLING OPENCLAW: sessions_spawn with skill={self.skill_name}]")
        
        # 构造 skill 调用 prompt
        skill_prompt = f"""
# [SKILL: {self.skill_name}]

请根据以下输入生成内容：

**Input**:
```json
{json.dumps(input_data, ensure_ascii=False, indent=2)}
```

**要求**:
1. 生成高质量的 Markdown 格式内容
2. 内容结构清晰
3. 保持技术准确性
4. 如果原文是英文，请翻译为中文

请直接输出 Markdown 内容。
"""
        
        # 调用 OpenClaw sessions_spawn API
        api_url = f"{OPENCLAW_GATEWAY_URL}/api/sessions/spawn"
        
        payload = {
            "task": skill_prompt,
            "mode": "run",  # one-shot 执行
            "runtime": "subagent",
            "timeoutSeconds": timeout,
            "model": "custom-coding-dashscope-aliyuncs-com/glm-5"
        }
        
        try:
            print(f"  → POST {api_url}")
            resp = requests.post(api_url, json=payload, timeout=timeout + 30)
            
            if resp.status_code == 200:
                result = resp.json()
                output = result.get('output', result.get('result', ''))
                session_id = result.get('sessionId', result.get('session_id', ''))
                
                print(f"  ✓ sessionId: {session_id}")
                print(f"  ✓ Output length: {len(output)} chars")
                
                return True, output
            else:
                error_msg = f"API error: {resp.status_code} - {resp.text[:100]}"
                print(f"  ✗ {error_msg}")
                return False, error_msg
                
        except requests.exceptions.Timeout:
            print(f"  ✗ Timeout after {timeout}s")
            return False, f"Timeout after {timeout}s"
        except Exception as e:
            print(f"  ✗ Exception: {str(e)[:100]}")
            return False, str(e)


class TechnicalBlogSkill(OpenClawSkillClient):
    """技术博客写作 Skill"""
    
    def __init__(self):
        super().__init__('technical-blog-writing')
    
    def expand(self, title: str, summary: str, source_url: str = '', style: str = 'analysis') -> Tuple[bool, str]:
        """
        扩写技术博客
        
        Args:
            title: 文章标题
            summary: 文章摘要/要点
            source_url: 原文链接
            style: 写作风格
            
        Returns:
            (success, markdown): 成功与否，生成的 Markdown
        """
        input_data = {
            'title': title,
            'summary': summary,
            'source_url': source_url,
            'style': style
        }
        
        # 显性标注 [USING SKILL]
        print(f"[USING SKILL: technical-blog-writing]")
        
        return self.call(input_data, timeout=180)


class BlogPostSkill(OpenClawSkillClient):
    """博客文章生成 Skill"""
    
    def __init__(self):
        super().__init__('blog-post')
    
    def summarize(self, title: str, content: str, length: str = 'medium', audience: str = 'developer') -> Tuple[bool, str]:
        """
        生成文章摘要
        
        Args:
            title: 文章标题
            content: 原文内容
            length: 目标长度
            audience: 目标读者
            
        Returns:
            (success, markdown): 成功与否，生成的 Markdown
        """
        input_data = {
            'title': title,
            'content': content,
            'length': length,
            'audience': audience
        }
        
        # 显性标注 [USING SKILL]
        print(f"[USING SKILL: blog-post]")
        
        return self.call(input_data, timeout=120)


# 便捷函数
def call_skill(skill_name: str, input_data: Dict, timeout: int = 120) -> Tuple[bool, str]:
    """
    调用指定 skill
    
    Args:
        skill_name: skill 名称
        input_data: 输入数据
        timeout: 超时时间
        
    Returns:
        (success, output): 成功与否，输出内容
    """
    client = OpenClawSkillClient(skill_name)
    return client.call(input_data, timeout)


def expand_blog(title: str, summary: str, source_url: str = '', style: str = 'analysis') -> Tuple[bool, str]:
    """使用 technical-blog-writing skill 扩写博客"""
    skill = TechnicalBlogSkill()
    return skill.expand(title, summary, source_url, style)


def summarize_blog(title: str, content: str, length: str = 'medium') -> Tuple[bool, str]:
    """使用 blog-post skill 生成摘要"""
    skill = BlogPostSkill()
    return skill.summarize(title, content, length)