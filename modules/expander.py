#!/usr/bin/env python3
"""
文章扩写模块 - 使用 OpenClaw skill: technical-blog-writing

显性标注: [USING SKILL: technical-blog-writing]
调用方式: OpenClaw sessions_spawn API
"""

import os
import sys
from typing import Dict, Optional

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.skill_client import TechnicalBlogSkill
from modules.llm_client import SimpleLLMClient


class ArticleExpander:
    """
    文章扩写器
    
    调用 OpenClaw sessions_spawn API 使用 [SKILL: technical-blog-writing]
    将文章摘要扩写为完整的技术博客文章。
    """
    
    def __init__(self, config: Dict = None, use_skill: bool = True):
        """
        初始化扩写器
        
        Args:
            config: 配置字典（可选）
            use_skill: 是否使用 OpenClaw skill（默认 True）
        """
        self.config = config or {}
        self.use_skill = use_skill
        self.skill = TechnicalBlogSkill() if use_skill else None
        self.llm_client = SimpleLLMClient('glm-5')  # 回退用
        
    def expand(self, article: Dict, style: str = 'analysis') -> Dict:
        """
        扩写文章 - 显性标注使用 OpenClaw skill
        
        Args:
            article: 文章数据（包含 title, summary, link 等）
            style: 写作风格
            
        Returns:
            扩写后的文章数据（包含 skill_used 字段）
        """
        title = article.get('title', '')
        summary = article.get('summary', article.get('description', ''))
        source_url = article.get('link', '')
        
        # ========== 显性标注：使用 OpenClaw skill ==========
        print(f"\n{'='*60}")
        print(f"[USING SKILL: technical-blog-writing]")
        print(f"[CALLING: OpenClaw sessions_spawn API]")
        print(f"[INPUT: title='{title[:50]}...']")
        print(f"{'='*60}\n")
        
        if self.use_skill and self.skill:
            success, content = self.skill.expand(
                title=title,
                summary=summary,
                source_url=source_url,
                style=style
            )
            
            if success:
                article['expanded_content'] = content
                article['skill_used'] = 'technical-blog-writing'
                article['skill_source'] = 'OpenClaw-sessions_spawn'
                print(f"\n[SKILL SUCCESS] Output: {len(content)} chars\n")
            else:
                # Skill 失败，回退到本地 LLM
                print(f"\n[SKILL FAILED] Reason: {content}")
                print(f"[FALLBACK: Using local LLM glm-5]\n")
                article['expanded_content'] = self._fallback_expand(title, summary, source_url)
                article['skill_used'] = 'llm-fallback'
                article['skill_source'] = 'local-glm-5'
        else:
            # 不使用 skill，直接用 LLM
            print(f"\n[USING LLM: glm-5 (no skill)]\n")
            article['expanded_content'] = self._fallback_expand(title, summary, source_url)
            article['skill_used'] = 'llm-direct'
            article['skill_source'] = 'local-glm-5'
            
        return article
    
    def _fallback_expand(self, title: str, summary: str, source_url: str) -> str:
        """
        回退扩写方法（使用本地 LLM）
        """
        prompt = f"""
请将以下技术文章摘要扩写为完整的博客文章。

标题: {title}
摘要: {summary}
原文链接: {source_url}

要求：
1. 保持技术准确性
2. 添加背景介绍和技术分析
3. 结构清晰，包含引言、正文、总结
4. 使用 Markdown 格式
5. 如果原文是英文，请翻译为中文

请直接输出 Markdown 内容：
"""
        
        content = self.llm_client.generate(prompt)
        return content


def expand_article(article: Dict, use_skill: bool = True) -> Dict:
    """
    扩写文章（便捷函数）
    
    Args:
        article: 文章数据
        use_skill: 是否使用 OpenClaw skill
        
    Returns:
        扩写后的文章数据
    """
    expander = ArticleExpander(use_skill=use_skill)
    return expander.expand(article)


# 测试
if __name__ == '__main__':
    test_article = {
        'title': 'GPT-4o 多模态能力解析',
        'summary': 'OpenAI 发布 GPT-4o，支持实时语音、图像、视频交互，响应速度提升 2x',
        'link': 'https://openai.com/blog/gpt-4o'
    }
    
    print("=" * 60)
    print("Testing ArticleExpander with OpenClaw skill...")
    print("=" * 60)
    
    expander = ArticleExpander(use_skill=True)
    result = expander.expand(test_article)
    
    print(f"\n{'='*60}")
    print(f"[RESULT]")
    print(f"  skill_used: {result.get('skill_used', 'unknown')}")
    print(f"  skill_source: {result.get('skill_source', 'unknown')}")
    print(f"  content_length: {len(result.get('expanded_content', ''))}")
    print(f"{'='*60}\n")
    
    if result.get('expanded_content'):
        print(f"Content preview (first 300 chars):\n")
        print(result['expanded_content'][:300] + "...")