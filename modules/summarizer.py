#!/usr/bin/env python3
"""
文章摘要模块 - 使用 OpenClaw skill: blog-post

显性标注: [USING SKILL: blog-post]
调用方式: OpenClaw sessions_spawn API
"""

import os
import sys
from typing import Dict, Optional

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.skill_client import BlogPostSkill
from modules.llm_client import SimpleLLMClient


class RSSSummarizer:
    """
    文章摘要器
    
    调用 OpenClaw sessions_spawn API 使用 [SKILL: blog-post]
    将长文章浓缩为精华摘要。
    """
    
    def __init__(self, config: Dict = None, use_skill: bool = True):
        """
        初始化摘要器
        
        Args:
            config: 配置字典（可选）
            use_skill: 是否使用 OpenClaw skill（默认 True）
        """
        self.config = config or {}
        self.use_skill = use_skill
        self.skill = BlogPostSkill() if use_skill else None
        self.llm_client = SimpleLLMClient()  # 从 config.yaml 读取
        
    def summarize(self, article: Dict, length: str = 'medium') -> Dict:
        """
        生成文章摘要 - 显性标注使用 OpenClaw skill
        
        Args:
            article: 文章数据（包含 title, content, description 等）
            length: 摘要长度（short/medium/long）
            
        Returns:
            包含摘要的文章数据（包含 skill_used 字段）
        """
        title = article.get('title', '')
        content = article.get('content', article.get('description', article.get('summary', '')))
        
        # ========== 显性标注：使用 OpenClaw skill ==========
        print(f"\n{'='*60}")
        print(f"[USING SKILL: blog-post]")
        print(f"[CALLING: OpenClaw sessions_spawn API]")
        print(f"[INPUT: title='{title[:50]}...']")
        print(f"{'='*60}\n")
        
        if self.use_skill and self.skill:
            success, summary = self.skill.summarize(
                title=title,
                content=content,
                length=length,
                audience='developer'
            )
            
            if success:
                article['ai_summary'] = summary
                article['skill_used'] = 'blog-post'
                article['skill_source'] = 'OpenClaw-sessions_spawn'
                print(f"\n[SKILL SUCCESS] Output: {len(summary)} chars\n")
            else:
                # Skill 失败，回退到本地 LLM
                print(f"\n[SKILL FAILED] Reason: {summary}")
                print(f"[FALLBACK: Using local LLM glm-5]\n")
                article['ai_summary'] = self._fallback_summarize(title, content, length)
                article['skill_used'] = 'llm-fallback'
                article['skill_source'] = 'local-glm-5'
        else:
            # 不使用 skill，直接用 LLM
            print(f"\n[USING LLM: glm-5 (no skill)]\n")
            article['ai_summary'] = self._fallback_summarize(title, content, length)
            article['skill_used'] = 'llm-direct'
            article['skill_source'] = 'local-glm-5'
            
        return article
    
    def _fallback_summarize(self, title: str, content: str, length: str) -> str:
        """
        回退摘要方法（使用本地 LLM）
        """
        length_guide = {
            'short': '100-200字',
            'medium': '200-400字',
            'long': '400-600字'
        }
        
        prompt = f"""
请为以下文章生成摘要。

标题: {title}
内容: {content[:1000]}

要求：
1. 长度: {length_guide.get(length, '200-400字')}
2. 突出核心观点和关键信息
3. 保持技术准确性
4. 如果原文是英文，请翻译为中文

摘要：
"""
        
        summary = self.llm_client.generate(prompt)
        return summary


def summarize_article(article: Dict, use_skill: bool = True) -> Dict:
    """
    生成摘要（便捷函数）
    
    Args:
        article: 文章数据
        use_skill: 是否使用 OpenClaw skill
        
    Returns:
        包含摘要的文章数据
    """
    summarizer = ArticleSummarizer(use_skill=use_skill)
    return summarizer.summarize(article)


# 测试
if __name__ == '__main__':
    test_article = {
        'title': 'Claude 3.5 Sonnet 发布',
        'content': 'Anthropic 发布 Claude 3.5 Sonnet，性能超越 Claude 3 Opus，同时保持了高水平的推理能力和安全性。新模型在编程、数学、推理等任务上表现出色...'
    }
    
    print("=" * 60)
    print("Testing ArticleSummarizer with OpenClaw skill...")
    print("=" * 60)
    
    summarizer = ArticleSummarizer(use_skill=True)
    result = summarizer.summarize(test_article)
    
    print(f"\n{'='*60}")
    print(f"[RESULT]")
    print(f"  skill_used: {result.get('skill_used', 'unknown')}")
    print(f"  skill_source: {result.get('skill_source', 'unknown')}")
    print(f"  summary_length: {len(result.get('ai_summary', ''))}")
    print(f"{'='*60}\n")
    
    if result.get('ai_summary'):
        print(f"Summary preview:\n")
        print(result['ai_summary'][:200] + "...")