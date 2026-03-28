#!/usr/bin/env python3
"""
本地处理器 - 直接执行博客流水线任务
不依赖 OpenClaw API，使用本地 AI API（如 OpenAI）
"""

import os
import json
import yaml
import feedparser
import requests
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime
import hashlib


class LocalWorker:
    """本地任务执行器"""
    
    def __init__(self, config_path: str = None):
        self.config = self._load_config(config_path)
        self.output_dir = Path("/root/home/blog-pipeline/output/articles")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # AI 配置 - 支持多种 API
        self.ai_config = self._get_ai_config()
    
    def _load_config(self, config_path: str = None) -> dict:
        if config_path is None:
            config_path = "/root/home/blog-pipeline/config.yaml"
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"加载配置失败: {e}")
            return {}
    
    def _get_ai_config(self) -> dict:
        """获取 AI 配置，优先环境变量"""
        return {
            'api_key': os.environ.get('OPENAI_API_KEY') or os.environ.get('AI_API_KEY'),
            'base_url': os.environ.get('AI_BASE_URL') or 'https://api.openai.com/v1',
            'model': os.environ.get('AI_MODEL') or 'gpt-3.5-turbo',
        }
    
    def _has_ai_config(self) -> bool:
        """检查是否配置了 AI API"""
        return bool(self.ai_config.get('api_key'))
    
    def fetch_rss(self, url: str, max_items: int = 5) -> List[Dict]:
        """抓取 RSS 源"""
        print(f"  抓取 RSS: {url}")
        try:
            feed = feedparser.parse(url)
            articles = []
            
            for entry in feed.entries[:max_items]:
                article = {
                    'title': entry.get('title', '无标题'),
                    'url': entry.get('link', ''),
                    'summary': entry.get('summary', entry.get('description', '')),
                    'published': entry.get('published', entry.get('updated', '')),
                    'source': feed.feed.get('title', '未知来源')
                }
                articles.append(article)
            
            print(f"    获取到 {len(articles)} 篇文章")
            return articles
        except Exception as e:
            print(f"    抓取失败: {e}")
            return []
    
    def summarize_article(self, title: str, content: str) -> Optional[str]:
        """生成文章摘要"""
        if not self._has_ai_config():
            # 无 API 时，截取前 200 字作为摘要
            return content[:200] + "..." if len(content) > 200 else content
        
        try:
            prompt = f"""请为以下文章生成一个简洁的中文摘要（200-300字）：

标题：{title}

内容：
{content[:2000]}

只返回摘要内容，不要其他解释。"""

            resp = requests.post(
                f"{self.ai_config['base_url']}/chat/completions",
                headers={
                    'Authorization': f"Bearer {self.ai_config['api_key']}",
                    'Content-Type': 'application/json'
                },
                json={
                    'model': self.ai_config['model'],
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0.7,
                    'max_tokens': 500
                },
                timeout=60
            )
            
            if resp.status_code == 200:
                return resp.json()['choices'][0]['message']['content']
            else:
                print(f"AI API 错误: {resp.status_code}")
                return content[:200] + "..."
        except Exception as e:
            print(f"摘要生成失败: {e}")
            return content[:200] + "..."
    
    def expand_article(self, title: str, summary: str, source_url: str = None) -> Optional[str]:
        """扩写文章"""
        if not self._has_ai_config():
            # 无 API 时，生成简单模板
            return f"""# {title}

{summary}

> 原文链接：{source_url or '无'}

---
*本文由博客流水线自动生成*
"""
        
        try:
            prompt = f"""请将以下摘要扩写成一篇完整的博客文章。

原标题：{title}
原始摘要：{summary}
{f'原始链接：{source_url}' if source_url else ''}

要求：
1. 扩写成 800-1200 字的完整文章
2. 保持原意，增加细节和深度
3. 使用 Markdown 格式
4. 文风专业但易读
5. 文末注明原文链接

直接返回文章内容，不要其他解释。"""

            resp = requests.post(
                f"{self.ai_config['base_url']}/chat/completions",
                headers={
                    'Authorization': f"Bearer {self.ai_config['api_key']}",
                    'Content-Type': 'application/json'
                },
                json={
                    'model': self.ai_config['model'],
                    'messages': [{'role': 'user', 'content': prompt}],
                    'temperature': 0.8,
                    'max_tokens': 2000
                },
                timeout=120
            )
            
            if resp.status_code == 200:
                return resp.json()['choices'][0]['message']['content']
            else:
                print(f"AI API 错误: {resp.status_code}")
                return None
        except Exception as e:
            print(f"扩写失败: {e}")
            return None
    
    def save_article(self, title: str, content: str, source_url: str = None) -> str:
        """保存文章到本地"""
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_title = "".join(c if c.isalnum() or c in (' ', '-', '_') else '' for c in title)
        safe_title = safe_title[:50].strip()
        filename = f"{timestamp}_{safe_title}.md"
        filepath = self.output_dir / filename
        
        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"  已保存: {filepath}")
        return str(filepath)
    
    def run_full_pipeline(self, rss_urls: List[str], max_items: int = 5) -> dict:
        """运行完整流水线"""
        print(f"\n{'='*50}")
        print(f"开始执行博客流水线...")
        print(f"{'='*50}")
        
        results = {
            'success': True,
            'articles_fetched': 0,
            'articles_processed': 0,
            'articles_saved': 0,
            'files': [],
            'errors': []
        }
        
        all_articles = []
        
        # 1. 抓取 RSS
        print(f"\n[1/3] 抓取 RSS 源...")
        for url in rss_urls:
            articles = self.fetch_rss(url, max_items=max(1, max_items // len(rss_urls)))
            all_articles.extend(articles)
        
        results['articles_fetched'] = len(all_articles)
        print(f"  总共获取 {len(all_articles)} 篇文章")
        
        if not all_articles:
            results['errors'].append("没有获取到任何文章")
            results['success'] = False
            return results
        
        # 2. 处理每篇文章
        print(f"\n[2/3] 处理文章...")
        max_process = min(len(all_articles), max_items)
        
        for i, article in enumerate(all_articles[:max_process]):
            print(f"\n  处理第 {i+1}/{max_process} 篇: {article['title'][:40]}...")
            
            # 生成摘要
            summary = self.summarize_article(article['title'], article['summary'])
            if not summary:
                results['errors'].append(f"摘要生成失败: {article['title']}")
                continue
            
            # 扩写文章
            expanded = self.expand_article(
                article['title'], 
                summary, 
                article['url']
            )
            
            if expanded:
                # 保存文章
                filepath = self.save_article(
                    article['title'],
                    expanded,
                    article['url']
                )
                results['files'].append(filepath)
                results['articles_processed'] += 1
                results['articles_saved'] += 1
            else:
                results['errors'].append(f"扩写失败: {article['title']}")
        
        # 3. 总结
        print(f"\n[3/3] 完成!")
        print(f"  抓取: {results['articles_fetched']} 篇")
        print(f"  处理: {results['articles_processed']} 篇")
        print(f"  保存: {results['articles_saved']} 篇")
        
        if results['errors']:
            print(f"  错误: {len(results['errors'])} 个")
        
        return results


# 单例
_worker = None

def get_worker() -> LocalWorker:
    global _worker
    if _worker is None:
        _worker = LocalWorker()
    return _worker


def run_pipeline(rss_urls: list, max_items: int = 5) -> dict:
    return get_worker().run_full_pipeline(rss_urls, max_items)