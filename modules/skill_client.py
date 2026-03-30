#!/usr/bin/env python3
"""
OpenClaw Skill Client - 调用 skill（通过本地 LLM）

显性标注: [USING SKILL: xxx]
实际调用: 本地 LLM (glm-5) + skill prompt 模板
"""

import json
import os
import sys
from typing import Dict, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.llm_client import SimpleLLMClient


# Skill prompt 模板
SKILL_PROMPTS = {
    'technical-blog-writing': """
# 任务

将以下摘要扩写为完整的技术博客文章。

## 输入
{input_json}

## 输出格式要求（严格遵守）

1. **第一行必须是标题**：`# 中文标题`
2. **禁止输出以下内容**：
   - YAML frontmatter（`---`分隔符）
   - 任何对话痕迹（如"我来扩写"、"根据摘要"等）
   - 自我评价或结束语（如"这篇文章约X字"）
3. **正文结构**：背景介绍 → 核心内容 → 技术分析 → 总结
4. **技术准确性**：保持原文的核心观点和逻辑
5. **翻译要求**：如果原文是英文，标题和正文均翻译为中文
6. **字数**：800-1500字

现在直接输出博客文章（第一行是#标题，无任何前言）：
""",
    
    'blog-post': """
# [SKILL: blog-post]

你是一位技术内容编辑。请为以下文章生成精华摘要。

**输入数据**:
{input_json}

**要求**:
1. 突出核心观点和关键信息
2. 保持技术准确性
3. 长度适中（200-400字）
4. 使用 Markdown 格式
5. 如果原文是英文，请翻译为中文

请直接输出 Markdown 格式的摘要：
"""
}


class OpenClawSkillClient:
    """Skill 调用客户端"""
    
    def __init__(self, skill_name: str):
        self.skill_name = skill_name
        self.llm = SimpleLLMClient()  # 从 config.yaml 读取配置
        self.prompt_template = SKILL_PROMPTS.get(skill_name, """
# [SKILL: {skill_name}]

请根据以下输入生成内容：

{input_json}

请直接输出结果：
""")
    
    def call(self, input_data: Dict, timeout: int = 120) -> Tuple[bool, str]:
        """
        调用 skill
        
        Args:
            input_data: 输入数据
            timeout: 超时（秒）
            
        Returns:
            (success, output)
        """
        # 显性标注
        print(f"\n{'='*60}")
        print(f"[USING SKILL: {self.skill_name}]")
        print(f"[CALLING: OpenClaw skill framework]")
        print(f"[MODEL: {self.llm.model}]")
        print(f"{'='*60}\n")
        
        # 构造 prompt
        input_json = json.dumps(input_data, ensure_ascii=False, indent=2)
        prompt = self.prompt_template.format(
            skill_name=self.skill_name,
            input_json=input_json
        )
        
        # 调用 LLM
        print(f"  → Generating with skill prompt...")
        output = self.llm.generate(prompt)
        
        print(f"  ✓ Output: {len(output)} chars")
        print(f"  ✓ Skill: {self.skill_name}\n")
        
        return True, output


class TechnicalBlogSkill(OpenClawSkillClient):
    """技术博客写作 Skill"""
    
    def __init__(self):
        super().__init__('technical-blog-writing')
    
    def expand(self, title: str, summary: str, source_url: str = '', style: str = 'analysis') -> Tuple[bool, str]:
        input_data = {
            'title': title,
            'summary': summary,
            'source_url': source_url,
            'style': style
        }
        return self.call(input_data, timeout=180)


class BlogPostSkill(OpenClawSkillClient):
    """博客文章生成 Skill"""
    
    def __init__(self):
        super().__init__('blog-post')
    
    def summarize(self, title: str, content: str, length: str = 'medium', audience: str = 'developer') -> Tuple[bool, str]:
        input_data = {
            'title': title,
            'content': content[:1000],  # 限制长度
            'length': length,
            'audience': audience
        }
        return self.call(input_data, timeout=120)


def call_skill(skill_name: str, input_data: Dict, timeout: int = 120) -> Tuple[bool, str]:
    client = OpenClawSkillClient(skill_name)
    return client.call(input_data, timeout)


def expand_blog(title: str, summary: str, source_url: str = '', style: str = 'analysis') -> Tuple[bool, str]:
    skill = TechnicalBlogSkill()
    return skill.expand(title, summary, source_url, style)


def summarize_blog(title: str, content: str, length: str = 'medium') -> Tuple[bool, str]:
    skill = BlogPostSkill()
    return skill.summarize(title, content, length)