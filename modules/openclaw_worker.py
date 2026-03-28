#!/usr/bin/env python3
"""
OpenClaw Worker - 通过 OpenClaw API 执行博客流水线任务

这个模块负责：
1. 调用 OpenClaw 的 sessions_spawn API 创建 subagent
2. Subagent 使用 OpenClaw 的工具（web_fetch, web_search, AI 模型等）完成任务
3. 返回结果给博客流水线
"""

import os
import json
import requests
from typing import Optional, Dict, List
from pathlib import Path


class OpenClawWorker:
    """OpenClaw 任务执行器"""
    
    def __init__(self):
        self.gateway_url = os.environ.get('OPENCLAW_GATEWAY', 'http://localhost:18789')
        self.api_base = f'{self.gateway_url}/api'
    
    def spawn_task(self, task: str, timeout: int = 300, model: str = None) -> dict:
        """
        生成一个 OpenClaw subagent 来执行任务
        
        Args:
            task: 任务描述
            timeout: 超时秒数
            model: 指定模型（可选）
        
        Returns:
            执行结果
        """
        payload = {
            'task': task,
            'mode': 'run',  # one-shot execution
            'runtime': 'subagent',
            'timeoutSeconds': timeout
        }
        
        if model:
            payload['model'] = model
        
        try:
            resp = requests.post(
                f'{self.api_base}/sessions/spawn',
                json=payload,
                timeout=timeout + 10
            )
            return resp.json()
        except Exception as e:
            return {'error': str(e), 'success': False}
    
    def fetch_rss(self, url: str) -> dict:
        """使用 OpenClaw 的 web_fetch 抓取 RSS"""
        task = f"""抓取 RSS 源并解析文章列表。

RSS URL: {url}

请执行以下步骤：
1. 使用 web_fetch 工具获取 RSS 内容
2. 解析 RSS XML，提取文章标题、链接、摘要、发布时间
3. 返回 JSON 格式的文章列表

返回格式：
{{
  "articles": [
    {{
      "title": "文章标题",
      "url": "https://...",
      "summary": "摘要内容",
      "published": "发布时间"
    }}
  ]
}}
"""
        return self.spawn_task(task, timeout=60)
    
    def summarize_article(self, title: str, content: str) -> dict:
        """使用 OpenClaw AI 生成文章摘要"""
        task = f"""请为以下文章生成一个简洁的中文摘要（200-300字）：

标题：{title}

内容：
{content[:3000]}

要求：
1. 提取核心观点和关键信息
2. 保持客观中立
3. 使用流畅的中文
4. 返回纯文本摘要
"""
        return self.spawn_task(task, timeout=120)
    
    def expand_article(self, title: str, summary: str, source_url: str = None) -> dict:
        """使用 OpenClaw AI 扩写文章"""
        task = f"""请将以下摘要扩写成一篇完整的博客文章。

原标题：{title}
原始摘要：{summary}
{f'原始链接：{source_url}' if source_url else ''}

要求：
1. 扩写成 800-1500 字的完整文章
2. 保持原意，增加细节和深度
3. 使用 Markdown 格式
4. 包含适当的标题层级
5. 文风专业但易读
6. 如果可能，用 web_search 补充相关背景信息

返回格式：
# 标题

[文章正文...]

> 原文链接：{source_url if source_url else '无'}
"""
        return self.spawn_task(task, timeout=180)
    
    def generate_image_prompt(self, article_title: str, article_content: str) -> dict:
        """生成文章配图的提示词"""
        task = f"""为以下博客文章生成一个适合的配图提示词。

文章标题：{article_title}
文章内容摘要：{article_content[:500]}

请生成一个英文的图片生成提示词，要求：
1. 与文章主题相关
2. 适合作为博客封面图
3. 风格现代、专业
4. 返回纯英文提示词
"""
        return self.spawn_task(task, timeout=60)
    
    def publish_to_platform(self, article_path: str, platform: str = 'markdown') -> dict:
        """发布文章到指定平台"""
        task = f"""将文章发布到 {platform} 平台。

文章路径：{article_path}

请读取文章内容并按照 {platform} 的格式要求进行发布。
"""
        return self.spawn_task(task, timeout=120)
    
    def run_full_pipeline(self, rss_urls: List[str], max_articles: int = 5) -> dict:
        """运行完整流水线"""
        task = f"""执行完整的博客流水线：

1. 抓取以下 RSS 源的文章（每个源最多 {max_articles // len(rss_urls)} 篇）：
{chr(10).join(f'- {url}' for url in rss_urls)}

2. 对每篇文章：
   - 生成中文摘要（200-300字）
   - 扩写成完整博客文章（800-1500字，Markdown格式）
   - 保存到 /root/home/blog-pipeline/output/articles/ 目录

3. 返回生成的文章列表和路径

注意：
- 使用 web_fetch 抓取 RSS
- 文件名使用文章标题的英文翻译或数字编号
- 每篇文章单独一个 .md 文件
"""
        return self.spawn_task(task, timeout=300)


# 单例实例
_worker = None

def get_worker() -> OpenClawWorker:
    global _worker
    if _worker is None:
        _worker = OpenClawWorker()
    return _worker


# 便捷函数
def fetch_rss(url: str) -> dict:
    return get_worker().fetch_rss(url)

def summarize(title: str, content: str) -> dict:
    return get_worker().summarize_article(title, content)

def expand(title: str, summary: str, source_url: str = None) -> dict:
    return get_worker().expand_article(title, summary, source_url)

def run_pipeline(rss_urls: list, max_articles: int = 5) -> dict:
    return get_worker().run_full_pipeline(rss_urls, max_articles)